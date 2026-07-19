"""Fail-closed ElevenLabs native Twilio outbound-call adapter."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

import httpx

from services.api.app.contracts import JobSpecV1, QuoteV1, Vendor
from services.api.app.core.config import LiveVoiceConfig, Settings
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.base import JsonHttpTransport
from services.api.app.orchestration.models import (
    VoiceCallReference,
    VoiceCallResult,
    job_spec_sha256,
)


class HttpxJsonTransport:
    """Send one JSON request while translating transport details into safe errors."""

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("ElevenLabs outbound call failed") from exc
        if not isinstance(body, dict):
            raise ProviderRequestError("ElevenLabs returned a non-object response")
        return body


class ElevenLabsVoiceProvider:
    """Initiate one explicitly enabled native ElevenLabs/Twilio call at a time."""

    initial_call_limit = 3

    def __init__(
        self,
        settings: Settings,
        transport: JsonHttpTransport,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def outbound_agent_id(self) -> str:
        return self._settings.live_voice.outbound_agent_id or "unconfigured-outbound-agent"

    @property
    def agent_config_version(self) -> str:
        return self._settings.live_voice.agent_config_version or "unconfigured-version"

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        destination_slot: Literal[0, 1, 2] = 0,
    ) -> VoiceCallResult:
        config = self._settings.require_live_voice_config()
        assert config.outbound_agent_id is not None
        return self._initiate(
            config,
            config.outbound_agent_id,
            job_spec,
            vendor,
            call_id,
            destination_slot,
            {"call_mode": "quote"},
        )

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
        destination_slot: Literal[0, 1, 2] = 0,
    ) -> VoiceCallResult:
        config = self._settings.require_live_voice_config()
        assert config.outbound_agent_id is not None
        leverage_total = (
            verified_competitor.comparable_total
            if verified_competitor.comparable_total is not None
            else verified_competitor.negotiated_total
        )
        if leverage_total is None:
            raise ProviderRequestError("Verified competitor omitted a comparable total")
        return self._initiate(
            config,
            config.outbound_agent_id,
            job_spec,
            target_vendor,
            call_id,
            destination_slot,
            {
                "call_mode": "negotiation",
                "verified_competitor_quote_id": str(verified_competitor.quote_id),
                "verified_competitor_total": str(leverage_total),
                "verified_competitor_evidence_json": json.dumps(
                    {
                        "evidence_ids": [
                            str(item.evidence_id)
                            for item in verified_competitor.transcript_evidence
                        ]
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "negotiation_objective": json.dumps(
                    {
                        "concessions": planned_quote.concessions,
                        "currency": planned_quote.currency,
                        "target_total": str(planned_quote.negotiated_total),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        )

    def _initiate(
        self,
        config: LiveVoiceConfig,
        agent_id: str,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        destination_slot: Literal[0, 1, 2],
        dynamic_variables: dict[str, str],
    ) -> VoiceCallResult:
        assert config.api_key is not None
        assert config.phone_number_id is not None
        assert config.outbound_agent_id is not None
        assert config.agent_config_version is not None
        if isinstance(destination_slot, bool) or destination_slot not in {0, 1, 2}:
            raise ProviderRequestError("Invalid live destination slot")
        try:
            destination_number = config.destination_numbers[destination_slot]
        except (IndexError, TypeError):
            raise ProviderRequestError("Invalid live destination slot") from None
        canonical_job_spec_json = json.dumps(
            job_spec.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        payload = {
            "agent_id": agent_id,
            "agent_phone_number_id": config.phone_number_id,
            "to_number": destination_number,
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "job_id": str(job_spec.job_id),
                    "call_id": str(call_id),
                    "vendor_id": str(vendor.vendor_id),
                    "vendor_name": vendor.name,
                    "job_spec_version": job_spec.version,
                    "job_spec_json": canonical_job_spec_json,
                    "job_spec_sha256": job_spec_sha256(job_spec),
                    "agent_config_version": config.agent_config_version,
                    **dynamic_variables,
                }
            },
            "call_recording_enabled": True,
        }
        body = self._transport.post_json(
            (f"{config.api_base_url.rstrip('/')}/v1/convai/twilio/outbound-call"),
            {
                "xi-api-key": config.api_key,
                "content-type": "application/json",
            },
            payload,
            timeout_seconds=10.0,
        )
        if body.get("success") is not True:
            raise ProviderRequestError("ElevenLabs rejected the outbound call")
        conversation_id = body.get("conversation_id")
        provider_call_id = body.get("callSid")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ProviderRequestError("ElevenLabs response omitted conversation_id")
        if not isinstance(provider_call_id, str) or not provider_call_id.strip():
            raise ProviderRequestError("ElevenLabs response omitted callSid")
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id=conversation_id.strip(),
                provider_call_id=provider_call_id.strip(),
            )
        )
