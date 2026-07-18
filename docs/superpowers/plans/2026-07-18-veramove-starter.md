# VeraMove Hackathon Starter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean, runnable VeraMove hackathon starter whose mock workflow creates and confirms a moving job, collects three evidence-backed quotes, negotiates a measurable improvement, and returns a ranked recommendation.

**Architecture:** FastAPI is the canonical contract owner and exposes a small application service backed by repository and integration protocols. Mock mode wires deterministic in-memory and fixture-backed implementations; the Vite/React frontend consumes only OpenAPI-generated types through one client. Python scripts provide one-command setup, development, validation, and contract export.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, pytest, Ruff, Vite, React, TypeScript, Tailwind CSS, React Router, Vitest, Testing Library, openapi-typescript, PostgreSQL/Supabase SQL.

## Global Constraints

- Work directly in the current repository and keep it independent from VeraAI.
- Default to `APP_MODE=mock`; a fresh clone must run without API credentials or Supabase.
- Never call ElevenLabs, Twilio, OpenAI, Tavily, or Supabase from this starter.
- Put all external capabilities behind protocols and deterministic mock adapters.
- FastAPI-generated OpenAPI at `packages/contracts/openapi.json` is the canonical API contract.
- Frontend domain types are generated from OpenAPI; do not maintain parallel handwritten contracts.
- Commit SQL migrations, but do not require a local Supabase instance.
- Do not add authentication, payments, booking, Docker, or a monorepo framework.
- Commit no secrets, real phone numbers, real home addresses, recordings, local databases, or personal information.
- Label every demo fixture synthetic.
- The final required commit message is `chore: bootstrap VeraMove hackathon repository`.

## File and Interface Map

### Backend

- `services/api/app/contracts/models.py`: all required versioned Pydantic domain and API models.
- `services/api/app/core/config.py`: environment-backed settings with mock defaults.
- `services/api/app/core/errors.py`: typed domain errors.
- `services/api/app/core/state_machine.py`: legal job-state transitions.
- `services/api/app/repositories/base.py`: `JobRepository` protocol.
- `services/api/app/repositories/memory.py`: process-local aggregate and webhook storage.
- `services/api/app/integrations/elevenlabs/base.py`: voice/call protocol, including the future Twilio boundary.
- `services/api/app/integrations/elevenlabs/mock.py`: deterministic call outcomes.
- `services/api/app/integrations/openai/base.py`: negotiation protocol.
- `services/api/app/integrations/openai/mock.py`: deterministic improved quote.
- `services/api/app/integrations/tavily/base.py`: vendor-discovery protocol.
- `services/api/app/integrations/tavily/mock.py`: deterministic vendor list.
- `services/api/app/orchestration/fixtures.py`: typed synthetic-fixture loader.
- `services/api/app/orchestration/service.py`: `VeraMoveService` workflow methods.
- `services/api/app/api/dependencies.py`: singleton mock wiring.
- `services/api/app/api/router.py`: all requested route handlers.
- `services/api/app/main.py`: FastAPI factory, exception mapping, and CORS for port 5173.

### Frontend

- `apps/web/src/api/schema.d.ts`: generated OpenAPI TypeScript types.
- `apps/web/src/api/client.ts`: single typed HTTP client.
- `apps/web/src/pages/*.tsx`: home, intake, confirmation, calls, and report routes.
- `apps/web/src/App.tsx`: router declaration.
- `apps/web/src/index.css`: Tailwind layers and minimal shared styling.
- `apps/web/src/test/*.test.tsx`: route and client-state tests.

### Shared, Data, and Operations

- `configs/moving.yaml`: all vertical-specific questions and rules.
- `data/demo/*.json`: synthetic move, vendors, policy cards, quotes, evidence, and recommendation.
- `supabase/migrations/202607180001_initial_schema.sql`: optional persistence schema.
- `scripts/bootstrap.py`, `scripts/dev.py`, `scripts/check.py`, `scripts/export_openapi.py`: cross-platform developer commands.
- `docs/*.md`, root governance files, and `.github/*`: onboarding, boundaries, ownership, and CI.

---

### Task 1: Establish Root Policy, Python Package, and Contract Tests

**Files:**

- Create: `.gitignore`
- Create: `.env.example`
- Create: `LICENSE`
- Create: `services/__init__.py`
- Create: `services/api/__init__.py`
- Create: `services/api/app/__init__.py`
- Create: `services/api/app/contracts/__init__.py`
- Create: `services/api/app/contracts/models.py`
- Create: `services/api/app/core/__init__.py`
- Create: `services/api/app/core/config.py`
- Create: `services/api/app/core/errors.py`
- Create: `services/api/app/core/state_machine.py`
- Create: `services/api/tests/test_contracts.py`
- Create: `services/api/tests/test_state_machine.py`
- Create: `services/api/requirements.txt`
- Create: `services/api/requirements-dev.txt`
- Create: `pyproject.toml`

**Interfaces:**

- Produces: `JobSpecV1`, `OriginDestinationAccess`, `InventoryItem`, `MovingServices`, `Vendor`, `FeeLineItem`, `TranscriptEvidence`, `QuoteV1`, `CallRecord`, `CallOutcome`, `RecommendationV1`, `JobRecord`, and all enums.
- Produces: `validate_transition(current: JobState, target: JobState) -> None`.
- Produces: `Settings.from_env() -> Settings` with `app_mode="mock"`, `api_host="127.0.0.1"`, and `api_port=8000` defaults.

- [ ] **Step 1: Write contract tests before models**

Create tests that build a complete two-bedroom `JobSpecV1`, reject an empty inventory and unsupported currency, serialize decimal quote totals, constrain `CallOutcomeType` to the four named values, and allow nullable VeraAI identifiers:

```python
def test_job_spec_accepts_nullable_future_vera_ids(job_spec_payload):
    model = JobSpecV1.model_validate(job_spec_payload)
    assert model.source_context.vera_user_id is None
    assert model.source_context.vera_property_id is None


def test_call_outcome_enum_is_closed():
    assert {value.value for value in CallOutcomeType} == {
        "itemized_quote",
        "callback_commitment",
        "documented_decline",
        "failed",
    }


def test_quote_rejects_non_usd_currency(quote_payload):
    quote_payload["currency"] = "EUR"
    with pytest.raises(ValidationError):
        QuoteV1.model_validate(quote_payload)
```

- [ ] **Step 2: Verify the tests fail before implementation**

Run: `python -m pytest services/api/tests/test_contracts.py -q`

Expected: collection fails because `services.api.app.contracts.models` does not exist.

- [ ] **Step 3: Implement complete Pydantic contracts**

Use UUID identifiers, `date`, timezone-aware `datetime`, `Decimal`, `HttpUrl`, constrained counts and distances, `extra="forbid"`, and these exact state/outcome values:

```python
class JobState(StrEnum):
    DRAFT = "draft"
    INTAKE_COMPLETE = "intake_complete"
    CONFIRMED = "confirmed"
    CALLING = "calling"
    QUOTES_READY = "quotes_ready"
    NEGOTIATING = "negotiating"
    COMPLETED = "completed"
    FAILED = "failed"


class CallOutcomeType(StrEnum):
    ITEMIZED_QUOTE = "itemized_quote"
    CALLBACK_COMMITMENT = "callback_commitment"
    DOCUMENTED_DECLINE = "documented_decline"
    FAILED = "failed"
```

`JobSpecV1` must expose every field from the approved specification. `QuoteV1` must expose vendor, job version, fee line items, both totals, currency, deposit, binding status, availability, concessions, red flags, provisional and verified dictionaries, verification status, transcript evidence, and recording URL. Add aggregate response models rather than returning untyped dictionaries.

- [ ] **Step 4: Write and implement state-transition tests**

```python
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (JobState.DRAFT, JobState.INTAKE_COMPLETE),
        (JobState.INTAKE_COMPLETE, JobState.CONFIRMED),
        (JobState.CONFIRMED, JobState.CALLING),
        (JobState.CALLING, JobState.QUOTES_READY),
        (JobState.QUOTES_READY, JobState.NEGOTIATING),
        (JobState.NEGOTIATING, JobState.COMPLETED),
    ],
)
def test_happy_path_transitions(current, target):
    validate_transition(current, target)


def test_illegal_transition_has_clear_message():
    with pytest.raises(InvalidStateTransition, match="confirmed -> completed"):
        validate_transition(JobState.CONFIRMED, JobState.COMPLETED)
```

Use an explicit transition map. Permit `FAILED` from `intake_complete`, `confirmed`, `calling`, `quotes_ready`, and `negotiating`; permit no transitions from terminal states.

- [ ] **Step 5: Run focused tests and Ruff**

Run: `python -m pytest services/api/tests/test_contracts.py services/api/tests/test_state_machine.py -q`

Expected: all tests pass.

Run: `python -m ruff check services/api/app/contracts services/api/app/core services/api/tests/test_contracts.py services/api/tests/test_state_machine.py`

Expected: `All checks passed!`

### Task 2: Add Synthetic Fixtures, Repository, and Mock Integration Boundaries

**Files:**

- Create: `data/demo/README.md`
- Create: `data/demo/job.json`
- Create: `data/demo/vendors.json`
- Create: `data/demo/vendor_policy_cards.json`
- Create: `data/demo/initial_quotes.json`
- Create: `data/demo/negotiated_quote.json`
- Create: `data/demo/transcript_evidence.json`
- Create: `data/demo/recommendation.json`
- Create: `services/api/app/repositories/__init__.py`
- Create: `services/api/app/repositories/base.py`
- Create: `services/api/app/repositories/memory.py`
- Create: `services/api/app/integrations/__init__.py`
- Create: `services/api/app/integrations/elevenlabs/__init__.py`
- Create: `services/api/app/integrations/elevenlabs/base.py`
- Create: `services/api/app/integrations/elevenlabs/mock.py`
- Create: `services/api/app/integrations/openai/__init__.py`
- Create: `services/api/app/integrations/openai/base.py`
- Create: `services/api/app/integrations/openai/mock.py`
- Create: `services/api/app/integrations/tavily/__init__.py`
- Create: `services/api/app/integrations/tavily/base.py`
- Create: `services/api/app/integrations/tavily/mock.py`
- Create: `services/api/app/orchestration/__init__.py`
- Create: `services/api/app/orchestration/fixtures.py`
- Create: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**

- Consumes: all domain models from Task 1.
- Produces: `JobRepository` methods `create`, `get`, `save`, `record_webhook`, and `reset`.
- Produces: `VoiceVendorGateway.create_calls(job_spec) -> list[CallRecord]`.
- Produces: `NegotiationGateway.negotiate(job_spec, quotes, verified_competitor) -> QuoteV1`.
- Produces: `VendorDiscoveryGateway.discover(origin, destination) -> list[Vendor]`.
- Produces: `DemoFixtures.load_*()` typed fixture methods.

- [ ] **Step 1: Create complete synthetic JSON fixtures**

Use stable UUIDs and fictional names: `ClearPath Movers` is transparent and itemized, `BudgetLift Moving` reveals stairs/long-carry/fuel fees only when questioned, and `Northstar Relocation` starts premium and negotiates after a verified competing quote. Use `example.com` recording links and non-dialable vendor labels. Make the negotiated Northstar total lower than its original total and include the verified ClearPath quote identifier in its evidence.

- [ ] **Step 2: Write adapter and repository tests**

```python
def test_repository_returns_defensive_copy(memory_repository, job_record):
    memory_repository.create(job_record)
    first = memory_repository.get(job_record.job_spec.job_id)
    first.state = JobState.FAILED
    assert memory_repository.get(job_record.job_spec.job_id).state != JobState.FAILED


def test_mock_voice_gateway_returns_three_itemized_calls(mock_voice, job_spec):
    calls = mock_voice.create_calls(job_spec)
    assert len(calls) == 3
    assert all(call.outcome.type is CallOutcomeType.ITEMIZED_QUOTE for call in calls)


def test_mock_negotiation_improves_total(mock_negotiator, job_spec, quotes):
    improved = mock_negotiator.negotiate(job_spec, quotes, quotes[0])
    assert improved.negotiated_total < improved.original_total
    assert improved.verification_status is VerificationStatus.VERIFIED
```

- [ ] **Step 3: Verify focused tests fail**

Run: `python -m pytest services/api/tests/test_repository_and_adapters.py -q`

Expected: imports fail because repository and adapter implementations do not exist.

- [ ] **Step 4: Implement protocols and deterministic mocks**

Use `typing.Protocol` for boundaries. The memory repository stores `JobRecord.model_dump(mode="json")` under a lock and reconstructs models on reads, ensuring callers cannot mutate stored state by aliasing. `record_webhook(idempotency_key, payload)` returns `False` for duplicate keys and `True` for the first event.

The mock gateways load only files through `DemoFixtures`; they must contain no HTTP clients, SDK imports, credentials, or network calls.

- [ ] **Step 5: Run repository and adapter tests**

Run: `python -m pytest services/api/tests/test_repository_and_adapters.py -q`

Expected: all tests pass.

### Task 3: Implement Workflow Orchestration and the Typed API

**Files:**

- Create: `services/api/app/orchestration/service.py`
- Create: `services/api/app/api/__init__.py`
- Create: `services/api/app/api/dependencies.py`
- Create: `services/api/app/api/router.py`
- Create: `services/api/app/main.py`
- Create: `services/api/tests/conftest.py`
- Create: `services/api/tests/test_service.py`
- Create: `services/api/tests/test_api.py`

**Interfaces:**

- Consumes: Task 1 contracts/state rules and Task 2 repository/gateways.
- Produces: `VeraMoveService.create_job`, `get_job`, `confirm_job`, `start_calls`, `negotiate`, `get_report`, `handle_elevenlabs_webhook`, and `discover_vendors`.
- Produces: `create_app() -> FastAPI` and module-level `app`.

- [ ] **Step 1: Write orchestration tests for the full stateful loop**

```python
def test_mock_workflow(service, job_spec):
    created = service.create_job(job_spec)
    assert created.state is JobState.INTAKE_COMPLETE

    confirmed = service.confirm_job(job_spec.job_id)
    assert confirmed.state is JobState.CONFIRMED
    assert confirmed.job_spec.confirmed is True
    assert confirmed.job_spec.confirmed_at is not None

    called = service.start_calls(job_spec.job_id)
    assert called.state is JobState.QUOTES_READY
    assert len(called.calls) == 3
    assert len(called.quotes) == 3

    completed = service.negotiate(job_spec.job_id)
    assert completed.state is JobState.COMPLETED
    assert len(completed.quotes) == 4
    assert completed.quotes[-1].negotiated_total < completed.quotes[-1].original_total

    report = service.get_report(job_spec.job_id)
    assert report.rankings[0].evidence_ids
```

Also test duplicate creation, repeated confirmation, calls before confirmation, negotiation before quotes, and report before completion. Each must raise a specific domain conflict.

- [ ] **Step 2: Implement `VeraMoveService`**

Keep state transitions synchronous and explicit. Confirmation uses `model_copy(update={"confirmed": True, "confirmed_at": now_utc})`. Starting calls persists the `calling` state before gateway work, then `quotes_ready`. Negotiation requires at least one verified competitor, persists `negotiating`, invokes the mock gateway, verifies measurable price or term improvement, attaches the improved quote, creates the synthetic recommendation, and persists `completed`.

- [ ] **Step 3: Write API tests for every route and error mapping**

```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock", "service": "veramove-api"}


def test_api_happy_path(client, job_spec_payload):
    created = client.post("/api/jobs", json=job_spec_payload)
    job_id = created.json()["job_spec"]["job_id"]
    assert client.post(f"/api/jobs/{job_id}/confirm").status_code == 200
    calls = client.post(f"/api/jobs/{job_id}/calls")
    assert len(calls.json()["calls"]) == 3
    negotiated = client.post(f"/api/jobs/{job_id}/negotiate")
    assert negotiated.json()["state"] == "completed"
    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.json()["rankings"][0]["evidence_ids"]


def test_illegal_api_transition_is_conflict(client, created_job_id):
    response = client.post(f"/api/jobs/{created_job_id}/calls")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
```

Cover `GET /api/jobs/{job_id}`, `POST /api/webhooks/elevenlabs` including duplicate idempotency, `GET /api/vendors/discover`, and unknown-job 404s.

- [ ] **Step 4: Implement FastAPI routes and application wiring**

Use response models for every route. Map `ResourceNotFound` to 404 and domain conflicts to 409. Configure CORS only for `http://127.0.0.1:5173` and `http://localhost:5173`. Reject non-mock app mode with a startup configuration error rather than silently enabling a real adapter.

- [ ] **Step 5: Run the complete backend suite**

Run: `python -m pytest services/api/tests -q`

Expected: all backend tests pass.

Run: `python -m ruff check services scripts`

Expected: `All checks passed!`

### Task 4: Centralize Moving Rules and Add Optional Supabase Schema

**Files:**

- Create: `configs/moving.yaml`
- Create: `supabase/migrations/202607180001_initial_schema.sql`
- Create: `evals/mock_workflow_cases.json`
- Create: `agents/intake/README.md`
- Create: `agents/negotiator/README.md`
- Create: `services/api/tests/test_project_assets.py`

**Interfaces:**

- Consumes: fee and outcome enum values from Task 1.
- Produces: stable YAML keys `intake_questions`, `required_job_spec_fields`, `fee_categories`, `red_flag_rules`, `negotiation_levers`, `required_call_outcomes`, and `honesty_constraints`.
- Produces: seven PostgreSQL tables with JSONB versioned payloads and idempotency protection.

- [ ] **Step 1: Write structural asset tests**

```python
def test_moving_config_contains_required_vertical_rules(repo_root):
    config = yaml.safe_load((repo_root / "configs/moving.yaml").read_text())
    assert config["red_flag_rules"]["below_comparison_median_percent"] == 30
    assert set(config["required_call_outcomes"]) == {
        "itemized_quote", "callback_commitment", "documented_decline", "failed"
    }
    assert "long_carry" in config["fee_categories"]


def test_migration_has_all_tables_and_idempotency(repo_root):
    sql = (repo_root / "supabase/migrations/202607180001_initial_schema.sql").read_text()
    for table in ("jobs", "vendors", "calls", "quotes", "transcript_evidence", "recommendations", "event_log"):
        assert f"create table if not exists {table}" in sql.lower()
    assert "idempotency_key" in sql
    assert "jsonb" in sql.lower()
```

- [ ] **Step 2: Create `moving.yaml` with the exact domain configuration**

Include every fee category from the brief, direct intake questions for all required `JobSpecV1` fields, honest disclosure rules, and negotiation levers such as verified competitor matching, deposit reduction, fee waiver, scheduling flexibility, and service upgrades. Runtime mocks may validate against this file but must not duplicate its thresholds.

- [ ] **Step 3: Create the SQL migration**

Enable `pgcrypto`, use `uuid default gen_random_uuid()` keys, `timestamptz` timestamps, foreign keys with sensible deletion behavior, JSONB payload columns, indexes on job/vendor/call foreign keys and state/status, and a unique non-null `event_log.idempotency_key`.

- [ ] **Step 4: Add evaluation and agent-boundary documentation**

The evaluation JSON must assert three calls, four total quotes after negotiation, measurable improvement, evidence-backed rankings, and detection of the hidden-fee vendor. Agent READMEs must state inputs, structured outputs, ownership, honesty rules, and that only mock adapters are callable.

- [ ] **Step 5: Run asset tests**

Run: `python -m pytest services/api/tests/test_project_assets.py -q`

Expected: all tests pass.

### Task 5: Export Canonical OpenAPI and Generate Frontend Types

**Files:**

- Create: `scripts/__init__.py`
- Create: `scripts/export_openapi.py`
- Generate: `packages/contracts/openapi.json`
- Create: `packages/contracts/README.md`

**Interfaces:**

- Consumes: `services.api.app.main.app`.
- Produces: deterministic, newline-terminated, sorted JSON at `packages/contracts/openapi.json`.
- Produces: frontend generation command `npm run generate:api`.

- [ ] **Step 1: Add an export test**

```python
def test_export_openapi_contains_required_routes(tmp_path):
    target = tmp_path / "openapi.json"
    export_openapi(target)
    document = json.loads(target.read_text())
    assert document["info"]["title"] == "VeraMove API"
    for path in ("/health", "/api/jobs", "/api/jobs/{job_id}", "/api/webhooks/elevenlabs", "/api/vendors/discover"):
        assert path in document["paths"]
```

- [ ] **Step 2: Implement deterministic export**

```python
def export_openapi(target: Path = DEFAULT_TARGET) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    target.write_text(payload, encoding="utf-8")
    return target
```

Resolve the repository root from `Path(__file__).resolve().parents[1]`, not the current working directory.

- [ ] **Step 3: Export and inspect the contract**

Run: `python scripts/export_openapi.py`

Expected: `packages/contracts/openapi.json` exists and reports all requested paths and named schemas.

### Task 6: Build the Typed Vite/React Placeholder Application

**Files:**

- Create: `apps/web/package.json`
- Create: `apps/web/package-lock.json`
- Create: `apps/web/index.html`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/tsconfig.node.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/tailwind.config.ts`
- Create: `apps/web/postcss.config.cjs`
- Create: `apps/web/src/vite-env.d.ts`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/index.css`
- Create: `apps/web/src/api/client.ts`
- Generate: `apps/web/src/api/schema.d.ts`
- Create: `apps/web/src/components/Layout.tsx`
- Create: `apps/web/src/components/AsyncState.tsx`
- Create: `apps/web/src/pages/HomePage.tsx`
- Create: `apps/web/src/pages/IntakePage.tsx`
- Create: `apps/web/src/pages/ConfirmPage.tsx`
- Create: `apps/web/src/pages/CallsPage.tsx`
- Create: `apps/web/src/pages/ReportPage.tsx`
- Create: `apps/web/src/test/setup.ts`
- Create: `apps/web/src/test/routes.test.tsx`

**Interfaces:**

- Consumes: generated `paths` and `components` from `src/api/schema.d.ts`.
- Produces: `api.health`, `api.createJob`, `api.getJob`, `api.confirmJob`, `api.startCalls`, `api.negotiate`, and `api.getReport`.
- Produces: routes `/`, `/intake`, `/confirm/:jobId`, `/calls/:jobId`, and `/report/:jobId`.

- [ ] **Step 1: Create frontend manifest and install dependencies**

Use scripts:

```json
{
  "dev": "vite --host 127.0.0.1 --port 5173",
  "generate:api": "openapi-typescript ../../packages/contracts/openapi.json -o src/api/schema.d.ts",
  "typecheck": "tsc --noEmit",
  "test": "vitest run",
  "build": "tsc -b && vite build"
}
```

Runtime dependencies are React, React DOM, and React Router DOM. Development dependencies are Vite, TypeScript, Tailwind CSS, PostCSS, Autoprefixer, openapi-typescript, Vitest, jsdom, Testing Library React, Testing Library DOM, and React type packages.

Run: `npm install --prefix apps/web`

Expected: `apps/web/package-lock.json` is generated without errors.

- [ ] **Step 2: Generate API types before writing the client**

Run: `npm run generate:api --prefix apps/web`

Expected: `apps/web/src/api/schema.d.ts` contains `JobSpecV1`, `QuoteV1`, `CallRecord`, and `RecommendationV1` from FastAPI OpenAPI.

- [ ] **Step 3: Write route tests**

```tsx
it("renders the homepage and demo status", async () => {
  vi.spyOn(api, "health").mockResolvedValue({ status: "ok", mode: "mock", service: "veramove-api" });
  render(<MemoryRouter initialEntries={["/"]}><AppRoutes /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "VeraMove" })).toBeInTheDocument();
  expect(await screen.findByText("API connected")).toBeInTheDocument();
  expect(screen.getByText("Demo mode")).toBeInTheDocument();
});


it("renders an error state when a job cannot be loaded", async () => {
  vi.spyOn(api, "getJob").mockRejectedValue(new Error("Job not found"));
  render(<MemoryRouter initialEntries={["/confirm/missing"]}><AppRoutes /></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Job not found");
});
```

- [ ] **Step 4: Implement one typed client and all route placeholders**

Use `VITE_API_BASE_URL ?? "http://127.0.0.1:8000"`. A shared request helper must parse FastAPI error details and throw an `Error` with a readable message. Infer request/response types from generated `paths`; route files must not declare domain interfaces.

The intake page submits the committed synthetic two-bedroom payload. Confirmation, call, and report pages load their job IDs from React Router, show a loading state immediately, show an alert on failure, and link to the next stage on success.

- [ ] **Step 5: Run frontend verification**

Run: `npm run typecheck --prefix apps/web`

Expected: no TypeScript errors.

Run: `npm test --prefix apps/web`

Expected: all Vitest tests pass.

Run: `npm run build --prefix apps/web`

Expected: Vite produces `apps/web/dist` successfully.

### Task 7: Implement Cross-Platform Bootstrap, Development, and Check Scripts

**Files:**

- Create: `scripts/bootstrap.py`
- Create: `scripts/dev.py`
- Create: `scripts/check.py`
- Create: `services/api/tests/test_scripts.py`

**Interfaces:**

- Consumes: backend requirements, frontend package scripts, and OpenAPI exporter.
- Produces: the exact public commands `python scripts/bootstrap.py`, `python scripts/dev.py`, and `python scripts/check.py`.

- [ ] **Step 1: Write command-construction tests**

```python
def test_bootstrap_uses_venv_python(repo_root):
    assert venv_python(repo_root).name in {"python", "python.exe"}


def test_check_pipeline_has_required_order():
    labels = [step.label for step in build_check_steps()]
    assert labels == [
        "Ruff", "pytest", "OpenAPI export", "API type generation",
        "frontend typecheck", "frontend tests", "frontend build",
    ]
```

- [ ] **Step 2: Implement `bootstrap.py`**

Create `.venv` with `venv.EnvBuilder(with_pip=True)`, install `requirements-dev.txt` (which includes `-r requirements.txt`), run OpenAPI export with the venv interpreter, run `npm install --prefix apps/web`, run the frontend generation script, and print the two next commands. Resolve platform-specific executable names with `os.name` and use `subprocess.run(..., check=True)` with argument lists.

- [ ] **Step 3: Implement `check.py`**

Prefer `.venv` Python when present and otherwise use `sys.executable`. Run the required steps in the exact order through a small immutable `CheckStep` model. Print a clear banner for each step and propagate the first nonzero exit code.

- [ ] **Step 4: Implement `dev.py`**

Start Uvicorn as `.venv/bin/python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000` and the frontend as `npm run dev --prefix apps/web`. On Ctrl+C or early child failure, terminate both, wait briefly, then kill only remaining child processes. Do not open a browser automatically.

- [ ] **Step 5: Run script tests**

Run: `python -m pytest services/api/tests/test_scripts.py -q`

Expected: all tests pass without starting servers or installing dependencies.

### Task 8: Complete Documentation, Ownership, and Continuous Integration

**Files:**

- Create: `README.md`
- Create: `AGENTS.md`
- Create: `CONTRIBUTING.md`
- Create: `CODEOWNERS`
- Create: `docs/architecture.md`
- Create: `docs/api-contract.md`
- Create: `docs/integration-boundaries.md`
- Create: `docs/demo-ux.md`
- Create: `.github/pull_request_template.md`
- Create: `.github/workflows/check.yml`
- Create: `services/api/tests/test_documentation.py`

**Interfaces:**

- Produces: contributor-facing setup and ownership contract.
- Produces: CI on pull requests and pushes to `main`, with Python and Node setup followed by bootstrap/check-compatible dependency installation and `python scripts/check.py`.

- [ ] **Step 1: Add documentation coverage tests**

```python
@pytest.mark.parametrize(
    "heading",
    [
        "Product summary", "Architecture", "Repository structure", "Prerequisites",
        "Five-minute local setup", "Environment variables", "Mock mode", "Commands",
        "API routes", "Team branch conventions", "Known limitations",
        "Synthetic data", "Future VeraAI integration",
    ],
)
def test_readme_has_required_sections(readme_text, heading):
    assert f"## {heading}" in readme_text


def test_agents_declares_all_member_ownership(agents_text):
    for member in range(1, 5):
        assert f"Member {member}" in agents_text
    assert "Do not rewrite another member's subsystem" in agents_text
```

- [ ] **Step 2: Write the root README and contributor files**

Document every required README section, the exact public commands, all routes, expected ports, `APP_MODE=mock`, synthetic disclosure, branch naming such as `member-1/orchestration`, and the nullable future Vera identifiers. `CODEOWNERS` uses obvious placeholder handles such as `@member-1` without claiming real accounts.

- [ ] **Step 3: Write `AGENTS.md` with exact ownership boundaries**

Copy the supplied Member 1 through Member 4 directories verbatim, state the contract-change process (edit Pydantic, update backend tests, export OpenAPI, regenerate frontend types, run check, obtain owners' review), require `python scripts/check.py` before PRs, and include no-secrets/no-real-PII rules.

- [ ] **Step 4: Write architecture and integration documents**

Explain the data flow, state machine, canonical contract generation, mock adapter boundary, Twilio's future role, optional Supabase schema, and demo UX. Do not describe external integrations as functional.

- [ ] **Step 5: Create CI**

Use `actions/checkout`, `actions/setup-python` with 3.11, and `actions/setup-node` with 20 and npm cache rooted at `apps/web/package-lock.json`. Install backend dev requirements and frontend packages, then run `python scripts/check.py`. Include no secret references or deployment jobs.

- [ ] **Step 6: Run documentation tests**

Run: `python -m pytest services/api/tests/test_documentation.py -q`

Expected: all tests pass.

### Task 9: Bootstrap, Full Validation, Runtime Smoke Test, and Final Commit

**Files:**

- Modify: any file implicated by failed acceptance evidence.
- Generate/update: `packages/contracts/openapi.json`
- Generate/update: `apps/web/src/api/schema.d.ts`
- Generate: `.venv` and `apps/web/node_modules` locally; keep both ignored.
- Remove after verification: `apps/web/dist` if it is not intentionally committed.

**Interfaces:**

- Consumes: all prior tasks.
- Produces: a fresh-clone-equivalent validated repository and final Git commit.

- [ ] **Step 1: Run the required bootstrap command**

Run: `python scripts/bootstrap.py`

Expected: `.venv` is created, Python and Node dependencies install, OpenAPI and TypeScript types regenerate, and next steps print without credential prompts.

- [ ] **Step 2: Run all checks and fix every failure**

Run: `python scripts/check.py`

Expected: Ruff, pytest, OpenAPI export, type generation, typecheck, frontend tests, and frontend build all pass; command exits zero.

- [ ] **Step 3: Verify generated artifacts are clean and deterministic**

Run `python scripts/export_openapi.py` and `npm run generate:api --prefix apps/web` again, then inspect `git diff --exit-code packages/contracts/openapi.json apps/web/src/api/schema.d.ts`.

Expected: no differences.

- [ ] **Step 4: Start both servers and smoke-test runtime behavior**

Run `python scripts/dev.py` in a controlled terminal session. Verify:

- `GET http://127.0.0.1:8000/health` returns 200 and mock mode.
- `GET http://127.0.0.1:8000/docs` returns 200.
- `GET http://127.0.0.1:5173/` returns the VeraMove application.
- The API create/confirm/calls/negotiate/report sequence returns three initial calls, four final quotes, an improved negotiated total or terms, and evidence-backed rankings.

Send Ctrl+C and verify both ports stop listening.

- [ ] **Step 5: Audit every explicit acceptance requirement**

Check the required tree, contract names and fields, state values, route list, YAML keys, fixture inventory and behavior, migration tables/indexes/idempotency, README sections, AGENTS ownership, CI triggers, ignored sensitive artifacts, and absence of external SDK calls. Treat a requirement as complete only when a file inspection, test, or runtime response proves it.

- [ ] **Step 6: Print the final tree and capture repository status**

Run: `find . -path './.git' -prune -o -path './.venv' -prune -o -path './apps/web/node_modules' -prune -o -path './apps/web/dist' -prune -o -print | sort`

Run: `git status --short`

Expected: only intended source and generated contract artifacts are present before staging.

- [ ] **Step 7: Commit the complete starter**

Run:

```bash
git add .
git commit -m "chore: bootstrap VeraMove hackathon repository"
```

Expected: Git reports a new commit with the exact required subject. If identity prevents the commit, leave all intended files unstaged or staged consistently and report the exact two commands above.
