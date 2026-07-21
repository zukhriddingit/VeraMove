"""Explicit one-call provider smoke that cannot mutate a canonical VeraMove job."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_voice_preflight import (  # noqa: E402
    PreflightReport,
    redact_identifier,
    run_default_preflight,
)
from services.api.app.contracts import JobSpecV1, Vendor, VendorCallPlanV1  # noqa: E402
from services.api.app.core.config import Settings  # noqa: E402
from services.api.app.integrations.elevenlabs.live import (  # noqa: E402
    ElevenLabsVoiceProvider,
    HttpxJsonTransport,
)
from services.api.app.orchestration.fixtures import DemoFixtures  # noqa: E402
from services.api.app.orchestration.models import VoiceCallResult  # noqa: E402
from services.api.app.orchestration.providers import VoiceCallDestination  # noqa: E402

SMOKE_CALL_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SMOKE_CONFIRMED_AT = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


class SmokeVoiceProvider(Protocol):
    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
        destination: VoiceCallDestination,
        call_plan: VendorCallPlanV1 | None,
    ) -> VoiceCallResult: ...


def _locked_synthetic_fixture(fixtures: DemoFixtures) -> JobSpecV1:
    payload = fixtures.load_job().model_dump(mode="json")
    payload.update(
        {
            "confirmed": True,
            "confirmed_at": SMOKE_CONFIRMED_AT.isoformat(),
            "locked_version": payload["version"],
            "data_classification": "role_play",
        }
    )
    return JobSpecV1.model_validate(payload)


def run_supervised_smoke(
    settings: Settings,
    *,
    provider: SmokeVoiceProvider,
    preflight: PreflightReport,
    confirmed: bool,
    fixtures: DemoFixtures | None = None,
) -> dict[str, str | int | bool]:
    """Place slot zero only after explicit confirmation and a passing preflight."""

    if not confirmed:
        raise ValueError("The one-call smoke requires explicit confirmation")
    live_config = settings.require_live_voice_config()
    if not preflight.ready:
        raise ValueError("The one-call smoke requires a passing live preflight")
    expected_identifiers = {
        "agent_config_version": redact_identifier(live_config.agent_config_version),
        "intake_agent": redact_identifier(live_config.intake_agent_id),
        "outbound_agent": redact_identifier(live_config.outbound_agent_id),
        "phone_number": redact_identifier(live_config.phone_number_id),
        "public_api": redact_identifier(live_config.public_api_base_url),
        "supabase_project": redact_identifier(settings.supabase.url),
    }
    if preflight.identifiers != expected_identifiers:
        raise ValueError("The one-call smoke requires preflight for the current configuration")

    source = fixtures or DemoFixtures()
    job_spec = _locked_synthetic_fixture(source)
    role_play_vendors = source.load_live_role_play_vendors()
    if len(role_play_vendors) != 3:
        raise ValueError("The synthetic smoke roster must contain exactly three vendors")
    result = provider.initiate_quote_call(
        job_spec,
        role_play_vendors[0],
        SMOKE_CALL_ID,
        VoiceCallDestination.supervised_role_play(0),
        None,
    )
    return {
        "correlation": redact_identifier(SMOKE_CALL_ID),
        "destination_slots_used": 1,
        "preflight_ready": True,
        "provider_reference_received": result.reference is not None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Place one supervised synthetic outbound call using destination slot zero. "
            "This does not create or transition a canonical job."
        )
    )
    parser.add_argument(
        "--confirm-supervised-one-call",
        action="store_true",
        help="Required explicit confirmation that slot zero belongs to a consenting participant.",
    )
    args = parser.parse_args(argv)
    if not args.confirm_supervised_one_call:
        parser.error("--confirm-supervised-one-call is required; no call was placed")

    settings = Settings.from_env()
    preflight = run_default_preflight(settings, check_only=True)
    if not preflight.ready:
        print(json.dumps(preflight.to_safe_dict(), sort_keys=True))
        return 1
    provider = ElevenLabsVoiceProvider(settings, HttpxJsonTransport())
    result = run_supervised_smoke(
        settings,
        provider=provider,
        preflight=preflight,
        confirmed=True,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
