# VeraMove Live Integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire independently enabled OpenAI document/narration, Tavily vendor discovery, and Supabase persistence while preserving credential-free mock mode and deterministic evidence rules.

**Architecture:** Each provider receives an injected HTTP-facing client behind the repository's existing protocols. `Settings` owns explicit enablement and validated credentials; dependency composition selects one implementation per boundary and never silently falls back after an enabled live provider fails. Supabase stores the same Pydantic aggregates exposed by the in-memory repository while also writing indexed relational rows for calls, quotes, evidence, recommendations, and idempotency.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, HTTPX, PostgreSQL/Supabase Data API, pytest, Ruff, OpenAI Responses API, Tavily Search API.

## Global Constraints

- `APP_MODE=mock` must run without credentials or Supabase.
- `OPENAI_ENABLED`, `TAVILY_ENABLED`, and `SUPABASE_ENABLED` default to `false` and are independent of `LIVE_CALLS_ENABLED`.
- Enabled provider failures must surface; do not fall back to synthetic data or process memory.
- OpenAI may extract facts and replace recommendation summary text only; deterministic rankings, findings, totals, evidence IDs, and recording URLs remain authoritative.
- Tavily results are vendor candidates with provenance, never quotes or verified negotiation leverage.
- Supabase elevated credentials remain server-side and must not appear in OpenAPI, frontend code, fixtures, errors, or logs.
- Exactly three distinct initial vendors must be resolved before the first call begins.
- No automated test may contact an external provider or place a telephone call.
- Route paths remain stable. The only public contract change is `VendorDiscoveryResponse.source: "synthetic_mock" | "tavily"`.
- Regenerate and commit FastAPI OpenAPI and generated TypeScript types after the contract change.
- Run `python scripts/check.py` and `.venv/bin/python -m evals.run` before completion.

---

### Task 1: Independent live-integration settings

**Files:**
- Modify: `services/api/app/core/config.py`
- Create: `services/api/tests/test_live_integrations_config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `OpenAIConfig`, `TavilyConfig`, `SupabaseConfig` dataclasses.
- Produces: `Settings.require_openai_config()`, `Settings.require_tavily_config()`, and `Settings.require_supabase_config()`.
- Consumes: existing `_optional_env()` and `_boolean_env()` parsing rules.

- [ ] **Step 1: Write configuration tests that fail before the dataclasses exist**

```python
from dataclasses import replace

import pytest

from services.api.app.core.config import (
    OpenAIConfig,
    Settings,
    SupabaseConfig,
    TavilyConfig,
)
from services.api.app.core.errors import ProviderConfigurationError


def test_live_integrations_default_disabled(monkeypatch):
    for name in (
        "OPENAI_ENABLED",
        "OPENAI_API_KEY",
        "TAVILY_ENABLED",
        "TAVILY_API_KEY",
        "SUPABASE_ENABLED",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.openai == OpenAIConfig()
    assert settings.tavily == TavilyConfig()
    assert settings.supabase == SupabaseConfig()


def test_enabled_integrations_require_complete_configuration():
    settings = Settings(
        openai=OpenAIConfig(enabled=True),
        tavily=TavilyConfig(enabled=True),
        supabase=SupabaseConfig(enabled=True),
    )
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        settings.require_openai_config()
    with pytest.raises(ProviderConfigurationError, match="TAVILY_API_KEY"):
        settings.require_tavily_config()
    with pytest.raises(ProviderConfigurationError, match="SUPABASE_URL"):
        settings.require_supabase_config()


def test_supabase_secret_key_precedes_legacy_service_role(monkeypatch):
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic-project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "synthetic-new-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-legacy-secret")
    assert Settings.from_env().require_supabase_config().secret_key == "synthetic-new-secret"


@pytest.mark.parametrize("name", ["OPENAI_API_BASE_URL", "TAVILY_API_BASE_URL"])
def test_provider_base_url_requires_https(monkeypatch, name):
    monkeypatch.setenv(name, "http://provider.example")
    with pytest.raises(ProviderConfigurationError, match="HTTPS"):
        Settings.from_env()
```

- [ ] **Step 2: Run the focused tests and verify the import failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_integrations_config.py -q`  
Expected: FAIL because the new configuration classes do not exist.

- [ ] **Step 3: Add strict dataclasses and environment parsing**

Add to `config.py`:

```python
def _https_base_url(name: str, default: str) -> str:
    value = _optional_env(name) or default
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ProviderConfigurationError(f"{name} must be an HTTPS base URL")
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    enabled: bool = False
    api_key: str | None = None
    document_model: str = "gpt-5.6-luna"
    recommendation_model: str = "gpt-5.6-terra"
    api_base_url: str = "https://api.openai.com"


@dataclass(frozen=True, slots=True)
class TavilyConfig:
    enabled: bool = False
    api_key: str | None = None
    api_base_url: str = "https://api.tavily.com"


@dataclass(frozen=True, slots=True)
class SupabaseConfig:
    enabled: bool = False
    url: str | None = None
    secret_key: str | None = None
```

Add the three fields to `Settings`, add `require_*_config()` methods that name only missing environment-variable names, and parse:

```python
openai=OpenAIConfig(
    enabled=_boolean_env("OPENAI_ENABLED"),
    api_key=_optional_env("OPENAI_API_KEY"),
    document_model=os.getenv("OPENAI_DOCUMENT_MODEL", "gpt-5.6-luna").strip(),
    recommendation_model=os.getenv(
        "OPENAI_RECOMMENDATION_MODEL", "gpt-5.6-terra"
    ).strip(),
    api_base_url=_https_base_url("OPENAI_API_BASE_URL", "https://api.openai.com"),
),
tavily=TavilyConfig(
    enabled=_boolean_env("TAVILY_ENABLED"),
    api_key=_optional_env("TAVILY_API_KEY"),
    api_base_url=_https_base_url("TAVILY_API_BASE_URL", "https://api.tavily.com"),
),
supabase=SupabaseConfig(
    enabled=_boolean_env("SUPABASE_ENABLED"),
    url=(
        _https_base_url("SUPABASE_URL", "https://disabled.supabase.co")
        if _optional_env("SUPABASE_URL")
        else None
    ),
    secret_key=(
        _optional_env("SUPABASE_SECRET_KEY")
        or _optional_env("SUPABASE_SERVICE_ROLE_KEY")
    ),
),
```

- [ ] **Step 4: Document disabled defaults and credential names in `.env.example`**

```dotenv
OPENAI_ENABLED=false
OPENAI_API_KEY=
OPENAI_DOCUMENT_MODEL=gpt-5.6-luna
OPENAI_RECOMMENDATION_MODEL=gpt-5.6-terra
OPENAI_API_BASE_URL=https://api.openai.com

TAVILY_ENABLED=false
TAVILY_API_KEY=
TAVILY_API_BASE_URL=https://api.tavily.com

SUPABASE_ENABLED=false
SUPABASE_URL=
SUPABASE_SECRET_KEY=
# Legacy fallback only:
SUPABASE_SERVICE_ROLE_KEY=
```

- [ ] **Step 5: Run focused tests and Ruff**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_integrations_config.py -q`  
Expected: PASS.  
Run: `.venv/bin/python -m ruff check services/api/app/core/config.py services/api/tests/test_live_integrations_config.py`  
Expected: PASS.

- [ ] **Step 6: Commit configuration**

```bash
git add services/api/app/core/config.py services/api/tests/test_live_integrations_config.py .env.example
git commit -m "feat(config): add live integration switches"
```

---

### Task 2: OpenAI Responses adapters

**Files:**
- Modify: `services/api/app/integrations/openai/base.py`
- Modify: `services/api/app/integrations/openai/document.py`
- Create: `services/api/app/integrations/openai/live.py`
- Modify: `services/api/app/integrations/openai/__init__.py`
- Create: `services/api/tests/test_openai_live.py`

**Interfaces:**
- Consumes: `StructuredDocumentClient`, `GroundedNarrativeClient`, `DocumentParseResult`, and injected `OpenAIJsonTransport`.
- Produces: `HttpxOpenAITransport`, `OpenAIResponsesClient`, and `OpenAIResponsesNarrativeClient`.
- Request contract: `POST {api_base_url}/v1/responses` with `reasoning.effort=none` and strict JSON schema for document extraction.

- [ ] **Step 1: Write request/response and failure tests using a recording transport**

```python
import json

import pytest

from services.api.app.contracts import DocumentParseResult
from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.openai.live import OpenAIResponsesClient


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def post(self, url, headers, payload):
        self.requests.append((url, headers, payload))
        return self.response


def completed_response(payload):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(payload)}],
            }
        ],
    }


def test_openai_document_request_uses_strict_responses_schema(fixtures):
    result = {
        "job_spec": fixtures.load_job().model_copy(
            update={"confirmed": False, "confirmed_at": None, "locked_version": None},
            deep=True,
        ).model_dump(mode="json"),
        "missing_fields": [],
        "warnings": [],
        "fields_requiring_confirmation": [],
        "provenance": [],
    }
    transport = RecordingTransport(completed_response(result))
    client = OpenAIResponsesClient(
        api_key="synthetic-openai-key",
        api_base_url="https://api.openai.example",
        transport=transport,
    )
    parsed = client.parse(
        model="gpt-5.6-luna",
        system_prompt="Extract supported facts.",
        content=b"SYNTHETIC two-bedroom move",
        mime_type="text/plain",
        source_id="synthetic.txt",
        response_schema=DocumentParseResult,
    )
    assert parsed == result
    url, headers, payload = transport.requests[0]
    assert url == "https://api.openai.example/v1/responses"
    assert headers["Authorization"] == "Bearer synthetic-openai-key"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["text"]["format"]["strict"] is True


@pytest.mark.parametrize(
    "response",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": []},
        {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "refusal"}]}],
        },
    ],
)
def test_openai_rejects_incomplete_empty_or_refused_output(response):
    client = OpenAIResponsesClient(
        api_key="synthetic",
        transport=RecordingTransport(response),
    )
    with pytest.raises(ProviderRequestError):
        client.parse(
            model="gpt-5.6-luna",
            system_prompt="Synthetic prompt",
            content=b"synthetic",
            mime_type="text/plain",
            source_id="synthetic.txt",
            response_schema=DocumentParseResult,
        )
```

- [ ] **Step 2: Run focused tests and confirm the module is missing**

Run: `.venv/bin/python -m pytest services/api/tests/test_openai_live.py -q`  
Expected: FAIL importing `services.api.app.integrations.openai.live`.

- [ ] **Step 3: Define the injected transport and safe HTTPX implementation**

```python
class OpenAIJsonTransport(Protocol):
    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]: ...


class HttpxOpenAITransport:
    def post(self, url, headers, payload):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError("OpenAI request failed") from exc
        if not isinstance(result, dict):
            raise ProviderRequestError("OpenAI returned an invalid response envelope")
        return result
```

Do not include status response bodies, request payloads, or keys in exception messages.

- [ ] **Step 4: Implement strict Responses document parsing**

```python
class OpenAIResponsesClient:
    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://api.openai.com",
        transport: OpenAIJsonTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base_url = api_base_url.rstrip("/")
        self._transport = transport or HttpxOpenAITransport()

    def parse(self, *, model, system_prompt, content, mime_type, source_id, response_schema):
        user_content = self._content_part(content, mime_type, source_id)
        response = self._transport.post(
            f"{self._api_base_url}/v1/responses",
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            {
                "model": model,
                "reasoning": {"effort": "none"},
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                    {"role": "user", "content": [user_content]},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "document_parse_result",
                        "strict": True,
                        "schema": response_schema.model_json_schema(),
                    }
                },
            },
        )
        return json.loads(self._output_text(response))
```

`_content_part()` returns `input_text` for `text/plain`, an `input_file` data URL for PDF, and an `input_image` data URL with `detail="low"` for PNG/JPEG. `_output_text()` requires `status=completed` and exactly one usable `output_text`; refusals and malformed envelopes raise `ProviderRequestError`.

- [ ] **Step 5: Support the text route in `OpenAIDocumentParser`**

Add `"text/plain"` to `SUPPORTED_DOCUMENT_TYPES`. Keep every existing postcondition. Add this assertion using the same `RecordingTransport` result fixture:

```python
parser = OpenAIDocumentParser(
    OpenAIResponsesClient(
        api_key="synthetic",
        transport=RecordingTransport(completed_response(result)),
    ),
    model="gpt-5.6-luna",
)
parsed = parser.parse_document(
    b"SYNTHETIC two-bedroom move",
    "text/plain",
    "synthetic.txt",
)
assert parsed.job_spec.intake_source is IntakeSource.DOCUMENT
assert parsed.job_spec.confirmed is False
assert parsed.job_spec.locked_version is None
```

- [ ] **Step 6: Implement grounded narrative output**

`OpenAIResponsesNarrativeClient.explain()` sends serialized `job_spec`, `rankings`, and `findings` in one bounded user message, sets `reasoning.effort=none`, requests plain text, and returns `_output_text(response)`. Its system prompt must say:

```text
Explain the already-determined VeraMove ranking. Preserve vendor order, totals,
findings, and evidence identifiers. Do not add facts, quotes, discounts, claims,
or recommendations not present in the supplied structured data. Return only a
concise customer-facing summary.
```

Add a test that captures the request and proves no provider response can mutate the ranking objects passed by the caller.

- [ ] **Step 7: Run OpenAI tests and Ruff**

Run: `.venv/bin/python -m pytest services/api/tests/test_openai_live.py services/api/tests/test_intelligence.py -q`  
Expected: PASS.  
Run: `.venv/bin/python -m ruff check services/api/app/integrations/openai services/api/tests/test_openai_live.py`  
Expected: PASS.

- [ ] **Step 8: Commit OpenAI adapters**

```bash
git add services/api/app/integrations/openai services/api/tests/test_openai_live.py
git commit -m "feat(openai): add strict Responses adapters"
```

---

### Task 3: Tavily live search and truthful discovery source

**Files:**
- Modify: `services/api/app/integrations/tavily/base.py`
- Modify: `services/api/app/integrations/tavily/mock.py`
- Modify: `services/api/app/integrations/tavily/cached.py`
- Create: `services/api/app/integrations/tavily/live.py`
- Modify: `services/api/app/integrations/tavily/__init__.py`
- Modify: `services/api/app/contracts/models.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/orchestration/service.py`
- Create: `services/api/tests/test_tavily_live.py`
- Modify: `services/api/tests/test_api.py`
- Modify: `services/api/tests/test_service.py`

**Interfaces:**
- Produces: `TavilyHttpClient.search(query: str, max_results: int) -> list[dict[str, Any]]`.
- Adds: `VendorDiscoveryGateway.source -> Literal["synthetic_mock", "tavily"]`.
- Changes: `VendorDiscoveryResponse.source` to the same closed union.
- Changes: initial batch resolves exactly three distinct vendors from the injected gateway before the first call.

- [ ] **Step 1: Write live-client request and failure tests**

```python
def test_tavily_http_client_uses_private_bounded_search_options():
    transport = RecordingTransport(
        {"results": [{"title": "Synthetic Movers", "url": "https://vendor.example"}]}
    )
    client = TavilyHttpClient(
        api_key="synthetic-tavily-key",
        api_base_url="https://api.tavily.example",
        transport=transport,
    )
    results = client.search(query="moving companies in Example City", max_results=10)
    assert len(results) == 1
    url, headers, payload = transport.requests[0]
    assert url == "https://api.tavily.example/search"
    assert headers["Authorization"] == "Bearer synthetic-tavily-key"
    assert payload == {
        "query": "moving companies in Example City",
        "search_depth": "basic",
        "topic": "general",
        "max_results": 10,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
```

Add parameterized malformed-envelope and transport-error tests that assert `ProviderRequestError` and never inspect or expose the key.

- [ ] **Step 2: Run focused tests and verify the client is absent**

Run: `.venv/bin/python -m pytest services/api/tests/test_tavily_live.py -q`  
Expected: FAIL importing `TavilyHttpClient`.

- [ ] **Step 3: Implement `TavilyHttpClient` behind an injected transport**

Use the same safe error pattern as OpenAI. Validate that `results` is a list of dictionaries; do not return Tavily `answer`, `raw_content`, images, usage, or request metadata.

```python
response = self._transport.post(
    f"{self._api_base_url}/search",
    {
        "Authorization": f"Bearer {self._api_key}",
        "Content-Type": "application/json",
    },
    {
        "query": query,
        "search_depth": "basic",
        "topic": "general",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    },
)
```

- [ ] **Step 4: Add a truthful source property to both gateways and the contract**

```python
class MockVendorDiscoveryGateway:
    source = "synthetic_mock"


class CachedTavilyVendorDiscovery:
    source = "tavily"
```

Change `VendorDiscoveryResponse.source` to `Literal["synthetic_mock", "tavily"]`. Change the route to return `source=service.vendor_discovery_source`.

- [ ] **Step 5: Resolve the entire three-vendor batch before placing any call**

In `VeraMoveService` add:

```python
@property
def vendor_discovery_source(self) -> str:
    return self._discovery.source

def _initial_vendors(self, record: JobRecord) -> list[Vendor]:
    candidates = self._discovery.discover(
        record.job_spec.origin.address_summary,
        record.job_spec.destination.address_summary,
    )
    distinct = list({vendor.vendor_id: vendor for vendor in candidates}.values())
    if len(distinct) < 3:
        raise DomainConflict("Initial calling requires three distinct vendors")
    return distinct[:3]
```

Call `_initial_vendors(record)` before transitioning the job to `calling`, then iterate the returned list. This guarantees a short Tavily response does not produce a partial call batch.

- [ ] **Step 6: Add API and service assertions**

Tests must prove:

```python
assert client.get("/api/vendors/discover?origin=Example%20City").json()["source"] == "synthetic_mock"
assert len(service.start_calls(job_id).calls) == 3
assert {call.vendor.vendor_id for call in result.calls} == {
    vendor.vendor_id for vendor in discovery_vendors[:3]
}
```

Add a discovery gateway returning two vendors and assert the job stays `confirmed`, with zero attempts and zero calls after the 409-domain failure.

- [ ] **Step 7: Run focused tests and Ruff**

Run: `.venv/bin/python -m pytest services/api/tests/test_tavily_live.py services/api/tests/test_api.py services/api/tests/test_service.py -q`  
Expected: PASS.  
Run: `.venv/bin/python -m ruff check services/api/app/integrations/tavily services/api/app/orchestration/service.py services/api/tests/test_tavily_live.py`  
Expected: PASS.

- [ ] **Step 8: Commit Tavily slice**

```bash
git add services/api/app/integrations/tavily services/api/app/contracts/models.py services/api/app/api/router.py services/api/app/orchestration/service.py services/api/tests/test_tavily_live.py services/api/tests/test_api.py services/api/tests/test_service.py
git commit -m "feat(tavily): wire provenance-backed discovery"
```

---

### Task 4: Supabase schema hardening and PostgREST client

**Files:**
- Create: `supabase/migrations/202607190002_live_persistence_hardening.sql`
- Create: `services/api/app/repositories/supabase_client.py`
- Create: `services/api/tests/test_supabase_client.py`
- Modify: `services/api/requirements.txt` only if HTTPX functionality already present proves insufficient; otherwise leave dependencies unchanged.

**Interfaces:**
- Produces: `SupabaseTableClient` protocol with `select_many`, `insert`, `upsert`, and `update`.
- Produces: `SupabasePostgrestClient` that sends server-only Data API requests.
- Database change: `calls.record_type IN ('attempt', 'canonical')` and backend-only table grants.

- [ ] **Step 1: Write transport request and safe-error tests**

```python
def test_postgrest_client_sends_backend_headers_and_bounded_filters():
    transport = RecordingTransport([{"id": "synthetic-id", "payload": {}}])
    client = SupabasePostgrestClient(
        url="https://synthetic.supabase.co",
        secret_key="synthetic-secret",
        transport=transport,
    )
    rows = client.select_many("jobs", {"id": "eq.synthetic-id"})
    assert len(rows) == 1
    method, url, headers, params, payload = transport.requests[0]
    assert method == "GET"
    assert url == "https://synthetic.supabase.co/rest/v1/jobs"
    assert headers["apikey"] == "synthetic-secret"
    assert headers["Authorization"] == "Bearer synthetic-secret"
    assert params == {"id": "eq.synthetic-id", "select": "*"}
    assert payload is None
```

Test insert duplicate handling separately so the repository can distinguish a unique violation from a provider outage without exposing response bodies.

- [ ] **Step 2: Run tests and verify the client module is missing**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_client.py -q`  
Expected: FAIL importing `SupabasePostgrestClient`.

- [ ] **Step 3: Add the migration**

```sql
alter table calls
    add column if not exists record_type text not null default 'attempt';

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'calls_record_type_check'
    ) then
        alter table calls add constraint calls_record_type_check
            check (record_type in ('attempt', 'canonical'));
    end if;
end
$$;

alter table jobs enable row level security;
alter table vendors enable row level security;
alter table calls enable row level security;
alter table quotes enable row level security;
alter table transcript_evidence enable row level security;
alter table recommendations enable row level security;
alter table event_log enable row level security;

revoke all on jobs, vendors, calls, quotes, transcript_evidence, recommendations, event_log
    from anon, authenticated;
grant select, insert, update, delete on jobs, vendors, calls, quotes,
    transcript_evidence, recommendations, event_log to service_role;

create index if not exists calls_record_type_idx on calls(record_type);
```

- [ ] **Step 4: Implement the high-level Data API client**

```python
class SupabaseTableClient(Protocol):
    def select_many(self, table: str, filters: dict[str, str]) -> list[dict[str, Any]]: ...
    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...
    def upsert(
        self, table: str, row: dict[str, Any], on_conflict: str
    ) -> dict[str, Any]: ...
    def update(
        self, table: str, filters: dict[str, str], values: dict[str, Any]
    ) -> dict[str, Any]: ...
```

`SupabasePostgrestClient` uses `{url}/rest/v1/{table}`, `Prefer: return=representation`, and `Prefer: resolution=merge-duplicates,return=representation` for upsert. Restrict table names to a hard-coded allowlist. Map network, JSON, `401`/`403`, `429`, and `5xx` to `ProviderRequestError("Supabase request failed")`; map unique violations to a dedicated internal `SupabaseDuplicate` exception without including provider payloads.

- [ ] **Step 5: Run client tests and Ruff**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_client.py -q`  
Expected: PASS.  
Run: `.venv/bin/python -m ruff check services/api/app/repositories/supabase_client.py services/api/tests/test_supabase_client.py`  
Expected: PASS.

- [ ] **Step 6: Commit schema and client**

```bash
git add supabase/migrations/202607190002_live_persistence_hardening.sql services/api/app/repositories/supabase_client.py services/api/tests/test_supabase_client.py
git commit -m "feat(supabase): add secure Data API foundation"
```

---

### Task 5: Supabase repository implementation

**Files:**
- Create: `services/api/app/repositories/supabase.py`
- Modify: `services/api/app/repositories/__init__.py`
- Create: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- Consumes: `SupabaseTableClient` and all three repository protocols.
- Produces: `SupabaseRepository`, structurally compatible with `JobRepository`, `CallRepository`, and `QuoteRepository`.
- Invariant: `reset()` always raises and never deletes remote data.

- [ ] **Step 1: Write repository contract tests against an in-memory fake table client**

Create `FakeSupabaseTableClient` that implements the four high-level methods and enforces `on_conflict` keys. Reuse existing fixture Pydantic objects. Tests must cover:

```python
def test_supabase_job_round_trip_and_confirmed_lock(repository, job_record):
    created = repository.create(job_record)
    assert repository.get(job_record.job_spec.job_id) == created
    confirmed = created.model_copy(
        update={
            "job_spec": created.job_spec.model_copy(
                update={
                    "confirmed": True,
                    "confirmed_at": FIXED_NOW,
                    "locked_version": "1.0",
                }
            )
        },
        deep=True,
    )
    repository.save(confirmed)
    mutated = confirmed.model_copy(
        update={
            "job_spec": confirmed.job_spec.model_copy(
                update={"insurance_preference": "Changed"}
            )
        },
        deep=True,
    )
    with pytest.raises(DomainConflict, match="locked"):
        repository.save(mutated)


def test_supabase_webhook_reservation_is_atomic(repository):
    assert repository.reserve_webhook("synthetic-event") is True
    assert repository.reserve_webhook("synthetic-event") is False


def test_supabase_reset_is_never_destructive(repository):
    with pytest.raises(RuntimeError, match="disabled"):
        repository.reset()
```

Also port the call-attempt, canonical-call, quote, event, and verified-leverage assertions from `test_repository_and_adapters.py` to the fake Supabase repository.

- [ ] **Step 2: Run focused tests and verify the repository is missing**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_repository.py -q`  
Expected: FAIL importing `SupabaseRepository`.

- [ ] **Step 3: Implement job persistence with exact Pydantic reconstruction**

```python
class SupabaseRepository:
    def __init__(self, client: SupabaseTableClient) -> None:
        self._client = client

    def create(self, record: JobRecord) -> JobRecord:
        row = self._job_row(record)
        try:
            self._client.insert("jobs", row)
        except SupabaseDuplicate as exc:
            raise DuplicateResource(f"Job {record.job_spec.job_id} already exists") from exc
        return self._copy_job(record)

    def get(self, job_id: UUID) -> JobRecord | None:
        rows = self._client.select_many("jobs", {"id": f"eq.{job_id}"})
        if not rows:
            return None
        return JobRecord.model_validate(rows[0]["payload"])

    def save(self, record: JobRecord) -> JobRecord:
        current = self.get(record.job_spec.job_id)
        if current is None:
            raise ResourceNotFound(f"Job {record.job_spec.job_id} was not found")
        if current.job_spec.confirmed and (
            current.job_spec.model_dump(mode="json")
            != record.job_spec.model_dump(mode="json")
        ):
            raise DomainConflict("Confirmed JobSpec version is locked and cannot be changed")
        self._client.upsert("jobs", self._job_row(record), on_conflict="id")
        self._persist_recommendation(record)
        return self._copy_job(record)
```

`_job_row()` writes `id`, `job_spec_version`, `state`, `confirmed_at`, `locked_job_spec_version`, `data_classification`, `payload`, and `updated_at`.

- [ ] **Step 4: Implement vendors, attempts, canonical calls, quotes, and evidence**

Before a call or quote, upsert the vendor by `id`. Store an attempt row as:

```python
{
    "id": str(attempt.call_id),
    "job_id": str(attempt.job_id),
    "vendor_id": str(attempt.vendor.vendor_id),
    "external_call_id": (
        attempt.reference.provider_call_id if attempt.reference else None
    ),
    "idempotency_key": f"call:{attempt.call_id}",
    "status": attempt.status.value,
    "outcome_type": None,
    "record_type": "attempt",
    "data_classification": attempt.vendor.data_classification.value,
    "payload": attempt.model_dump(mode="json"),
}
```

`save_call()` updates the canonical `JobRecord` payload and upserts the same call ID with `record_type="canonical"`, outcome type, and the `CallRecord` payload. `save_quote()` updates the job aggregate and upserts `quotes`, every `TranscriptEvidence`, and the vendor. Preserve `manually_fabricated` and verification columns explicitly.

- [ ] **Step 5: Implement safe event and idempotency storage**

`reserve_webhook(key)` inserts an `event_log` row whose ID is `uuid5(NAMESPACE_URL, f"webhook:{key}")`, `source="elevenlabs"`, `event_type="reserved"`, `idempotency_key=key`, `payload={}`. Return `False` only on `SupabaseDuplicate`; propagate other failures.

`append_event(event)` inserts a distinct row with `source="veramove"`, `idempotency_key=f"job-event:{event.event_id}"`, and `payload=event.model_dump(mode="json")`. `list_events(job_id)` selects only `source=eq.veramove` and parses `JobEvent` from payload. Raw provider bodies never enter these rows.

- [ ] **Step 6: Implement verified leverage and non-destructive reset**

Use the same predicates as `InMemoryRepository.get_verified_competing_quote()`. `reset()` is exactly:

```python
def reset(self) -> None:
    raise RuntimeError("SupabaseRepository reset is disabled")
```

- [ ] **Step 7: Run repository tests, compatibility tests, and Ruff**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_repository.py services/api/tests/test_repository_and_adapters.py -q`  
Expected: PASS.  
Run: `.venv/bin/python -m ruff check services/api/app/repositories services/api/tests/test_supabase_repository.py`  
Expected: PASS.

- [ ] **Step 8: Commit repository**

```bash
git add services/api/app/repositories services/api/tests/test_supabase_repository.py
git commit -m "feat(supabase): persist VeraMove workflow state"
```

---

### Task 6: Runtime composition and narration wiring

**Files:**
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/main.py`
- Modify: `services/api/app/orchestration/providers.py`
- Modify: `services/api/app/orchestration/mock_intelligence.py`
- Create: `services/api/app/orchestration/live_intelligence.py`
- Modify: `services/api/app/orchestration/service.py`
- Create: `services/api/tests/test_live_integrations_wiring.py`
- Modify: `services/api/tests/conftest.py`

**Interfaces:**
- Produces: `build_repository(settings, supabase_client=None)`.
- Produces: `LiveIntelligenceProvider.extract_document()` delegating to `OpenAIDocumentParser` and `negotiate()` delegating to the existing safe negotiation gateway.
- Changes: the `VeraMoveService` constructor accepts `recommendation_narrator: RecommendationNarrator | None = None`, and `_build_recommendation()` applies summary-only narration.
- Application state owns the selected repository and service snapshot.

- [ ] **Step 1: Write composition tests before changing dependencies**

```python
def test_default_composition_uses_only_mock_and_memory():
    settings = Settings()
    repository = build_repository(settings)
    service = build_service(settings, repository)
    assert isinstance(repository, InMemoryRepository)
    assert service.vendor_discovery_source == "synthetic_mock"


def test_enabled_supabase_never_falls_back_to_memory():
    settings = Settings(
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic.supabase.co",
            secret_key="synthetic-secret",
        )
    )
    repository = build_repository(settings, supabase_client=FakeSupabaseTableClient())
    assert isinstance(repository, SupabaseRepository)


def test_enabled_tavily_and_openai_select_live_boundaries():
    service = build_service(
        enabled_settings,
        InMemoryRepository(),
        openai_transport=recording_openai_transport,
        tavily_transport=recording_tavily_transport,
    )
    assert service.vendor_discovery_source == "tavily"
    created = service.create_job_from_document("SYNTHETIC moving inventory")
    assert created.job_spec.intake_source is IntakeSource.DOCUMENT
```

Add a test where an enabled Tavily transport raises and assert no synthetic vendors are returned. Add a test where an enabled Supabase client raises and assert no memory-created job exists.

- [ ] **Step 2: Run focused tests and verify live builders are absent**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_integrations_wiring.py -q`  
Expected: FAIL importing `build_repository` or `LiveIntelligenceProvider`.

- [ ] **Step 3: Build one repository and service per application settings snapshot**

Keep the default app's in-memory repository available to existing test fixtures, but store the selected runtime objects on FastAPI state:

```python
def create_app() -> FastAPI:
    settings = Settings.from_env()
    repository = build_repository(settings)
    service = build_service(settings, repository)
    application = FastAPI(
        title="VeraMove API",
        summary="Mock-first moving-services negotiation API",
        version="0.1.0",
    )
    application.state.settings = settings
    application.state.repository = repository
    application.state.service = service
```

Keep the existing CORS middleware, exception handlers, router inclusion, and return statement unchanged after these state assignments.

Dependencies become:

```python
def get_service(request: Request) -> VeraMoveService:
    return request.app.state.service


def get_runtime_repository(request: Request):
    return request.app.state.repository
```

Update the autouse test reset fixture to reset only the default app's in-memory repository. Never call `reset()` on a Supabase repository.

- [ ] **Step 4: Compose OpenAI, Tavily, and Supabase independently**

`build_repository()` returns memory unless `settings.supabase.enabled`; enabled mode calls `require_supabase_config()` and builds `SupabaseRepository` with a `SupabasePostgrestClient`.

`build_service()`:

- retains mock voice when `APP_MODE=mock` and live voice only when `APP_MODE=live`;
- uses `MockVendorDiscoveryGateway` unless Tavily is enabled;
- uses `MockIntelligenceProvider` unless OpenAI is enabled;
- in OpenAI mode, creates `OpenAIResponsesClient`, `OpenAIDocumentParser`, `LiveIntelligenceProvider`, and `OpenAIRecommendationNarrator(OpenAIResponsesNarrativeClient(api_key=config.api_key, api_base_url=config.api_base_url, transport=openai_transport), model=config.recommendation_model)`;
- passes the narrator separately to `VeraMoveService`;
- does not require OpenAI, Tavily, or Supabase merely because voice mode is live.

- [ ] **Step 5: Add live document intelligence without model-planned leverage**

```python
class LiveIntelligenceProvider:
    def __init__(self, document_parser, negotiation_gateway) -> None:
        self._document_parser = document_parser
        self._negotiation_gateway = negotiation_gateway

    def extract_document(self, document_text: str) -> JobSpecV1:
        if not document_text.strip():
            raise DomainConflict("Document text is required")
        return self._document_parser.parse_document(
            document_text.encode("utf-8"),
            "text/plain",
            "document-text-input",
        ).job_spec

    def negotiate(self, job_spec, quotes, verified_competitor):
        return self._negotiation_gateway.negotiate(
            job_spec, quotes, verified_competitor
        )
```

Negotiation planning remains deterministic until the backend/voice owner supplies a separately reviewed model contract; OpenAI never creates competing-quote evidence.

- [ ] **Step 6: Wire summary-only narration after recommendation construction**

After `_build_recommendation()` has copied canonical rankings and evidence, call:

```python
if self._recommendation_narrator is not None:
    summary = self._recommendation_narrator.explain(
        record.job_spec,
        recommendation.rankings,
        recommendation.hidden_fee_findings,
    )
    recommendation = recommendation.model_copy(update={"summary": summary}, deep=True)
```

Test that every field except `summary` equals the deterministic result.

- [ ] **Step 7: Run wiring, API, service, and webhook tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_integrations_wiring.py services/api/tests/test_api.py services/api/tests/test_service.py services/api/tests/test_webhooks.py services/api/tests/test_live_voice.py -q`  
Expected: PASS.

- [ ] **Step 8: Commit runtime composition**

```bash
git add services/api/app/api/dependencies.py services/api/app/main.py services/api/app/orchestration services/api/tests/test_live_integrations_wiring.py services/api/tests/conftest.py
git commit -m "feat(api): compose independent live integrations"
```

---

### Task 7: Generated contracts, deployment configuration, documentation, and final validation

**Files:**
- Modify: `render.yaml`
- Modify: `README.md`
- Modify: `docs/integration-boundaries.md`
- Modify: `docs/intelligence-handoff.md`
- Modify: `docs/backend-voice-runbook.md`
- Modify: `packages/contracts/openapi.json` through generation only
- Modify: `apps/web/src/api/schema.d.ts` through generation only
- Modify: relevant documentation tests under `services/api/tests/`

**Interfaces:**
- Produces: deployment-safe disabled defaults and manual activation instructions.
- Produces: regenerated canonical OpenAPI and TypeScript artifacts.
- Validates: complete mock lifecycle, live adapter request shapes with fakes, 14/14 intelligence evals, and full repository checks.

- [ ] **Step 1: Add Render variables without activating providers**

```yaml
      - key: OPENAI_ENABLED
        value: "false"
      - key: OPENAI_API_KEY
        sync: false
      - key: TAVILY_ENABLED
        value: "false"
      - key: TAVILY_API_KEY
        sync: false
      - key: SUPABASE_ENABLED
        value: "false"
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SECRET_KEY
        sync: false
```

Keep `LIVE_CALLS_ENABLED=false`. Do not place real values in YAML.

- [ ] **Step 2: Document exact behavior and activation order**

README and runbook must state:

1. Run the two Supabase migrations in order.
2. Enter `SUPABASE_URL` and backend-only `SUPABASE_SECRET_KEY`; enable Supabase and verify a synthetic job survives a Render redeploy.
3. Enter `TAVILY_API_KEY`; enable Tavily and verify `source=tavily` plus provenance.
4. Enter `OPENAI_API_KEY`; enable OpenAI and verify a synthetic text document produces an unconfirmed valid JobSpec.
5. Keep billable voice disabled during integration tests.
6. Never paste keys into source, issues, recordings, logs, or chat.

State the remaining limitation: a live ElevenLabs post-call webhook is authenticated and persisted but still does not materialize a canonical quote/report.

- [ ] **Step 3: Regenerate public contract artifacts**

Run: `.venv/bin/python scripts/export_openapi.py`  
Expected: `packages/contracts/openapi.json` changes only for the intended source union and directly related schemas.  
Run: `npm --prefix apps/web run generate:api`  
Expected: `apps/web/src/api/schema.d.ts` reflects `"synthetic_mock" | "tavily"`; no handwritten frontend changes.

- [ ] **Step 4: Run targeted backend tests**

Run:

```bash
.venv/bin/python -m pytest \
  services/api/tests/test_live_integrations_config.py \
  services/api/tests/test_openai_live.py \
  services/api/tests/test_tavily_live.py \
  services/api/tests/test_supabase_client.py \
  services/api/tests/test_supabase_repository.py \
  services/api/tests/test_live_integrations_wiring.py -q
```

Expected: PASS with zero external calls.

- [ ] **Step 5: Run deterministic evaluations**

Run: `.venv/bin/python -m evals.run`  
Expected: `14/14 evaluations passed.` or a larger fully passing set.

- [ ] **Step 6: Run the complete repository gate**

Run: `python scripts/check.py`  
Expected: Ruff, all pytest tests, OpenAPI export, API type generation, TypeScript typecheck, Vitest, and Vite production build all pass.

- [ ] **Step 7: Run secret and scope checks**

Run: `git diff --check`  
Expected: no output.  
Run: `rg -n "sk-|tvly-|sb_secret_|service_role.*[A-Za-z0-9]" --glob '!docs/superpowers/**' --glob '!package-lock.json' .`  
Expected: no real credential-like value; documented variable names are allowed.  
Run: `git status --short`  
Expected: only intended integration, generated-contract, deployment, and documentation files.

- [ ] **Step 8: Commit deployment and generated artifacts**

```bash
git add render.yaml README.md docs/integration-boundaries.md docs/intelligence-handoff.md docs/backend-voice-runbook.md packages/contracts/openapi.json apps/web/src/api/schema.d.ts services/api/tests
git commit -m "docs(integrations): document live provider rollout"
```

- [ ] **Step 9: Push the implementation branch after final review**

Run: `git push origin deploy/veramove-demo`  
Expected: remote branch advances without force-push.

Do not enable external providers automatically. Hand the user the exact Render variables to enter and perform one provider at a time with `LIVE_CALLS_ENABLED=false`.
