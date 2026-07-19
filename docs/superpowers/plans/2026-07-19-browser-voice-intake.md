# Browser Voice Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace VeraMove's scripted Live Mode voice placeholder with a real, authenticated browser-microphone conversation that materializes the existing unconfirmed `JobSpecV1` and advances to confirmation.

**Architecture:** FastAPI reserves a durable intake session, mints one short-lived ElevenLabs WebRTC token through a server-only adapter, and attaches the SDK-returned conversation ID. A focused React controller uses `@elevenlabs/react` for media and transcript callbacks, then polls the existing intake-session contract until the signed post-call webhook atomically creates the canonical voice JobSpec. Demo Mode remains scripted, deterministic, and credential-free.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, pytest, Supabase/PostgreSQL, React 19, TypeScript 5.8, TanStack Query/Router, Vitest, Testing Library, `@elevenlabs/react@1.10.1`, npm.

## Global Constraints

- FastAPI-generated OpenAPI is the canonical public contract; never add handwritten frontend domain models.
- `APP_MODE=mock` and frontend Demo Mode must run without ElevenLabs credentials or Supabase.
- Real browser voice requires `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, enabled Supabase, and the reviewed browser-intake configuration subset.
- `ELEVENLABS_API_KEY` and agent IDs remain server-only; the browser receives only a short-lived conversation token and three correlation variables.
- The only allowed browser-to-provider traffic is the SDK's authenticated WebRTC media session. Browser code must not call ElevenLabs REST endpoints or supply prompt, voice, model, first-message, or agent-ID overrides.
- Post-call webhook materialization remains the only path that creates a voice `JobRecord`; it must be unconfirmed, unlocked, and `intake_source=voice`.
- Never store provider tokens, live transcript text, real names, phone numbers, addresses, or other real PII in repositories, logs, fixtures, browser storage, or analytics.
- Keep the current VeraMove interface and use fictional, clearly labeled role-play details for manual tests.
- Use npm and retain only `apps/web/package-lock.json` as the frontend lockfile.
- Every task uses TDD, passes its focused checks, and ends in a small commit.

---

## File Structure

### Backend

- `services/api/app/orchestration/intake_sessions.py` — owns credential-reservation state and legal intake-session transitions.
- `services/api/app/repositories/memory.py` — persists the reservation timestamp in credential-free tests.
- `services/api/app/repositories/supabase.py` — maps the reservation timestamp to the live table.
- `supabase/migrations/202607190005_browser_voice_intake.sql` — adds the nullable, non-secret reservation timestamp.
- `services/api/app/integrations/elevenlabs/tokens.py` — isolated server-side WebRTC token adapter and injectable transport.
- `services/api/app/core/config.py` — fail-closed browser-intake configuration guard that does not require outbound phone fields.
- `services/api/app/api/models.py` — typed token and conversation-attachment request/response models.
- `services/api/app/api/dependencies.py` — constructs the token adapter from the immutable application settings.
- `services/api/app/api/router.py` — exposes token issuance and conversation attachment without provider details.

### Frontend

- `apps/web/src/api/client.ts` — remains the only FastAPI HTTP client and exports generated intake types.
- `apps/web/src/lib/api/endpoints.ts` — exposes typed voice-intake operations to non-presentation code.
- `apps/web/src/lib/voice/useBrowserVoiceIntake.ts` — owns microphone permission, SDK callbacks, transcript memory, cleanup, and bounded polling.
- `apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx` — renders the real voice experience without raw HTTP calls.
- `apps/web/src/components/veramove/VoiceIntakePanel.tsx` — selects Live or scripted Demo behavior while preserving the current layout.
- `apps/web/src/routes/intake.tsx` — updates the stale capability note.

### Tests and documentation

- `services/api/tests/test_intake_sessions.py` — focused session-reservation tests.
- `services/api/tests/test_browser_voice_tokens.py` — token adapter tests.
- `services/api/tests/test_api.py` — public route, no-store, and fail-closed behavior.
- `services/api/tests/test_live_integrations_config.py` — browser-specific configuration requirements.
- `services/api/tests/test_supabase_repository.py` — live row round-trip coverage.
- `services/api/tests/test_openapi.py` — canonical route and schema coverage.
- `apps/web/src/lib/api/voice.test.ts` — centralized typed API request tests.
- `apps/web/src/lib/voice/useBrowserVoiceIntake.test.tsx` — mocked media/SDK lifecycle tests.
- `apps/web/src/components/veramove/LiveVoiceIntakePanel.test.tsx` — UI state and recovery tests.
- `apps/web/README.md` — browser voice local/live operation and manual smoke test.
- `agents/elevenlabs-dashboard-checklist.md` — authenticated client-session dashboard requirement.

---

### Task 1: Persist one browser credential reservation per intake session

**Files:**
- Create: `services/api/tests/test_intake_sessions.py`
- Create: `supabase/migrations/202607190005_browser_voice_intake.sql`
- Modify: `services/api/app/orchestration/intake_sessions.py`
- Modify: `services/api/app/orchestration/voice_materializer.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase.py`
- Modify: `services/api/tests/test_supabase_repository.py`
- Modify: `services/api/tests/test_async_voice_orchestration.py`

**Interfaces:**
- Consumes: existing `IntakeSessionService.create_web_session()` and repository session lookup.
- Produces: `IntakeSession.browser_credential_issued_at: datetime | None`, `IntakeSessionStore.reserve_intake_browser_credential(session_id: UUID, issued_at: datetime) -> IntakeSession`, and `IntakeSessionService.reserve_browser_credential(session_id: UUID | str) -> IntakeSession`.

- [ ] **Step 1: Write failing orchestration tests for the single-use reservation**

Create `services/api/tests/test_intake_sessions.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from services.api.app.core.errors import DomainConflict
from services.api.app.orchestration.intake_sessions import IntakeSessionService
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 19, 14, 0, tzinfo=UTC)


def make_service() -> IntakeSessionService:
    return IntakeSessionService(
        repository=InMemoryRepository(),
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-19.browser-v1",
        clock=lambda: NOW,
    )


def test_web_session_reserves_one_browser_credential_without_creating_job() -> None:
    service = make_service()
    created = service.create_web_session()

    reserved = service.reserve_browser_credential(created.intake_session_id)

    assert reserved.browser_credential_issued_at == NOW
    assert reserved.status.value == "pending"
    assert reserved.conversation_id is None
    assert service.repository.get(created.job_id) is None

    with pytest.raises(DomainConflict, match="already received"):
        service.reserve_browser_credential(created.intake_session_id)


def test_telephone_and_terminal_sessions_cannot_reserve_browser_credentials() -> None:
    service = make_service()
    telephone = service.create_pre_call_session(
        agent_id="agent_synthetic_intake",
        provider_call_key="CA_synthetic_phone_call",
    )
    with pytest.raises(DomainConflict, match="web intake"):
        service.reserve_browser_credential(telephone.intake_session_id)

    web = service.create_web_session()
    service.fail_session(web.intake_session_id, "synthetic_failure")
    with pytest.raises(DomainConflict, match="pending"):
        service.reserve_browser_credential(web.intake_session_id)


def test_reservation_timestamp_cannot_change_or_precede_session_creation() -> None:
    service = make_service()
    created = service.create_web_session()
    reserved = service.reserve_browser_credential(created.intake_session_id)

    changed = reserved.model_copy(
        update={"browser_credential_issued_at": NOW + timedelta(seconds=1)},
        deep=True,
    )
    with pytest.raises(DomainConflict, match="credential reservation"):
        service.repository.save_intake_session(changed)
```

- [ ] **Step 2: Run the orchestration tests and confirm the new contract is missing**

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_intake_sessions.py -v
```

Expected: FAIL because `reserve_browser_credential` and `browser_credential_issued_at` do not exist.

- [ ] **Step 3: Add the reservation field, invariants, and service operation**

In `IntakeSession`, add:

```python
browser_credential_issued_at: datetime | None = None
```

Include it in the timezone-aware validator:

```python
@field_validator(
    "created_at",
    "updated_at",
    "completed_at",
    "browser_credential_issued_at",
)
```

Add these model and update invariants:

```python
if (
    self.browser_credential_issued_at is not None
    and self.browser_credential_issued_at < self.created_at
):
    raise ValueError("browser credential reservation cannot precede session creation")
if self.browser_credential_issued_at is not None and self.provider_call_key_hash is not None:
    raise ValueError("telephone intake sessions cannot reserve browser credentials")
```

```python
if (
    current.browser_credential_issued_at is not None
    and candidate.browser_credential_issued_at != current.browser_credential_issued_at
):
    raise DomainConflict("Intake session credential reservation cannot be changed")
```

Add this atomic method to `IntakeSessionStore` and `IntakeSessionRepository`:

```python
def reserve_intake_browser_credential(
    self,
    session_id: UUID,
    issued_at: datetime,
) -> IntakeSession: ...
```

Implement it in `InMemoryRepository` under the existing lock:

```python
# Add IntakeSessionStatus to the existing intake_sessions import.
def reserve_intake_browser_credential(
    self,
    session_id: UUID,
    issued_at: datetime,
) -> IntakeSession:
    with self._lock:
        payload = self._intake_sessions.get(session_id)
        if payload is None:
            raise ResourceNotFound(f"Intake session {session_id} was not found")
        current = IntakeSession.model_validate(deepcopy(payload))
        if current.provider_call_key_hash is not None:
            raise DomainConflict("Browser credentials require a web intake session")
        if current.status is not IntakeSessionStatus.PENDING:
            raise DomainConflict("Browser credentials require a pending intake session")
        if current.browser_credential_issued_at is not None:
            raise DomainConflict("Intake session already received a browser credential")
        candidate = current.model_copy(
            update={
                "browser_credential_issued_at": issued_at,
                "updated_at": issued_at,
            },
            deep=True,
        )
        validate_intake_session_update(current, candidate)
        self._intake_sessions[session_id] = deepcopy(candidate.model_dump(mode="json"))
    return self._copy_intake_session(candidate)
```

Add this method to `IntakeSessionService`:

```python
def reserve_browser_credential(self, session_id: UUID | str) -> IntakeSession:
    session = self._require_session(UUID(str(session_id)))
    return self.repository.reserve_intake_browser_credential(
        session.intake_session_id,
        self.clock(),
    )
```

Delegate the expanded store protocol from `_IntakeStore` in `services/api/app/orchestration/voice_materializer.py`:

```python
def reserve_intake_browser_credential(
    self,
    session_id: UUID,
    issued_at: datetime,
) -> IntakeSession:
    return self._sessions.reserve_intake_browser_credential(session_id, issued_at)
```

- [ ] **Step 4: Add the Supabase column and repository mapping**

Create `supabase/migrations/202607190005_browser_voice_intake.sql`:

```sql
alter table public.intake_sessions
    add column if not exists browser_credential_issued_at timestamptz;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'intake_sessions_browser_credential_shape_check'
          and conrelid = 'public.intake_sessions'::regclass
    ) then
        alter table public.intake_sessions
            add constraint intake_sessions_browser_credential_shape_check
            check (
                browser_credential_issued_at is null
                or (
                    provider_call_key_hash is null
                    and browser_credential_issued_at >= created_at
                )
            );
    end if;
end
$$;

create or replace function public.veramove_reserve_browser_voice_credential(
    p_session_id uuid,
    p_issued_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    reserved intake_sessions%rowtype;
begin
    if p_session_id is null or p_issued_at is null then
        raise exception 'invalid browser credential reservation';
    end if;
    update intake_sessions
    set browser_credential_issued_at = p_issued_at,
        updated_at = p_issued_at
    where id = p_session_id
      and status = 'pending'
      and provider_call_key_hash is null
      and browser_credential_issued_at is null
      and p_issued_at >= created_at
    returning * into reserved;
    if not found then
        raise exception 'browser credential reservation conflict';
    end if;
    return to_jsonb(reserved);
end
$$;

revoke all on function public.veramove_reserve_browser_voice_credential(uuid, timestamptz)
    from public, anon, authenticated;
grant execute on function public.veramove_reserve_browser_voice_credential(uuid, timestamptz)
    to service_role;
```

Add to `_intake_session_row`:

```python
"browser_credential_issued_at": (
    session.browser_credential_issued_at.isoformat()
    if session.browser_credential_issued_at is not None
    else None
),
```

Add to `_intake_session_from_row`:

```python
"browser_credential_issued_at": row.get("browser_credential_issued_at"),
```

Implement the Supabase repository operation through the atomic RPC:

```python
def reserve_intake_browser_credential(
    self,
    session_id: UUID,
    issued_at: datetime,
) -> IntakeSession:
    payload = self._client.rpc(
        "veramove_reserve_browser_voice_credential",
        {
            "p_session_id": str(session_id),
            "p_issued_at": issued_at.isoformat(),
        },
    )
    if not isinstance(payload, dict):
        raise ProviderRequestError("Supabase returned an invalid intake reservation")
    return self._intake_session_from_row(payload)
```

Extend the intake-session round-trip test in `services/api/tests/test_supabase_repository.py` by creating a session with `browser_credential_issued_at=FIXED_NOW` and asserting:

```python
assert stored.browser_credential_issued_at == FIXED_NOW
assert table_client.tables["intake_sessions"][str(session.intake_session_id)][
    "browser_credential_issued_at"
] == FIXED_NOW.isoformat()
```

Add an RPC mapping test using the existing fake client:

```python
def test_supabase_reserves_browser_credential_through_atomic_rpc(
    repository,
    table_client,
) -> None:
    session = IntakeSession(
        expected_agent_id="agent_synthetic_intake",
        agent_config_version="2026-07-19.browser-v1",
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    row = repository._intake_session_row(
        session.model_copy(
            update={"browser_credential_issued_at": FIXED_NOW},
            deep=True,
        )
    )
    table_client.rpc_responses["veramove_reserve_browser_voice_credential"] = row

    reserved = repository.reserve_intake_browser_credential(
        session.intake_session_id,
        FIXED_NOW,
    )

    assert reserved.browser_credential_issued_at == FIXED_NOW
    assert table_client.operations[-1] == (
        "rpc",
        "veramove_reserve_browser_voice_credential",
        {
            "p_session_id": str(session.intake_session_id),
            "p_issued_at": FIXED_NOW.isoformat(),
        },
    )
```

- [ ] **Step 5: Run the focused repository and orchestration tests**

In `test_signed_intake_completion_creates_one_unconfirmed_voice_job` in `services/api/tests/test_async_voice_orchestration.py`, reserve the browser credential before attaching the conversation:

```python
session_view = sessions.create_web_session()
reserved = sessions.reserve_browser_credential(session_view.intake_session_id)
assert reserved.browser_credential_issued_at == NOW
conversation_id = "conv_synthetic_intake_1"
```

Keep the existing assertions that the signed webhook is idempotent, creates exactly one unconfirmed `IntakeSource.VOICE` JobSpec, and does not persist the transcript.

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_intake_sessions.py services/api/tests/test_supabase_repository.py services/api/tests/test_async_voice_orchestration.py -v
```

Expected: PASS, with one reservation timestamp persisted and no provider token stored.

- [ ] **Step 6: Commit the durable reservation boundary**

```bash
git add services/api/app/orchestration/intake_sessions.py services/api/app/orchestration/voice_materializer.py services/api/app/repositories/memory.py services/api/app/repositories/supabase.py services/api/tests/test_intake_sessions.py services/api/tests/test_supabase_repository.py services/api/tests/test_async_voice_orchestration.py supabase/migrations/202607190005_browser_voice_intake.sql
git commit -m "feat: reserve browser voice intake credentials"
```

---

### Task 2: Add the fail-closed ElevenLabs WebRTC token adapter

**Files:**
- Create: `services/api/app/integrations/elevenlabs/tokens.py`
- Create: `services/api/tests/test_browser_voice_tokens.py`
- Modify: `services/api/app/core/config.py`
- Modify: `services/api/tests/test_live_integrations_config.py`

**Interfaces:**
- Consumes: `ConversationHttpTransport.get_json(url, headers, timeout_seconds)` and `LiveVoiceConfig`.
- Produces: `BrowserVoiceTokenIssuer.issue_token() -> str`, `ElevenLabsBrowserVoiceTokenClient`, and `Settings.require_browser_voice_config() -> LiveVoiceConfig`.

- [ ] **Step 1: Write failing adapter and configuration tests**

Create `services/api/tests/test_browser_voice_tokens.py`:

```python
from typing import Any

import pytest

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.tokens import ElevenLabsBrowserVoiceTokenClient


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str], float]] = []

    def get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.requests.append((url, headers, timeout_seconds))
        return self.response

    def get_bytes(self, url, headers, timeout_seconds):
        raise AssertionError("browser token issuance never fetches audio")


def test_issues_encoded_agent_token_without_exposing_key_in_url() -> None:
    transport = RecordingTransport({"token": "synthetic-ephemeral-token"})
    client = ElevenLabsBrowserVoiceTokenClient(
        api_key="synthetic-server-key",
        agent_id="agent_synthetic/intake",
        transport=transport,
    )

    assert client.issue_token() == "synthetic-ephemeral-token"
    assert transport.requests == [
        (
            "https://api.elevenlabs.io/v1/convai/conversation/token?agent_id=agent_synthetic%2Fintake",
            {"xi-api-key": "synthetic-server-key"},
            10.0,
        )
    ]
    assert "synthetic-server-key" not in transport.requests[0][0]


@pytest.mark.parametrize("payload", ({}, {"token": ""}, {"token": 7}))
def test_rejects_missing_or_malformed_provider_token(payload) -> None:
    client = ElevenLabsBrowserVoiceTokenClient(
        api_key="synthetic-server-key",
        agent_id="agent_synthetic_intake",
        transport=RecordingTransport(payload),
    )

    with pytest.raises(ProviderRequestError, match="invalid browser voice token"):
        client.issue_token()
```

Append to `services/api/tests/test_live_integrations_config.py`:

```python
def test_browser_voice_requires_only_intake_configuration_and_durable_storage() -> None:
    settings = Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-elevenlabs-key",
            intake_agent_id="synthetic-intake-agent",
            webhook_secret="w" * 32,
            agent_config_version="2026-07-19.browser-v1",
            live_calls_enabled=True,
        ),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )

    assert settings.require_browser_voice_config().intake_agent_id == (
        "synthetic-intake-agent"
    )


@pytest.mark.parametrize(
    "settings",
    (
        Settings(),
        Settings(app_mode="live", live_voice=LiveVoiceConfig(live_calls_enabled=False)),
        Settings(
            app_mode="live",
            live_voice=LiveVoiceConfig(live_calls_enabled=True),
            supabase=SupabaseConfig(enabled=True),
        ),
    ),
)
def test_browser_voice_configuration_fails_closed(settings) -> None:
    with pytest.raises(ProviderConfigurationError):
        settings.require_browser_voice_config()
```

- [ ] **Step 2: Run the focused tests and confirm the adapter/guard are absent**

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_browser_voice_tokens.py services/api/tests/test_live_integrations_config.py -v
```

Expected: FAIL on the missing `tokens` module and `require_browser_voice_config` method.

- [ ] **Step 3: Implement the injectable token adapter**

Create `services/api/app/integrations/elevenlabs/tokens.py`:

```python
"""Issue short-lived ElevenLabs WebRTC tokens without exposing provider credentials."""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlencode

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.base import ConversationHttpTransport
from services.api.app.integrations.elevenlabs.conversations import HttpxConversationTransport


class BrowserVoiceTokenIssuer(Protocol):
    def issue_token(self) -> str: ...


class ElevenLabsBrowserVoiceTokenClient:
    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        api_base_url: str = "https://api.elevenlabs.io",
        transport: ConversationHttpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._agent_id = agent_id
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxConversationTransport()

    def issue_token(self) -> str:
        query = urlencode({"agent_id": self._agent_id})
        payload = self._transport.get_json(
            f"{self._api_base_url}/v1/convai/conversation/token?{query}",
            {"xi-api-key": self._api_key},
            10.0,
        )
        token = payload.get("token")
        if not isinstance(token, str) or not token.strip() or len(token) > 8_192:
            raise ProviderRequestError("ElevenLabs returned an invalid browser voice token")
        return token.strip()
```

- [ ] **Step 4: Implement the browser-specific live configuration guard**

Add to `Settings` in `services/api/app/core/config.py`:

```python
def require_browser_voice_config(self) -> LiveVoiceConfig:
    if self.app_mode != "live":
        raise ProviderConfigurationError("Browser voice requires APP_MODE=live")
    config = self.live_voice
    if not config.live_calls_enabled:
        raise ProviderConfigurationError("Browser voice requires LIVE_CALLS_ENABLED=true")
    self.require_supabase_config()
    required = {
        "ELEVENLABS_API_KEY": config.api_key,
        "ELEVENLABS_INTAKE_AGENT_ID": config.intake_agent_id,
        "AGENT_CONFIG_VERSION": config.agent_config_version,
    }
    missing = [name for name, value in required.items() if value is None or not value.strip()]
    if missing:
        raise ProviderConfigurationError(
            f"Missing browser voice configuration: {', '.join(missing)}"
        )
    if not _secret_is_strong(config.webhook_secret):
        raise ProviderConfigurationError(
            "ELEVENLABS_WEBHOOK_SECRET must be at least "
            f"{MIN_LIVE_SECRET_BYTES} bytes"
        )
    return config
```

This method deliberately does not require `ELEVENLABS_OUTBOUND_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID`, `LIVE_TEST_TO_NUMBERS`, pre-call secret, or recording-proxy settings.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_browser_voice_tokens.py services/api/tests/test_live_integrations_config.py -v
```

Expected: PASS; request capture contains only the server header and encoded configured Intake Agent ID.

- [ ] **Step 6: Commit the provider boundary**

```bash
git add services/api/app/integrations/elevenlabs/tokens.py services/api/app/core/config.py services/api/tests/test_browser_voice_tokens.py services/api/tests/test_live_integrations_config.py
git commit -m "feat: issue secure browser voice tokens"
```

---

### Task 3: Expose typed token and conversation-correlation routes

**Files:**
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/tests/test_api.py`
- Modify: `services/api/tests/test_openapi.py`
- Modify: `packages/contracts/openapi.json`
- Modify: `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: `IntakeSessionService.reserve_browser_credential`, `IntakeSessionService.attach_conversation`, and `BrowserVoiceTokenIssuer.issue_token`.
- Produces: `POST /api/intake/sessions/{session_id}/voice-token`, `POST /api/intake/sessions/{session_id}/conversation`, `BrowserVoiceTokenResponse`, and `AttachIntakeConversationRequest`.

- [ ] **Step 1: Write failing public API tests**

Update imports in `services/api/tests/test_api.py`:

```python
from services.api.app.api.dependencies import (
    get_browser_voice_token_issuer,
    get_live_voice_operator_service,
    get_service,
)
from services.api.app.core.config import LiveVoiceConfig, Settings, SupabaseConfig
from services.api.app.core.errors import ProviderRequestError
```

Add:

```python
class StaticBrowserTokenIssuer:
    def __init__(self, token: str = "synthetic-ephemeral-token") -> None:
        self.token = token
        self.calls = 0

    def issue_token(self) -> str:
        self.calls += 1
        return self.token


def browser_voice_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-elevenlabs-key",
            intake_agent_id="synthetic-intake-agent",
            webhook_secret="w" * 32,
            agent_config_version="2026-07-19.browser-v1",
            live_calls_enabled=True,
        ),
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        ),
    )


def test_browser_voice_token_and_conversation_routes_are_correlated_and_no_store() -> None:
    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    issuer = StaticBrowserTokenIssuer()
    application.dependency_overrides[get_browser_voice_token_issuer] = lambda: issuer

    with TestClient(application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        issued = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
        attached = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/conversation",
            json={"conversation_id": "conv_synthetic_browser"},
        )

    assert issued.status_code == 200
    assert issued.headers["cache-control"] == "no-store"
    assert issued.json() == {
        "conversation_token": "synthetic-ephemeral-token",
        "dynamic_variables": {
            "job_id": session["job_id"],
            "intake_session_id": session["intake_session_id"],
            "agent_config_version": "2026-07-19.browser-v1",
        },
    }
    assert "synthetic-elevenlabs-key" not in issued.text
    assert "synthetic-intake-agent" not in issued.text
    assert issuer.calls == 1
    assert attached.status_code == 200
    assert attached.json()["status"] == "in_progress"
    assert attached.json()["conversation_id"] == "conv_synthetic_browser"


def test_browser_voice_token_is_single_use_and_mock_mode_is_rejected() -> None:
    mock_application = create_app(Settings())
    with TestClient(mock_application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        rejected = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "provider_configuration_error"

    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    issuer = StaticBrowserTokenIssuer()
    application.dependency_overrides[get_browser_voice_token_issuer] = lambda: issuer
    with TestClient(application) as test_client:
        unknown = test_client.post(f"/api/intake/sessions/{uuid4()}/voice-token")
        session = test_client.post("/api/intake/sessions").json()
        path = f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        assert test_client.post(path).status_code == 200
        replay = test_client.post(path)
        attached_path = (
            f"/api/intake/sessions/{session['intake_session_id']}/conversation"
        )
        first_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_browser"},
        )
        same_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_browser"},
        )
        changed_attach = test_client.post(
            attached_path,
            json={"conversation_id": "conv_synthetic_other"},
        )
    assert unknown.status_code == 404
    assert replay.status_code == 409
    assert issuer.calls == 1
    assert first_attach.status_code == 200
    assert same_attach.status_code == 200
    assert changed_attach.status_code == 409


def test_provider_failure_marks_reserved_session_failed_without_returning_token() -> None:
    class FailingIssuer:
        def issue_token(self) -> str:
            raise ProviderRequestError("synthetic safe provider failure")

    application = create_app(Settings())
    application.state.settings = browser_voice_settings()
    application.dependency_overrides[get_browser_voice_token_issuer] = FailingIssuer
    with TestClient(application) as test_client:
        session = test_client.post("/api/intake/sessions").json()
        issued = test_client.post(
            f"/api/intake/sessions/{session['intake_session_id']}/voice-token"
        )
        stored = test_client.get(
            f"/api/intake/sessions/{session['intake_session_id']}"
        )
    assert issued.status_code == 502
    assert stored.json()["status"] == "failed"
    assert "token" not in stored.text
```

- [ ] **Step 2: Run the route tests and verify both endpoints return 404**

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_api.py -k "browser_voice" -v
```

Expected: FAIL because neither route nor dependency exists.

- [ ] **Step 3: Add route-local request and response models**

Add to `services/api/app/api/models.py`:

```python
class AttachIntakeConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class BrowserVoiceTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_token: str = Field(min_length=1, max_length=8_192, repr=False)
    dynamic_variables: IntakeDynamicVariables
```

- [ ] **Step 4: Wire the server-only token issuer dependency**

Add to `services/api/app/api/dependencies.py`:

```python
from services.api.app.integrations.elevenlabs.tokens import (
    BrowserVoiceTokenIssuer,
    ElevenLabsBrowserVoiceTokenClient,
)


def get_browser_voice_token_issuer(request: Request) -> BrowserVoiceTokenIssuer:
    config = request.app.state.settings.require_browser_voice_config()
    assert config.api_key is not None
    assert config.intake_agent_id is not None
    return ElevenLabsBrowserVoiceTokenClient(
        api_key=config.api_key,
        agent_id=config.intake_agent_id,
        api_base_url=config.api_base_url,
    )
```

- [ ] **Step 5: Add both FastAPI routes and safe failure handling**

Update `services/api/app/api/router.py` imports and aliases:

```python
from services.api.app.api.dependencies import get_browser_voice_token_issuer
from services.api.app.api.models import (
    AttachIntakeConversationRequest,
    BrowserVoiceTokenResponse,
)
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.tokens import BrowserVoiceTokenIssuer

BrowserVoiceTokens = Annotated[
    BrowserVoiceTokenIssuer,
    Depends(get_browser_voice_token_issuer),
]
```

Add below the existing intake-session routes:

```python
@router.post(
    "/api/intake/sessions/{session_id}/voice-token",
    response_model=BrowserVoiceTokenResponse,
    tags=["intake"],
)
def issue_browser_voice_token(
    session_id: UUID,
    response: Response,
    sessions: IntakeSessions,
    token_issuer: BrowserVoiceTokens,
) -> BrowserVoiceTokenResponse:
    session = sessions.reserve_browser_credential(session_id)
    try:
        token = token_issuer.issue_token()
    except ProviderRequestError:
        sessions.fail_session(session_id, "browser_token_issue_failed")
        raise
    response.headers["Cache-Control"] = "no-store"
    return BrowserVoiceTokenResponse(
        conversation_token=token,
        dynamic_variables=IntakeDynamicVariables(
            job_id=session.job_id,
            intake_session_id=session.intake_session_id,
            agent_config_version=session.agent_config_version,
        ),
    )


@router.post(
    "/api/intake/sessions/{session_id}/conversation",
    response_model=IntakeSessionResponse,
    tags=["intake"],
)
def attach_browser_voice_conversation(
    session_id: UUID,
    request: AttachIntakeConversationRequest,
    sessions: IntakeSessions,
) -> IntakeSessionResponse:
    attached = sessions.attach_conversation(
        session_id,
        request.conversation_id,
        agent_id=sessions.expected_agent_id,
    )
    return IntakeSessionResponse.model_validate(sessions.get_session(session_id).model_dump())
```

- [ ] **Step 6: Run API tests and add OpenAPI assertions**

Run:

```bash
.venv/bin/python -m pytest services/api/tests/test_api.py -k "browser_voice" -v
```

Expected: PASS.

Add both paths to the route tuple in `services/api/tests/test_openapi.py`:

```python
"/api/intake/sessions/{session_id}/voice-token",
"/api/intake/sessions/{session_id}/conversation",
```

Add schemas:

```python
"AttachIntakeConversationRequest",
"BrowserVoiceTokenResponse",
```

- [ ] **Step 7: Regenerate the canonical contract and frontend types**

Run:

```bash
.venv/bin/python scripts/export_openapi.py
npm --prefix apps/web run generate:api
.venv/bin/python -m pytest services/api/tests/test_openapi.py -v
```

Expected: OpenAPI export reports `packages/contracts/openapi.json`, type generation updates `apps/web/src/api/schema.d.ts`, and the test passes.

- [ ] **Step 8: Commit the API contract**

```bash
git add services/api/app/api/models.py services/api/app/api/dependencies.py services/api/app/api/router.py services/api/tests/test_api.py services/api/tests/test_openapi.py packages/contracts/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat: expose browser voice intake sessions"
```

---

### Task 4: Add the generated frontend voice API client and pinned SDK

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Create: `apps/web/src/lib/api/voice.test.ts`

**Interfaces:**
- Consumes: generated `BrowserVoiceTokenResponse`, `AttachIntakeConversationRequest`, `IntakeSessionResponse`, and `IntegrationStatusSnapshot`.
- Produces: `apiClient.createIntakeSession`, `issueBrowserVoiceToken`, `attachIntakeConversation`, `getIntakeSession`, `integrationStatus`, plus matching endpoint functions.

- [ ] **Step 1: Install the exact browser SDK and frontend test tools**

Run:

```bash
npm --prefix apps/web install @elevenlabs/react@1.10.1
npm --prefix apps/web install --save-dev @testing-library/react@16.3.2 @testing-library/user-event@14.6.1 jsdom@29.1.1
```

Expected: only `apps/web/package.json` and `apps/web/package-lock.json` change; no additional lockfile appears.

- [ ] **Step 2: Write a failing centralized-client request test**

Create `apps/web/src/lib/api/voice.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/api/client";

const session = {
  intake_session_id: "00000000-0000-0000-0000-000000000001",
  job_id: "00000000-0000-0000-0000-000000000002",
  status: "pending" as const,
  conversation_id: null,
  job_spec: null,
};

describe("browser voice API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses only the centralized FastAPI client for the session lifecycle", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 201 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_token: "synthetic-token",
            dynamic_variables: {
              job_id: session.job_id,
              intake_session_id: session.intake_session_id,
              agent_config_version: "2026-07-19.browser-v1",
            },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...session,
            status: "in_progress",
            conversation_id: "conv_synthetic_browser",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiClient.createIntakeSession();
    await apiClient.issueBrowserVoiceToken(session.intake_session_id);
    await apiClient.attachIntakeConversation(
      session.intake_session_id,
      "conv_synthetic_browser",
    );
    await apiClient.getIntakeSession(session.intake_session_id);

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method])).toEqual([
      [expect.stringContaining("/api/intake/sessions"), "POST"],
      [expect.stringContaining("/voice-token"), "POST"],
      [expect.stringContaining("/conversation"), "POST"],
      [expect.stringContaining(`/api/intake/sessions/${session.intake_session_id}`), undefined],
    ]);
  });
});
```

- [ ] **Step 3: Run the client test and verify methods are missing**

Run:

```bash
npm --prefix apps/web test -- src/lib/api/voice.test.ts
```

Expected: FAIL with missing `apiClient` methods.

- [ ] **Step 4: Add generated type exports and centralized methods**

Add to `apps/web/src/api/client.ts` type exports:

```typescript
export type IntakeSessionResponse = Schemas["IntakeSessionResponse"];
export type BrowserVoiceTokenResponse = Schemas["BrowserVoiceTokenResponse"];
export type AttachIntakeConversationRequest = Schemas["AttachIntakeConversationRequest"];
export type IntegrationStatusSnapshot = Schemas["IntegrationStatusSnapshot"];
```

Add to `apiClient`:

```typescript
integrationStatus: () =>
  apiFetch<IntegrationStatusSnapshot>("/api/integrations/status"),
createIntakeSession: () =>
  apiFetch<IntakeSessionResponse>("/api/intake/sessions", { method: "POST" }),
issueBrowserVoiceToken: (sessionId: string) =>
  apiFetch<BrowserVoiceTokenResponse>(
    `/api/intake/sessions/${sessionId}/voice-token`,
    { method: "POST" },
  ),
attachIntakeConversation: (sessionId: string, conversationId: string) =>
  apiFetch<IntakeSessionResponse>(
    `/api/intake/sessions/${sessionId}/conversation`,
    {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId }),
    },
  ),
getIntakeSession: (sessionId: string) =>
  apiFetch<IntakeSessionResponse>(`/api/intake/sessions/${sessionId}`),
```

Expose direct typed aliases in `apps/web/src/lib/api/endpoints.ts`:

```typescript
export const getIntegrationStatus = apiClient.integrationStatus;
export const createIntakeSession = apiClient.createIntakeSession;
export const issueBrowserVoiceToken = apiClient.issueBrowserVoiceToken;
export const attachIntakeConversation = apiClient.attachIntakeConversation;
export const getIntakeSession = apiClient.getIntakeSession;
```

- [ ] **Step 5: Run frontend client tests and typecheck**

Run:

```bash
npm --prefix apps/web test -- src/lib/api/voice.test.ts
npm --prefix apps/web run typecheck
```

Expected: PASS.

- [ ] **Step 6: Verify package-manager normalization and commit**

Run:

```bash
find apps/web -maxdepth 1 -type f -name '*lock*' -print
```

Expected: only `apps/web/package-lock.json`.

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/src/api/client.ts apps/web/src/lib/api/endpoints.ts apps/web/src/lib/api/voice.test.ts
git commit -m "feat: add typed browser voice client"
```

---

### Task 5: Build the browser voice lifecycle controller

**Files:**
- Create: `apps/web/src/lib/voice/useBrowserVoiceIntake.ts`
- Create: `apps/web/src/lib/voice/useBrowserVoiceIntake.test.tsx`

**Interfaces:**
- Consumes: typed functions from `@/lib/api/endpoints` and `useConversation` from `@elevenlabs/react`.
- Produces: `useBrowserVoiceIntake(): BrowserVoiceIntakeController`, with `phase`, `mode`, `turns`, `jobSpec`, `error`, `start`, `end`, and `retryStatus`.

- [ ] **Step 1: Write a failing mocked browser-media lifecycle test**

Create `apps/web/src/lib/voice/useBrowserVoiceIntake.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UseConversationOptions } from "@elevenlabs/react";
import { useBrowserVoiceIntake } from "./useBrowserVoiceIntake";
import * as voiceApi from "@/lib/api/endpoints";

const sdk = vi.hoisted(() => ({
  options: undefined as UseConversationOptions | undefined,
  startSession: vi.fn(),
  endSession: vi.fn(),
}));

vi.mock("@elevenlabs/react", async () => {
  const actual = await vi.importActual<typeof import("@elevenlabs/react")>(
    "@elevenlabs/react",
  );
  return {
    ...actual,
    useConversation: (options: UseConversationOptions) => {
      sdk.options = options;
      return {
        startSession: sdk.startSession,
        endSession: sdk.endSession,
        status: "disconnected",
        mode: "listening",
      };
    },
  };
});

vi.mock("@/lib/api/endpoints", () => ({
  getIntegrationStatus: vi.fn(),
  createIntakeSession: vi.fn(),
  issueBrowserVoiceToken: vi.fn(),
  attachIntakeConversation: vi.fn(),
  getIntakeSession: vi.fn(),
}));

const session = {
  intake_session_id: "00000000-0000-0000-0000-000000000001",
  job_id: "00000000-0000-0000-0000-000000000002",
  status: "pending" as const,
  conversation_id: null,
  job_spec: null,
};

describe("useBrowserVoiceIntake", () => {
  const stopTrack = vi.fn();
  const getUserMedia = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sdk.options = undefined;
    vi.mocked(voiceApi.getIntegrationStatus).mockResolvedValue({
      openai: { enabled: true, configured: true, usage: [] },
      tavily: { enabled: true, configured: true },
      supabase: { enabled: true, configured: true },
      live_voice: { enabled: true, configured: true },
    });
    vi.mocked(voiceApi.createIntakeSession).mockResolvedValue(session);
    vi.mocked(voiceApi.issueBrowserVoiceToken).mockResolvedValue({
      conversation_token: "synthetic-token",
      dynamic_variables: {
        job_id: session.job_id,
        intake_session_id: session.intake_session_id,
        agent_config_version: "2026-07-19.browser-v1",
      },
    });
    vi.mocked(voiceApi.attachIntakeConversation).mockResolvedValue({
      ...session,
      status: "in_progress",
      conversation_id: "conv_synthetic_browser",
    });
    getUserMedia.mockResolvedValue({
      getTracks: () => [{ stop: stopTrack }],
    });
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia,
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("checks capability before microphone, starts WebRTC, attaches, and renders turns", async () => {
    const { result } = renderHook(() => useBrowserVoiceIntake());

    await act(async () => result.current.start());

    expect(
      vi.mocked(voiceApi.getIntegrationStatus).mock.invocationCallOrder[0],
    ).toBeLessThan(getUserMedia.mock.invocationCallOrder[0]);
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(sdk.startSession).toHaveBeenCalledWith({
      conversationToken: "synthetic-token",
      connectionType: "webrtc",
      dynamicVariables: {
        job_id: session.job_id,
        intake_session_id: session.intake_session_id,
        agent_config_version: "2026-07-19.browser-v1",
      },
    });

    await act(async () => {
      sdk.options?.onConnect?.({ conversationId: "conv_synthetic_browser" });
    });
    await waitFor(() =>
      expect(voiceApi.attachIntakeConversation).toHaveBeenCalledWith(
        session.intake_session_id,
        "conv_synthetic_browser",
      ),
    );

    act(() => {
      sdk.options?.onMessage?.({
        event_id: 1,
        message: "What date is your fictional move?",
        role: "agent",
        source: "ai",
      });
      sdk.options?.onMessage?.({
        event_id: 2,
        message: "August fifteenth.",
        role: "user",
        source: "user",
      });
    });
    expect(result.current.turns.map((turn) => turn.speaker)).toEqual(["agent", "you"]);
  });

  it("fails before requesting microphone when live voice is unavailable", async () => {
    vi.mocked(voiceApi.getIntegrationStatus).mockResolvedValue({
      openai: { enabled: true, configured: true, usage: [] },
      tavily: { enabled: true, configured: true },
      supabase: { enabled: true, configured: true },
      live_voice: { enabled: false, configured: false },
    });
    const { result } = renderHook(() => useBrowserVoiceIntake());

    await act(async () => result.current.start());

    expect(getUserMedia).not.toHaveBeenCalled();
    expect(voiceApi.createIntakeSession).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("failed");
    expect(result.current.error).toMatch(/not available/i);
  });

  it("maps microphone denial to safe retry guidance", async () => {
    getUserMedia.mockRejectedValue(
      new DOMException("Synthetic permission denial", "NotAllowedError"),
    );
    const { result } = renderHook(() => useBrowserVoiceIntake());

    await act(async () => result.current.start());

    expect(voiceApi.createIntakeSession).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("failed");
    expect(result.current.error).toMatch(/microphone permission/i);
  });

  it("polls a disconnected session to completion and never persists transcript", async () => {
    vi.useFakeTimers();
    const completed = {
      ...session,
      status: "completed" as const,
      conversation_id: "conv_synthetic_browser",
      job_spec: {
        version: "1.0" as const,
        job_id: session.job_id,
        intake_source: "voice" as const,
        origin: { address_summary: "Fictional Rock Hill, SC" },
        destination: { address_summary: "Fictional Charlotte, NC" },
        inventory: [],
        oversized_or_fragile_items: [],
        services: {},
        source_context: {},
        confirmed: false,
        confirmed_at: null,
        locked_version: null,
        data_classification: "role_play" as const,
      },
    };
    vi.mocked(voiceApi.getIntakeSession).mockResolvedValue(completed);
    const { result } = renderHook(() => useBrowserVoiceIntake());
    await act(async () => result.current.start());

    act(() => sdk.options?.onDisconnect?.({ reason: "agent" }));
    await act(async () => vi.runOnlyPendingTimersAsync());

    expect(result.current.phase).toBe("completed");
    expect(result.current.jobSpec?.confirmed).toBe(false);
    expect(localStorage.length).toBe(0);
  });
});
```

- [ ] **Step 2: Run the hook test and confirm the controller is absent**

Run:

```bash
npm --prefix apps/web test -- src/lib/voice/useBrowserVoiceIntake.test.tsx
```

Expected: FAIL because `useBrowserVoiceIntake.ts` does not exist.

- [ ] **Step 3: Implement the focused controller**

Create `apps/web/src/lib/voice/useBrowserVoiceIntake.ts` with these public types and constants:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import type { JobSpecV1 } from "@/api/client";
import * as voiceApi from "@/lib/api/endpoints";

export type BrowserVoicePhase =
  | "ready"
  | "requesting_microphone"
  | "connecting"
  | "connected"
  | "processing"
  | "delayed"
  | "completed"
  | "failed";

export interface VoiceTurn {
  id: string;
  speaker: "agent" | "you";
  text: string;
}

export interface BrowserVoiceIntakeController {
  phase: BrowserVoicePhase;
  mode: "speaking" | "listening";
  turns: VoiceTurn[];
  jobSpec: JobSpecV1 | null;
  error: string | null;
  start: () => Promise<void>;
  end: () => void;
  retryStatus: () => Promise<void>;
}

const POLL_INTERVAL_MS = 1_500;
const MAX_POLLS = 40;
```

Implement the hook with refs for `sessionId`, poll count, timer, mounted state, and seen message IDs. The callback behavior must be exactly:

```typescript
export function useBrowserVoiceIntake(): BrowserVoiceIntakeController {
  const [phase, setPhase] = useState<BrowserVoicePhase>("ready");
  const [mode, setMode] = useState<"speaking" | "listening">("listening");
  const [turns, setTurns] = useState<VoiceTurn[]>([]);
  const [jobSpec, setJobSpec] = useState<JobSpecV1 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string | null>(null);
  const pollCount = useRef(0);
  const pollTimer = useRef<number | null>(null);
  const mounted = useRef(true);
  const seenMessages = useRef(new Set<string>());
  const endSessionRef = useRef<() => void>(() => undefined);
  const failedRef = useRef(false);

  const fail = useCallback((message: string) => {
    if (!mounted.current) return;
    failedRef.current = true;
    setError(message);
    setPhase("failed");
  }, []);

  const poll = useCallback(async () => {
    if (!sessionId.current || !mounted.current) return;
    try {
      const current = await voiceApi.getIntakeSession(sessionId.current);
      if (!mounted.current) return;
      if (current.status === "completed" && current.job_spec) {
        setJobSpec(current.job_spec);
        setPhase("completed");
        return;
      }
      if (current.status === "failed") {
        fail("The voice interview could not be completed. Try again or use Demo Mode.");
        return;
      }
      pollCount.current += 1;
      if (pollCount.current >= MAX_POLLS) {
        setPhase("delayed");
        return;
      }
      pollTimer.current = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    } catch {
      fail("We could not check the interview status. Try checking again.");
    }
  }, [fail]);

  const { startSession, endSession } = useConversation({
    onConnect: ({ conversationId }) => {
      if (!mounted.current) return;
      setPhase("connected");
      const currentSession = sessionId.current;
      if (!currentSession) {
        fail("The voice session lost its VeraMove correlation.");
        return;
      }
      void voiceApi
        .attachIntakeConversation(currentSession, conversationId)
        .catch(() => {
          endSessionRef.current();
          fail("The voice session could not be linked to this intake.");
        });
    },
    onModeChange: ({ mode: nextMode }) => {
      if (mounted.current) setMode(nextMode);
    },
    onMessage: ({ event_id, message, role }) => {
      if (!mounted.current) return;
      const text = message.trim();
      if (!text) return;
      const key = `${event_id ?? "none"}:${role}:${text}`;
      if (seenMessages.current.has(key)) return;
      seenMessages.current.add(key);
      setTurns((current) => [
        ...current,
        { id: key, speaker: role === "agent" ? "agent" : "you", text },
      ]);
    },
    onDisconnect: () => {
      if (!mounted.current) return;
      if (!sessionId.current || failedRef.current) return;
      setPhase("processing");
      pollCount.current = 0;
      void poll();
    },
    onError: () => fail("The live voice connection failed. Try again or use Demo Mode."),
  });

  useEffect(() => {
    endSessionRef.current = endSession;
  }, [endSession]);
```

Complete the public actions and cleanup:

```typescript
  const start = useCallback(async () => {
    failedRef.current = false;
    setError(null);
    setTurns([]);
    setJobSpec(null);
    seenMessages.current.clear();
    try {
      const capability = await voiceApi.getIntegrationStatus();
      if (!capability.live_voice.enabled || !capability.live_voice.configured) {
        fail("Live voice is not available. Switch to Demo Mode to continue.");
        return;
      }
      setPhase("requesting_microphone");
      const permission = await navigator.mediaDevices.getUserMedia({ audio: true });
      permission.getTracks().forEach((track) => track.stop());
      setPhase("connecting");
      const created = await voiceApi.createIntakeSession();
      sessionId.current = created.intake_session_id;
      const credential = await voiceApi.issueBrowserVoiceToken(created.intake_session_id);
      const variables = credential.dynamic_variables;
      startSession({
        conversationToken: credential.conversation_token,
        connectionType: "webrtc",
        dynamicVariables: {
          job_id: variables.job_id,
          intake_session_id: variables.intake_session_id,
          agent_config_version: variables.agent_config_version,
        },
      });
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "NotAllowedError") {
        fail("Microphone permission is required for the live voice interview.");
      } else {
        fail("The live voice interview could not start. Try again or use Demo Mode.");
      }
    }
  }, [fail, startSession]);

  const end = useCallback(() => {
    setPhase("processing");
    endSession();
  }, [endSession]);

  const retryStatus = useCallback(async () => {
    setError(null);
    setPhase("processing");
    pollCount.current = 0;
    await poll();
  }, [poll]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
      endSession();
    };
  }, [endSession]);

  return { phase, mode, turns, jobSpec, error, start, end, retryStatus };
}
```

- [ ] **Step 4: Run hook tests and TypeScript validation**

Run:

```bash
npm --prefix apps/web test -- src/lib/voice/useBrowserVoiceIntake.test.tsx
npm --prefix apps/web run typecheck
```

Expected: PASS with a mocked microphone and no network or real provider connection.

- [ ] **Step 5: Commit the controller**

```bash
git add apps/web/src/lib/voice/useBrowserVoiceIntake.ts apps/web/src/lib/voice/useBrowserVoiceIntake.test.tsx
git commit -m "feat: manage browser voice intake lifecycle"
```

---

### Task 6: Integrate the real voice panel without redesigning intake

**Files:**
- Create: `apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx`
- Create: `apps/web/src/components/veramove/LiveVoiceIntakePanel.test.tsx`
- Modify: `apps/web/src/components/veramove/VoiceIntakePanel.tsx`
- Modify: `apps/web/src/routes/intake.tsx`

**Interfaces:**
- Consumes: `BrowserVoiceIntakeController` and `ConversationProvider`.
- Produces: unchanged `VoiceIntakePanel({ onComplete })` public component with real Live Mode and preserved scripted Demo Mode.

- [ ] **Step 1: Write a failing Live panel interaction test**

Create `apps/web/src/components/veramove/LiveVoiceIntakePanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveVoiceIntakePanel } from "./LiveVoiceIntakePanel";
import { useBrowserVoiceIntake } from "@/lib/voice/useBrowserVoiceIntake";
import { setRuntimeMode } from "@/api/client";

vi.mock("@/lib/voice/useBrowserVoiceIntake", () => ({
  useBrowserVoiceIntake: vi.fn(),
}));
vi.mock("@/api/client", () => ({ setRuntimeMode: vi.fn() }));

describe("LiveVoiceIntakePanel", () => {
  const start = vi.fn();
  const end = vi.fn();
  const retryStatus = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useBrowserVoiceIntake).mockReturnValue({
      phase: "ready",
      mode: "listening",
      turns: [],
      jobSpec: null,
      error: null,
      start,
      end,
      retryStatus,
    });
  });

  afterEach(() => vi.useRealTimers());

  it("starts live voice and displays explicit fictional-data consent copy", async () => {
    render(<LiveVoiceIntakePanel onComplete={vi.fn()} />);

    expect(screen.getByText(/fictional move details/i)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /start voice interview/i }));
    expect(start).toHaveBeenCalledOnce();
  });

  it("renders transcript turns and ends an active interview", async () => {
    vi.mocked(useBrowserVoiceIntake).mockReturnValue({
      phase: "connected",
      mode: "speaking",
      turns: [
        { id: "1", speaker: "agent", text: "What is your fictional move date?" },
        { id: "2", speaker: "you", text: "August fifteenth." },
      ],
      jobSpec: null,
      error: null,
      start,
      end,
      retryStatus,
    });
    render(<LiveVoiceIntakePanel onComplete={vi.fn()} />);

    expect(screen.getByText("What is your fictional move date?")).toBeTruthy();
    expect(screen.getByText("August fifteenth.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /end interview/i }));
    expect(end).toHaveBeenCalledOnce();
  });

  it("shows a safe error and offers an explicit Demo switch", async () => {
    vi.mocked(useBrowserVoiceIntake).mockReturnValue({
      phase: "failed",
      mode: "listening",
      turns: [],
      jobSpec: null,
      error: "The live voice connection failed. Try again or use Demo Mode.",
      start,
      end,
      retryStatus,
    });
    render(<LiveVoiceIntakePanel onComplete={vi.fn()} />);

    expect(screen.getByText(/live voice connection failed/i)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /switch to demo/i }));
    expect(setRuntimeMode).toHaveBeenCalledWith("demo");
  });

  it("briefly shows success, then advances for a completed unconfirmed JobSpec", async () => {
    vi.useFakeTimers();
    const onComplete = vi.fn();
    vi.mocked(useBrowserVoiceIntake).mockReturnValue({
      phase: "completed",
      mode: "listening",
      turns: [],
      error: null,
      start,
      end,
      retryStatus,
      jobSpec: {
        version: "1.0",
        job_id: "00000000-0000-0000-0000-000000000002",
        intake_source: "voice",
        origin: { address_summary: "Fictional Rock Hill, SC" },
        destination: { address_summary: "Fictional Charlotte, NC" },
        inventory: [],
        oversized_or_fragile_items: [],
        services: {},
        source_context: {},
        confirmed: false,
        confirmed_at: null,
        locked_version: null,
        data_classification: "role_play",
      },
    });

    render(<LiveVoiceIntakePanel onComplete={onComplete} />);
    expect(onComplete).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(700));
    expect(onComplete).toHaveBeenCalledWith("00000000-0000-0000-0000-000000000002");
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run the component test and confirm the panel is missing**

Run:

```bash
npm --prefix apps/web test -- src/components/veramove/LiveVoiceIntakePanel.test.tsx
```

Expected: FAIL because `LiveVoiceIntakePanel.tsx` does not exist.

- [ ] **Step 3: Implement the Live panel using the existing visual language**

Create `apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx`. Use the existing `Button`, `StatusPill`, `Mic`, `Radio`, `Loader2`, `CheckCircle2`, `AlertTriangle`, and `RotateCcw` primitives. Drive status copy with this exact mapping:

```typescript
const STATUS = {
  ready: ["Ready to connect", "neutral"],
  requesting_microphone: ["Requesting microphone…", "info"],
  connecting: ["Connecting to voice agent…", "info"],
  connected: ["Live AI voice", "verified"],
  processing: ["Processing your answers…", "info"],
  delayed: ["Still processing", "caution"],
  completed: ["Interview complete", "verified"],
  failed: ["Interview failed", "risk"],
} as const;
```

Call `onComplete` only after a 700 ms success state from an effect that proves all canonical completion invariants:

```typescript
useEffect(() => {
  if (
    controller.phase === "completed" &&
    controller.jobSpec?.intake_source === "voice" &&
    controller.jobSpec.confirmed === false &&
    controller.jobSpec.confirmed_at == null &&
    controller.jobSpec.locked_version == null
  ) {
    const timer = window.setTimeout(
      () => onComplete(controller.jobSpec!.job_id),
      700,
    );
    return () => window.clearTimeout(timer);
  }
  return undefined;
}, [controller.jobSpec, controller.phase, onComplete]);
```

The body must include:

```tsx
<p className="mt-1 text-sm text-muted-foreground">
  Speak with VeraMove's live AI intake agent for about two minutes.
  Use fictional move details only; audio is processed by ElevenLabs for this supervised demo.
</p>
```

Render `controller.turns` with the same Agent/You labels and transcript container classes already used by `VoiceIntakePanel.tsx`. Render these controls exactly by phase:

```tsx
<div className="flex flex-wrap gap-2">
  {controller.phase === "ready" || controller.phase === "failed" ? (
    <Button onClick={() => void controller.start()} className="gap-1.5">
      <Mic className="h-4 w-4" />
      {controller.phase === "failed" ? "Retry interview" : "Start voice interview"}
    </Button>
  ) : controller.phase === "connected" ? (
    <Button onClick={controller.end} variant="outline" className="gap-1.5">
      End interview
    </Button>
  ) : controller.phase === "delayed" ? (
    <Button onClick={() => void controller.retryStatus()} variant="outline" className="gap-1.5">
      <RotateCcw className="h-4 w-4" /> Check status again
    </Button>
  ) : null}
  {(controller.phase === "failed" || controller.phase === "delayed") && (
    <Button onClick={() => setRuntimeMode("demo")} variant="ghost">
      Switch to Demo
    </Button>
  )}
</div>
```

Import `setRuntimeMode` from `@/api/client`; switching modes is explicit and never fabricates completion for the failed live session.

When `jobSpec` exists, render a real extracted preview from:

```typescript
const extracted = [
  ["Route", `${jobSpec.origin.address_summary ?? "Unknown"} → ${jobSpec.destination.address_summary ?? "Unknown"}`],
  ["Date", jobSpec.move_date ?? "Unknown"],
  ["Home", jobSpec.bedroom_count == null ? "Unknown" : `${jobSpec.bedroom_count} bedroom`],
  ["Inventory", jobSpec.inventory.map((item) => `${item.quantity}× ${item.name}`).join(", ") || "None listed"],
];
```

Do not render provider errors, token values, agent IDs, or raw exceptions.

- [ ] **Step 4: Select the Live panel while preserving the existing Demo implementation**

In `apps/web/src/components/veramove/VoiceIntakePanel.tsx`:

1. Rename the current exported implementation to `DemoVoiceIntakePanel` without changing its timers, variants, fixture transcript, or Demo adapter behavior.
2. Remove the obsolete Live Mode note and `runtimeMode === "live"` button disable from the Demo implementation because it will only render in Demo Mode.
3. Remove the now-unused `Info`, `FlaskConical`, `setRuntimeMode`, and `DEMO_JOB_ID` imports from that file.
4. Add this wrapper:

```tsx
import { ConversationProvider } from "@elevenlabs/react";
import { LiveVoiceIntakePanel } from "./LiveVoiceIntakePanel";

export function VoiceIntakePanel({ onComplete }: { onComplete: (jobId: string) => void }) {
  const runtimeMode = useRuntimeMode();
  if (runtimeMode === "live") {
    return (
      <ConversationProvider>
        <LiveVoiceIntakePanel onComplete={onComplete} />
      </ConversationProvider>
    );
  }
  return <DemoVoiceIntakePanel onComplete={onComplete} />;
}
```

Do not add any provider ID, API key, or `VITE_ELEVENLABS_*` variable.

- [ ] **Step 5: Update the stale intake capability note**

Replace the footer in `apps/web/src/routes/intake.tsx` with:

```tsx
<p className="text-xs text-muted-foreground">
  Live Mode sends document text and authenticated voice-session requests to the VeraMove API.
  Demo Mode remains synthetic and credential-free. Every completed intake still requires review
  and explicit confirmation before vendor calls.
</p>
```

- [ ] **Step 6: Run component tests, the complete frontend suite, and production build**

Run:

```bash
npm --prefix apps/web test -- src/components/veramove/LiveVoiceIntakePanel.test.tsx src/lib/voice/useBrowserVoiceIntake.test.tsx
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: all Vitest tests pass, TypeScript reports no errors, and Vite produces the production bundle.

- [ ] **Step 7: Commit the real Live Mode panel**

```bash
git add apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx apps/web/src/components/veramove/LiveVoiceIntakePanel.test.tsx apps/web/src/components/veramove/VoiceIntakePanel.tsx apps/web/src/routes/intake.tsx
git commit -m "feat: connect live browser voice intake"
```

---

### Task 7: Document, verify, and prepare the live deployment

**Files:**
- Create: `apps/web/README.md`
- Modify: `agents/elevenlabs-dashboard-checklist.md`
- Modify: `.env.example`
- Verify: all files changed in Tasks 1–6

**Interfaces:**
- Consumes: complete browser voice feature and existing Render/ElevenLabs configuration.
- Produces: operator instructions, a green repository quality gate, and a bounded manual live test checklist.

- [ ] **Step 1: Add concise frontend operation documentation**

Create `apps/web/README.md`:

```markdown
# VeraMove web

The React frontend uses FastAPI-generated types from `src/api/schema.d.ts` and one HTTP client in
`src/api/client.ts`.

## Voice intake

- Demo Mode uses a scripted synthetic transcript and needs no provider credentials.
- Live Mode checks `/api/integrations/status`, requests microphone permission, creates an intake
  session, obtains a short-lived WebRTC token from VeraMove, and connects through
  `@elevenlabs/react`.
- The ElevenLabs API key, Intake Agent ID, prompt, model, and voice never enter the frontend.
- Transcript turns remain only in React memory. The signed post-call webhook creates the canonical,
  unconfirmed `JobSpecV1`; the browser polls the intake session and then opens Confirm.

Run locally:

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

Run checks:

```bash
npm --prefix apps/web run generate:api
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix apps/web run build
```

Use fictional role-play move details only during live tests.
```

- [ ] **Step 2: Document the one required dashboard setting**

Add to `agents/elevenlabs-dashboard-checklist.md` under the Intake Agent security section:

```markdown
### Authenticated browser voice

- [ ] Enable agent authentication for the VeraMove Intake Agent so the backend can issue short-lived
  WebRTC conversation tokens.
- [ ] Do not configure a public widget or expose the Intake Agent ID in frontend environment values.
- [ ] Keep prompt, first-message, voice, and model client overrides disabled.
- [ ] Keep the existing signed post-call webhook and the three dynamic variables: `job_id`,
  `intake_session_id`, and `agent_config_version`.
```

- [ ] **Step 3: Clarify existing environment configuration without adding a secret**

Update the `.env.example` live-voice comment to:

```dotenv
# Controlled live voice remains disabled unless explicitly enabled. Browser intake uses the API key,
# Intake Agent ID, webhook secret, agent-config version, and Supabase; no provider secret belongs in VITE_*.
```

Do not add `VITE_ELEVENLABS_API_KEY`, `VITE_ELEVENLABS_AGENT_ID`, or another frontend provider variable.

- [ ] **Step 4: Run the canonical repository quality gate**

Run:

```bash
.venv/bin/python scripts/check.py
```

Expected, in order: Ruff PASS, pytest PASS, OpenAPI export PASS, API type generation PASS, frontend typecheck PASS, Vitest PASS, and Vite production build PASS.

- [ ] **Step 5: Inspect generated and secret-sensitive diffs**

Run:

```bash
git diff --check
git status --short
git diff -- .env.example render.yaml apps/web services/api supabase agents
```

Expected: no populated credentials, phone numbers, provider tokens, transcript fixtures containing real details, duplicate domain models, raw presentation `fetch`, or extra lockfiles.

Run:

```bash
rg -n "VITE_ELEVENLABS|xi-api-key|conversation_token" apps/web/src
```

Expected: `xi-api-key` and `VITE_ELEVENLABS` have zero matches; `conversation_token` appears only in generated types, the centralized API/controller, and synthetic tests.

- [ ] **Step 6: Commit documentation and final generated consistency**

```bash
git add .env.example apps/web/README.md agents/elevenlabs-dashboard-checklist.md packages/contracts/openapi.json apps/web/src/api/schema.d.ts
git commit -m "docs: add browser voice intake runbook"
```

- [ ] **Step 7: Apply the live migration and perform one supervised smoke test**

In Supabase SQL Editor, apply `supabase/migrations/202607190005_browser_voice_intake.sql`. In the ElevenLabs Intake Agent dashboard, complete the four authenticated-browser checklist items. Deploy the backend before the frontend.

Use the public VeraMove site in Live Mode with fictional details and verify this exact sequence:

1. **Start voice interview** requests microphone permission only after integration readiness succeeds.
2. The Intake Agent gives AI/recording disclosure and asks for consent.
3. Agent and user turns appear in the live transcript without duplicates.
4. **End interview** changes the panel to processing.
5. The session becomes completed and opens `/confirm/{job_id}`.
6. The JobSpec shows `intake_source=voice`, `confirmed=false`, `confirmed_at=null`, and `locked_version=null`.
7. No vendor call starts before the user presses Confirm.
8. Switching back to Demo Mode still completes the scripted flow without provider calls.

If processing exceeds 60 seconds, use **Check status again** and inspect Render's safe error code plus ElevenLabs webhook delivery status. Do not paste API keys, webhook bodies, transcript text, or real participant details into logs or issue comments.

---

## Completion Criteria

- Every focused test and `python scripts/check.py` passes.
- The public OpenAPI and generated TypeScript artifacts include both browser voice routes.
- Exactly one non-secret credential reservation is persisted per web intake session; no token is persisted.
- The browser uses only the centralized FastAPI client plus the token-authenticated SDK WebRTC connection.
- The signed post-call webhook creates exactly one canonical, unconfirmed voice JobSpec.
- Live transcript, permission, connection, processing, delayed, completion, and safe failure states work.
- Demo Mode remains credential-free and unchanged.
- The manual fictional browser conversation reaches Confirm without exposing credentials or collecting real PII.
