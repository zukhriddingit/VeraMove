"""Read-only, redacted readiness checks for a supervised live voice run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.app.core.config import LiveVoiceConfig, Settings, SupabaseConfig  # noqa: E402

EXPECTED_AGENT_NAMES = ("VeraMove Intake", "VeraMove Outbound Negotiator")
INTAKE_PROMPT_VARIABLES = (
    "job_id",
    "intake_session_id",
    "agent_config_version",
    "intake_data_mode",
    "resume_mode",
    "partial_job_spec_json",
    "missing_fields_json",
)
OUTBOUND_PROMPT_VARIABLES = (
    "job_id",
    "call_id",
    "vendor_id",
    "vendor_name",
    "job_spec_version",
    "job_spec_json",
    "call_mode",
    "agent_config_version",
    "call_context",
    "vendor_call_plan_json",
    "website_claims_json",
    "verification_questions_json",
    "verified_competitor_quote_id",
    "verified_competitor_total",
    "verified_competitor_evidence_json",
    "negotiation_objective",
)
INTAKE_DATA_COLLECTION_FIELDS = (
    "recording_consent",
    "summary_confirmed",
    "move_date",
    "date_flexible",
    "origin_address_summary",
    "origin_dwelling_type",
    "origin_floors",
    "origin_stairs",
    "origin_elevator_access",
    "origin_parking_distance_feet",
    "destination_address_summary",
    "destination_dwelling_type",
    "destination_floors",
    "destination_stairs",
    "destination_elevator_access",
    "destination_parking_distance_feet",
    "bedroom_count",
    "inventory_json",
    "special_items_json",
    "packing",
    "disassembly",
    "storage",
    "storage_days",
    "insurance_preference",
)
OUTBOUND_DATA_COLLECTION_FIELDS = (
    "recording_consent",
    "recipient_opt_out",
    "outcome_type",
    "callback_at",
    "outcome_reason",
    "headline_total",
    "deposit",
    "original_total",
    "negotiated_total",
    "binding_type",
    "availability_status",
    "availability",
    "fee_items_json",
    "addressed_fee_categories_json",
    "concessions_json",
)
MIN_INITIAL_CALLS = 3
MAX_DEMO_RETENTION_DAYS = 7
_VERSION_PATTERN = re.compile(r'^agent_config_version:\s*["\']?([^"\'\s]+)', re.MULTILINE)


def redact_identifier(value: object) -> str:
    """Return a stable one-way label instead of an identifier or personal value."""

    normalized = str(value) if value is not None else "missing"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest}"


@dataclass(frozen=True, slots=True)
class ProviderReadiness:
    """Provider facts reduced to booleans and counts before reporting."""

    agent_count: int = 0
    expected_agents_match: bool = False
    agent_config_version_matches: bool = False
    provider_version_ids_present: bool = False
    provider_version_descriptions_match: bool = False
    prompt_dynamic_variables_match: bool = False
    data_collection_fields_match: bool = False
    provider_tools_omitted: bool = False
    intake_pre_call_enabled: bool = False
    workspace_pre_call_configured: bool = False
    post_call_events_configured: bool = False
    post_call_webhook_enabled: bool = False
    inbound_phone_assigned_to_intake: bool = False
    audio_saving_agent_count: int = 0
    short_retention_agent_count: int = 0
    concurrency_capacity: int = 0
    daily_call_capacity: int = 0
    provider_credits_available: bool = False


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Safe readiness result. It deliberately contains no raw provider values."""

    check_only: bool
    ready: bool
    identifiers: dict[str, str]
    counts: dict[str, int]
    checks: dict[str, bool]

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "check_only": self.check_only,
            "ready_for_supervised_three_call_run": self.ready,
            "identifiers": dict(self.identifiers),
            "counts": dict(self.counts),
            "checks": dict(self.checks),
        }


class ProviderPreflightClient(Protocol):
    def inspect(self, config: LiveVoiceConfig) -> ProviderReadiness: ...


class SupabasePreflightClient(Protocol):
    def is_reachable(self, config: SupabaseConfig) -> bool: ...


class PublicWebhookPreflightClient(Protocol):
    def is_reachable(self, public_api_base_url: str) -> bool: ...


class HttpElevenLabsPreflightClient:
    """Read provider configuration and reduce it to safe readiness facts."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def inspect(self, config: LiveVoiceConfig) -> ProviderReadiness:
        if config.api_key is None:
            return ProviderReadiness()
        headers = {"xi-api-key": config.api_key, "accept": "application/json"}
        agent_ids = (config.intake_agent_id, config.outbound_agent_id)
        if any(agent_id is None for agent_id in agent_ids) or config.phone_number_id is None:
            return ProviderReadiness()

        agents = [
            self._get_json(config, f"/v1/convai/agents/{agent_id}", headers)
            for agent_id in agent_ids
        ]
        version_ids = tuple(
            _first_string(agent, (("version_id",),)) for agent in agents
        )
        branch_ids = tuple(
            _first_string(agent, (("branch_id",),)) for agent in agents
        )
        versions = [
            self._get_json(
                config,
                f"/v1/convai/agents/{agent_id}/versions/{version_id}",
                headers,
            )
            for agent_id, version_id in zip(agent_ids, version_ids, strict=True)
            if version_id is not None
        ]
        workspace_settings = self._get_json(config, "/v1/convai/settings", headers)
        workspace_webhooks = self._get_json(
            config,
            "/v1/workspace/webhooks",
            headers,
            params={"include_usages": "true"},
        )
        phone_number = self._get_json(
            config,
            f"/v1/convai/phone-numbers/{config.phone_number_id}",
            headers,
        )
        subscription = self._get_json(config, "/v1/user/subscription", headers)
        names = tuple(_first_string(agent, (("name",), ("agent", "name"))) for agent in agents)
        returned_ids = tuple(
            _first_string(agent, (("agent_id",), ("id",))) for agent in agents
        )
        identities_match = names == EXPECTED_AGENT_NAMES and all(
            returned in {None, expected}
            for returned, expected in zip(returned_ids, agent_ids, strict=True)
        )
        provider_version_ids_present = (
            len(versions) == len(agents)
            and all(version_ids)
            and all(branch_ids)
            and all(
                _version_identity_matches(
                    version,
                    expected_agent_id=agent_id,
                    expected_version_id=version_id,
                    expected_branch_id=branch_id,
                )
                for version, agent_id, version_id, branch_id in zip(
                    versions,
                    agent_ids,
                    version_ids,
                    branch_ids,
                    strict=True,
                )
            )
        )
        expected_version_description = (
            f"VeraMove {config.agent_config_version}"
            if config.agent_config_version is not None
            else None
        )
        provider_versions_match = (
            provider_version_ids_present
            and expected_version_description is not None
            and all(
                _first_string(version, (("version_description",),))
                == expected_version_description
                for version in versions
            )
        )
        prompt_variables_match = all(
            _prompt_contains_variables(agent, required)
            for agent, required in zip(
                agents,
                (INTAKE_PROMPT_VARIABLES, OUTBOUND_PROMPT_VARIABLES),
                strict=True,
            )
        )
        data_collection_fields_match = all(
            _data_collection_matches(agent, required)
            for agent, required in zip(
                agents,
                (INTAKE_DATA_COLLECTION_FIELDS, OUTBOUND_DATA_COLLECTION_FIELDS),
                strict=True,
            )
        )
        provider_tools_omitted = all(_provider_tools_omitted(agent) for agent in agents)
        intake_pre_call_enabled = (
            _conversation_initiation_enabled(agents[0]) is True
            and _conversation_initiation_enabled(agents[1]) is False
        )
        post_call_webhook_id = _first_string(
            workspace_settings,
            (("webhooks", "post_call_webhook_id"),),
        )
        audio_count = sum(_audio_saving_enabled(agent) for agent in agents)
        retention_count = sum(
            0 < _retention_days(agent) <= MAX_DEMO_RETENTION_DAYS for agent in agents
        )
        concurrency = _first_int(
            subscription,
            (
                ("concurrency_limit",),
                ("workspace_concurrency_limit",),
                ("limits", "concurrency"),
            ),
        )
        if concurrency is None:
            agent_concurrency = [
                _first_int(
                    agent,
                    (
                        ("platform_settings", "call_limits", "agent_concurrency_limit"),
                        ("platform_settings", "call_limits", "concurrency_limit"),
                    ),
                )
                for agent in agents
            ]
            concurrency = min(
                (value for value in agent_concurrency if value is not None),
                default=0,
            )

        daily_capacity = _remaining_count(
            subscription,
            remaining_paths=(("daily_calls_remaining",), ("limits", "daily_calls_remaining")),
            limit_paths=(("daily_call_limit",), ("limits", "daily_calls")),
            used_paths=(("daily_calls_used",), ("usage", "daily_calls")),
        )
        if daily_capacity is None:
            agent_daily_capacity = [
                _remaining_count(
                    agent,
                    remaining_paths=(("platform_settings", "call_limits", "daily_remaining"),),
                    limit_paths=(("platform_settings", "call_limits", "daily_limit"),),
                    used_paths=(("platform_settings", "call_limits", "daily_used"),),
                )
                for agent in agents
            ]
            known_agent_capacity = [
                value for value in agent_daily_capacity if value is not None
            ]
            if known_agent_capacity:
                daily_capacity = min(known_agent_capacity)
        if daily_capacity is None:
            explicit_daily_limits = [
                _first_int(
                    agent,
                    (("platform_settings", "call_limits", "daily_limit"),),
                )
                for agent in agents
            ]
            known_daily_limits = [
                value for value in explicit_daily_limits if value is not None
            ]
            daily_capacity = min(known_daily_limits, default=0)

        return ProviderReadiness(
            agent_count=len(agents),
            expected_agents_match=identities_match,
            agent_config_version_matches=_local_agent_versions_match(
                config.agent_config_version
            ),
            provider_version_ids_present=provider_version_ids_present,
            provider_version_descriptions_match=provider_versions_match,
            prompt_dynamic_variables_match=prompt_variables_match,
            data_collection_fields_match=data_collection_fields_match,
            provider_tools_omitted=provider_tools_omitted,
            intake_pre_call_enabled=intake_pre_call_enabled,
            workspace_pre_call_configured=_workspace_pre_call_configured(
                workspace_settings,
                expected_url=(
                    f"{config.public_api_base_url.rstrip('/')}"
                    "/api/webhooks/elevenlabs/pre-call"
                    if config.public_api_base_url is not None
                    else None
                ),
            ),
            post_call_events_configured=_post_call_events_configured(
                workspace_settings
            ),
            post_call_webhook_enabled=_post_call_webhook_enabled(
                workspace_webhooks,
                post_call_webhook_id,
                expected_url=(
                    f"{config.public_api_base_url.rstrip('/')}/api/webhooks/elevenlabs"
                    if config.public_api_base_url is not None
                    else None
                ),
            ),
            inbound_phone_assigned_to_intake=_phone_assigned_to_agent(
                phone_number,
                expected_phone_number_id=config.phone_number_id,
                expected_agent_id=config.intake_agent_id,
            ),
            audio_saving_agent_count=audio_count,
            short_retention_agent_count=retention_count,
            concurrency_capacity=max(0, concurrency),
            daily_call_capacity=max(0, daily_capacity),
            provider_credits_available=_credits_available(subscription),
        )

    def _get_json(
        self,
        config: LiveVoiceConfig,
        path: str,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = httpx.get(
            f"{config.api_base_url.rstrip('/')}{path}",
            headers=headers,
            params=params,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Provider readiness response was not an object")
        return body


class HttpSupabasePreflightClient:
    """Probe one bounded server-only PostgREST query without printing its body."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def is_reachable(self, config: SupabaseConfig) -> bool:
        if config.url is None or config.secret_key is None:
            return False
        try:
            response = httpx.get(
                f"{config.url.rstrip('/')}/rest/v1/jobs",
                headers={
                    "apikey": config.secret_key,
                    "authorization": f"Bearer {config.secret_key}",
                    "accept": "application/json",
                },
                params={"select": "id", "limit": "1"},
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 300


class HttpPublicWebhookPreflightClient:
    """Verify the public API and fail-closed post-call webhook from outside the app."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    def is_reachable(self, public_api_base_url: str) -> bool:
        base_url = public_api_base_url.rstrip("/")
        try:
            health = httpx.get(f"{base_url}/health", timeout=self._timeout_seconds)
            if health.status_code < 200 or health.status_code >= 300:
                return False
            health_body = health.json()
            if not isinstance(health_body, dict) or health_body.get("mode") != "live":
                return False
            webhook = httpx.post(
                f"{base_url}/api/webhooks/elevenlabs",
                content=b"{}",
                headers={"content-type": "application/json"},
                timeout=self._timeout_seconds,
            )
        except (httpx.HTTPError, ValueError):
            return False
        return webhook.status_code == 401


def run_preflight(
    settings: Settings,
    *,
    provider: ProviderPreflightClient,
    supabase: SupabasePreflightClient,
    public_webhook: PublicWebhookPreflightClient,
    check_only: bool,
) -> PreflightReport:
    """Run bounded read-only checks and return only safe readiness fields."""

    config_valid = True
    try:
        live_config = settings.require_live_voice_config()
    except Exception:
        config_valid = False
        live_config = settings.live_voice

    provider_state = ProviderReadiness()
    supabase_reachable = False
    public_webhook_reachable = False
    if config_valid:
        try:
            provider_state = provider.inspect(live_config)
        except Exception:
            provider_state = ProviderReadiness()
        try:
            supabase_reachable = supabase.is_reachable(settings.supabase)
        except Exception:
            supabase_reachable = False
        assert live_config.public_api_base_url is not None
        try:
            public_webhook_reachable = public_webhook.is_reachable(
                live_config.public_api_base_url
            )
        except Exception:
            public_webhook_reachable = False

    checks = {
        "configuration": config_valid,
        "expected_agents": provider_state.agent_count == 2
        and provider_state.expected_agents_match,
        "agent_config_version": provider_state.agent_config_version_matches,
        "provider_version_ids": provider_state.provider_version_ids_present,
        "provider_version_descriptions": (
            provider_state.provider_version_descriptions_match
        ),
        "prompt_dynamic_variables": provider_state.prompt_dynamic_variables_match,
        "data_collection_fields": provider_state.data_collection_fields_match,
        "no_unreviewed_provider_tools": provider_state.provider_tools_omitted,
        "intake_only_pre_call_enablement": provider_state.intake_pre_call_enabled,
        "workspace_pre_call_secret_locator": (
            provider_state.workspace_pre_call_configured
        ),
        "post_call_events": provider_state.post_call_events_configured,
        "post_call_webhook_enabled": provider_state.post_call_webhook_enabled,
        "inbound_phone_assigned_to_intake": (
            provider_state.inbound_phone_assigned_to_intake
        ),
        "audio_saving": provider_state.audio_saving_agent_count == 2,
        "short_nonzero_retention": provider_state.short_retention_agent_count == 2,
        "concurrency_available": provider_state.concurrency_capacity >= 1,
        "daily_limit_available": provider_state.daily_call_capacity >= MIN_INITIAL_CALLS,
        "provider_credits": provider_state.provider_credits_available,
        "supabase_connectivity": supabase_reachable,
        "public_webhook_reachability": public_webhook_reachable,
        "sequential_dispatch_required": 0 < provider_state.concurrency_capacity < 3,
    }
    readiness_keys = tuple(key for key in checks if key != "sequential_dispatch_required")
    ready = all(checks[key] for key in readiness_keys)
    return PreflightReport(
        check_only=check_only,
        ready=ready,
        identifiers={
            "agent_config_version": redact_identifier(live_config.agent_config_version),
            "intake_agent": redact_identifier(live_config.intake_agent_id),
            "outbound_agent": redact_identifier(live_config.outbound_agent_id),
            "phone_number": redact_identifier(live_config.phone_number_id),
            "public_api": redact_identifier(live_config.public_api_base_url),
            "supabase_project": redact_identifier(settings.supabase.url),
        },
        counts={
            "agents": provider_state.agent_count,
            "audio_saving_agents": provider_state.audio_saving_agent_count,
            "concurrency_capacity": provider_state.concurrency_capacity,
            "daily_call_capacity": provider_state.daily_call_capacity,
            "short_retention_agents": provider_state.short_retention_agent_count,
        },
        checks=checks,
    )


def run_default_preflight(settings: Settings, *, check_only: bool = True) -> PreflightReport:
    return run_preflight(
        settings,
        provider=HttpElevenLabsPreflightClient(),
        supabase=HttpSupabasePreflightClient(),
        public_webhook=HttpPublicWebhookPreflightClient(),
        check_only=check_only,
    )


def _dig(body: dict[str, Any], path: tuple[str, ...]) -> object:
    current: object = body
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _first_string(
    body: dict[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> str | None:
    for path in paths:
        value = _dig(body, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_int(
    body: dict[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> int | None:
    for path in paths:
        value = _dig(body, path)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _first_bool(
    body: dict[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> bool | None:
    for path in paths:
        value = _dig(body, path)
        if isinstance(value, bool):
            return value
    return None


def _version_identity_matches(
    version: dict[str, Any],
    *,
    expected_agent_id: str | None,
    expected_version_id: str | None,
    expected_branch_id: str | None,
) -> bool:
    return (
        expected_agent_id is not None
        and expected_version_id is not None
        and expected_branch_id is not None
        and _first_string(version, (("agent_id",),)) == expected_agent_id
        and _first_string(version, (("id",),)) == expected_version_id
        and _first_string(version, (("branch_id",),)) == expected_branch_id
    )


def _prompt_contains_variables(
    agent: dict[str, Any],
    required_variables: tuple[str, ...],
) -> bool:
    prompt = _first_string(
        agent,
        (
            ("conversation_config", "agent", "prompt", "prompt"),
            ("conversation_config", "prompt", "prompt"),
        ),
    )
    return prompt is not None and all(
        f"{{{{{variable}}}}}" in prompt for variable in required_variables
    )


def _data_collection_matches(
    agent: dict[str, Any],
    required_fields: tuple[str, ...],
) -> bool:
    collection = _dig(agent, ("platform_settings", "data_collection"))
    if isinstance(collection, dict):
        identifiers = set(collection)
    elif isinstance(collection, list):
        identifiers = {
            identifier
            for item in collection
            if isinstance(item, dict)
            and isinstance(
                identifier := item.get("data_collection_id") or item.get("identifier"),
                str,
            )
        }
    else:
        return False
    return identifiers == set(required_fields)


def _provider_tools_omitted(agent: dict[str, Any]) -> bool:
    tool_ids = _dig(agent, ("conversation_config", "agent", "prompt", "tool_ids"))
    return tool_ids is None or tool_ids == []


def _conversation_initiation_enabled(agent: dict[str, Any]) -> bool | None:
    return _first_bool(
        agent,
        (
            (
                "platform_settings",
                "overrides",
                "enable_conversation_initiation_client_data_from_webhook",
            ),
        ),
    )


def _workspace_pre_call_configured(
    settings: dict[str, Any],
    *,
    expected_url: str | None,
) -> bool:
    webhook = _dig(settings, ("conversation_initiation_client_data_webhook",))
    if not isinstance(webhook, dict):
        return False
    url = webhook.get("url")
    request_headers = webhook.get("request_headers")
    if expected_url is None or url != expected_url or not expected_url.startswith("https://"):
        return False
    if not isinstance(request_headers, dict):
        return False
    secret_locator = next(
        (
            value
            for key, value in request_headers.items()
            if isinstance(key, str) and key.lower() == "x-veramove-precall-secret"
        ),
        None,
    )
    return (
        isinstance(secret_locator, dict)
        and isinstance(secret_locator.get("secret_id"), str)
        and bool(secret_locator["secret_id"].strip())
    )


def _post_call_events_configured(settings: dict[str, Any]) -> bool:
    webhooks = _dig(settings, ("webhooks",))
    if not isinstance(webhooks, dict):
        return False
    events = webhooks.get("events")
    return (
        isinstance(webhooks.get("post_call_webhook_id"), str)
        and bool(webhooks["post_call_webhook_id"].strip())
        and isinstance(events, list)
        and set(events) == {"transcript", "call_initiation_failure"}
        and webhooks.get("transcript_format") == "json"
        and webhooks.get("send_audio") is False
    )


def _post_call_webhook_enabled(
    workspace_webhooks: dict[str, Any],
    expected_webhook_id: str | None,
    *,
    expected_url: str | None,
) -> bool:
    webhooks = workspace_webhooks.get("webhooks")
    if (
        expected_webhook_id is None
        or expected_url is None
        or not isinstance(webhooks, list)
    ):
        return False
    for webhook in webhooks:
        if not isinstance(webhook, dict) or webhook.get("webhook_id") != expected_webhook_id:
            continue
        return (
            webhook.get("auth_type") == "hmac"
            and webhook.get("webhook_url") == expected_url
            and webhook.get("is_disabled") is False
            and webhook.get("is_auto_disabled") is False
        )
    return False


def _phone_assigned_to_agent(
    phone_number: dict[str, Any],
    *,
    expected_phone_number_id: str | None,
    expected_agent_id: str | None,
) -> bool:
    return (
        expected_phone_number_id is not None
        and expected_agent_id is not None
        and _first_string(phone_number, (("phone_number_id",),))
        == expected_phone_number_id
        and phone_number.get("provider") == "twilio"
        and _first_string(phone_number, (("assigned_agent", "agent_id"),))
        == expected_agent_id
    )


def _audio_saving_enabled(agent: dict[str, Any]) -> bool:
    value = _first_bool(
        agent,
        (
            ("audio_saving_enabled",),
            ("platform_settings", "privacy", "record_voice"),
            ("platform_settings", "privacy", "audio_saving_enabled"),
        ),
    )
    return value is True


def _retention_days(agent: dict[str, Any]) -> int:
    value = _first_int(
        agent,
        (
            ("retention_days",),
            ("platform_settings", "privacy", "retention_days"),
            ("platform_settings", "privacy", "audio_retention_days"),
        ),
    )
    return value or 0


def _remaining_count(
    body: dict[str, Any],
    *,
    remaining_paths: tuple[tuple[str, ...], ...],
    limit_paths: tuple[tuple[str, ...], ...],
    used_paths: tuple[tuple[str, ...], ...],
) -> int | None:
    remaining = _first_int(body, remaining_paths)
    if remaining is not None:
        return remaining
    limit = _first_int(body, limit_paths)
    used = _first_int(body, used_paths)
    if limit is None or used is None:
        return None
    return max(0, limit - used)


def _credits_available(subscription: dict[str, Any]) -> bool:
    remaining = _first_int(
        subscription,
        (("credits_remaining",), ("usage", "credits_remaining")),
    )
    if remaining is not None:
        return remaining > 0
    return (
        _remaining_count(
            subscription,
            remaining_paths=(("characters_remaining",),),
            limit_paths=(("character_limit",),),
            used_paths=(("character_count",),),
        )
        or 0
    ) > 0


def _local_agent_versions_match(expected: str | None) -> bool:
    if expected is None:
        return False
    versions: list[str] = []
    for path in (ROOT / "agents/intake/agent.yaml", ROOT / "agents/negotiator/agent.yaml"):
        match = _VERSION_PATTERN.search(path.read_text(encoding="utf-8"))
        if match is None:
            return False
        versions.append(match.group(1))
    return len(set(versions)) == 1 and versions[0] == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, redacted preflight for the supervised VeraMove three-call run."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Required safety flag; this command never places a call.",
    )
    args = parser.parse_args(argv)
    if not args.check_only:
        parser.error("--check-only is required; preflight never places calls")
    report = run_default_preflight(Settings.from_env(), check_only=True)
    print(json.dumps(report.to_safe_dict(), sort_keys=True))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
