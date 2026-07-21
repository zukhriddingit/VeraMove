"""Fail-closed ElevenLabs native Twilio outbound-call adapter."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx

from services.api.app.contracts import (
    CallContext,
    JobSpecV1,
    QuoteV1,
    Vendor,
    VendorCallPlanV1,
)
from services.api.app.core.config import LiveVoiceConfig, Settings
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.base import JsonHttpTransport
from services.api.app.orchestration.models import (
    VoiceCallReference,
    VoiceCallResult,
    job_spec_sha256,
)
from services.api.app.orchestration.providers import VoiceCallDestination


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
        destination: VoiceCallDestination | int | None = None,
        call_plan: VendorCallPlanV1 | None = None,
    ) -> VoiceCallResult:
        destination = self._normalize_destination(destination)
        config = self._config_for(destination)
        assert config.outbound_agent_id is not None
        return self._initiate(
            config,
            config.outbound_agent_id,
            job_spec,
            vendor,
            call_id,
            destination,
            {
                "call_mode": "quote",
                "verified_competitor_quote_id": "",
                "verified_competitor_total": "",
                "verified_competitor_evidence_json": "",
                "negotiation_objective": "",
                **self._call_plan_variables(call_plan, job_spec, vendor),
            },
        )

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
        destination: VoiceCallDestination | int | None = None,
        call_plan: VendorCallPlanV1 | None = None,
    ) -> VoiceCallResult:
        destination = self._normalize_destination(destination)
        config = self._config_for(destination)
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
            destination,
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
                **self._call_plan_variables(
                    call_plan,
                    job_spec,
                    target_vendor,
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
        destination: VoiceCallDestination,
        dynamic_variables: dict[str, str],
    ) -> VoiceCallResult:
        assert config.api_key is not None
        assert config.phone_number_id is not None
        assert config.outbound_agent_id is not None
        assert config.agent_config_version is not None
        destination_number = self._destination_number(config, destination)
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
                    "call_context": destination.call_context.value,
                    **dynamic_variables,
                }
            },
            "call_recording_enabled": destination.recording_consented,
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

    def _config_for(self, destination: VoiceCallDestination) -> LiveVoiceConfig:
        if destination.call_context is CallContext.OFFICIAL_BUSINESS:
            return self._settings.require_real_vendor_call_config()
        return self._settings.require_live_voice_config()

    @staticmethod
    def _normalize_destination(
        destination: VoiceCallDestination | int | None,
    ) -> VoiceCallDestination:
        if destination is None:
            return VoiceCallDestination.supervised_role_play(0)
        if isinstance(destination, bool):
            raise ProviderRequestError("Invalid live destination slot")
        if isinstance(destination, int):
            if destination not in {0, 1, 2}:
                raise ProviderRequestError("Invalid live destination slot")
            return VoiceCallDestination.supervised_role_play(destination)
        return destination

    @staticmethod
    def _destination_number(
        config: LiveVoiceConfig,
        destination: VoiceCallDestination,
    ) -> str:
        if destination.call_context is CallContext.OFFICIAL_BUSINESS:
            if destination.normalized_number is None:
                raise ProviderRequestError(
                    "Authorized vendor destination could not be resolved"
                )
            return destination.normalized_number
        try:
            return config.destination_numbers[destination.destination_slot]
        except (IndexError, TypeError):
            raise ProviderRequestError("Invalid live destination slot") from None

    @staticmethod
    def _call_plan_variables(
        call_plan: VendorCallPlanV1 | None,
        job_spec: JobSpecV1,
        vendor: Vendor,
    ) -> dict[str, str]:
        if call_plan is None:
            return {
                "vendor_call_plan_json": "",
                "website_claims_json": "[]",
                "verification_questions_json": "[]",
            }
        if (
            call_plan.vendor_id != vendor.vendor_id
            or call_plan.job_spec_version != job_spec.version
            or call_plan.job_spec_sha256 != job_spec_sha256(job_spec)
        ):
            raise ProviderRequestError(
                "Vendor call plan does not match the locked JobSpec"
            )
        return {
            "vendor_call_plan_json": json.dumps(
                call_plan.model_dump(mode="json"),
                separators=(",", ":"),
                sort_keys=True,
            ),
            "website_claims_json": json.dumps(
                [item.model_dump(mode="json") for item in call_plan.website_claims],
                separators=(",", ":"),
                sort_keys=True,
            ),
            "verification_questions_json": json.dumps(
                [item.model_dump(mode="json") for item in call_plan.questions],
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
