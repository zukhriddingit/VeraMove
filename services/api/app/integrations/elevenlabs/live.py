"""Fail-closed ElevenLabs native Twilio outbound-call adapter."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx

from services.api.app.contracts import JobSpecV1, QuoteV1, Vendor
from services.api.app.core.config import LiveVoiceConfig, Settings
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.base import JsonHttpTransport
from services.api.app.orchestration.models import VoiceCallReference, VoiceCallResult


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

    initial_call_limit = 1

    def __init__(
        self,
        settings: Settings,
        transport: JsonHttpTransport,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> VoiceCallResult:
        config = self._settings.require_live_voice_config()
        assert config.quote_agent_id is not None
        return self._initiate(
            config,
            config.quote_agent_id,
            job_spec,
            vendor,
            call_id,
            {},
        )

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
    ) -> VoiceCallResult:
        config = self._settings.require_live_voice_config()
        assert config.negotiator_agent_id is not None
        return self._initiate(
            config,
            config.negotiator_agent_id,
            job_spec,
            target_vendor,
            call_id,
            {
                "verified_competitor_quote_id": str(
                    verified_competitor.quote_id
                ),
                "verified_competitor_total": str(
                    verified_competitor.negotiated_total
                ),
                "target_vendor_name": target_vendor.name,
                "planned_objective": json.dumps(
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
        dynamic_variables: dict[str, str],
    ) -> VoiceCallResult:
        assert config.api_key is not None
        assert config.phone_number_id is not None
        assert config.test_to_number is not None
        payload = {
            "agent_id": agent_id,
            "agent_phone_number_id": config.phone_number_id,
            "to_number": config.test_to_number,
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "job_id": str(job_spec.job_id),
                    "call_id": str(call_id),
                    "vendor_name": vendor.name,
                    "job_spec_json": job_spec.model_dump_json(),
                    **dynamic_variables,
                }
            },
            "call_recording_enabled": True,
        }
        body = self._transport.post_json(
            (
                f"{config.api_base_url.rstrip('/')}"
                "/v1/convai/twilio/outbound-call"
            ),
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
            raise ProviderRequestError(
                "ElevenLabs response omitted conversation_id"
            )
        if not isinstance(provider_call_id, str) or not provider_call_id.strip():
            raise ProviderRequestError("ElevenLabs response omitted callSid")
        return VoiceCallResult(
            reference=VoiceCallReference(
                conversation_id=conversation_id.strip(),
                provider_call_id=provider_call_id.strip(),
            )
        )
