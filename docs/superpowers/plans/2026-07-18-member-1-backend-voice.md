# Member 1 Backend and Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver VeraMove's mock-complete backend lifecycle and a fail-closed ElevenLabs outbound-call path with typed orchestration, verified negotiation leverage, signed idempotent webhooks, and release-ready validation.

**Architecture:** Keep FastAPI and the canonical Member 2 contracts intact while splitting orchestration behind `VoiceProvider`, `IntelligenceProvider`, `JobRepository`, `CallRepository`, and `QuoteRepository`. Store live in-progress work as an internal `CallAttempt` because canonical `CallRecord` requires a completed outcome and recording URL; only normalized completed results enter the canonical aggregate. Mock mode composes the same single-call primitive into three deterministic calls, while live mode uses ElevenLabs' native Twilio endpoint through an injected HTTP transport.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, HTTPX, PyYAML, pytest, Ruff, ElevenLabs native Twilio HTTP API, HMAC-SHA256 webhooks, Vite/React generated OpenAPI types.

## Global Constraints

- Work on `feat/member-1-backend-voice`, which is based on `main` commit `7bbd44b`.
- Preserve the existing repository structure; do not bootstrap or replace the starter.
- Treat `services/api/app/contracts`, `services/api/app/integrations/openai`, `packages/contracts`, `data`, `supabase`, `evals`, and frontend source as other owners' code.
- Do not change canonical `JobSpecV1`, `CallRecord`, `CallOutcome`, `QuoteV1`, or `RecommendationV1` fields in this plan.
- FastAPI-generated `packages/contracts/openapi.json` remains canonical; generated artifacts change only through repository scripts.
- Keep `APP_MODE=mock` as the default and require no credentials for mock startup, tests, or CI.
- Permit `APP_MODE=live` only with `LIVE_CALLS_ENABLED=true`, all ElevenLabs settings, and `LIVE_TEST_TO_NUMBER`.
- Never place a real call from an automated test, `python scripts/check.py`, or CI.
- Never commit secrets, real phone numbers, home addresses, raw live transcripts, recordings, or personal moving records.
- Mock mode must create exactly three initial vendor calls from defensive copies of one confirmed `JobSpecV1`. The controlled live adapter limits the calls endpoint to one opt-in test call and remains `CALLING`.
- Only verified, evidence-backed, same-job, same-version, different-vendor quotes may be negotiation leverage.
- Support exactly `itemized_quote`, `callback_commitment`, `documented_decline`, and `failed` outcomes.
- Preserve the frozen routes named in the approved design; retain existing compatible starter routes.
- Freeze these exact method/path pairs: `POST /api/intake/document`, `POST /api/jobs/{job_id}/confirm`, `POST /api/jobs/{job_id}/calls`, `POST /api/webhooks/elevenlabs`, `POST /api/jobs/{job_id}/negotiate`, `GET /api/jobs/{job_id}/report`, `GET /api/jobs/{job_id}/events`, `GET /health`, and `GET /api/jobs/{job_id}`.
- Do not create a release tag before team code freeze.
- Run focused tests after every red/green cycle and finish with `python scripts/check.py`.

## File and Interface Map

### Governance and Agent Assets

- `CONTRIBUTING.md`: role-based branch and review guidance.
- `agents/intake/README.md`, `agents/negotiator/README.md`: correct Toheeb ownership.
- `agents/intake/prompt.md`, `agents/intake/agent.yaml`: document/voice intake behavior.
- `agents/negotiator/prompt.md`, `agents/negotiator/agent.yaml`: evidence-constrained negotiation behavior.
- `agents/tools.yaml`: machine-readable definitions for the four required tools.

### Orchestration and Persistence

- `services/api/app/orchestration/models.py`: internal `CallAttempt`, `VoiceCallReference`, `VoiceCallResult`, and `JobEvent`.
- `services/api/app/orchestration/providers.py`: `VoiceProvider` and `IntelligenceProvider` protocols.
- `services/api/app/orchestration/mock_intelligence.py`: deterministic intake and adapter around the existing negotiation gateway.
- `services/api/app/orchestration/tools.py`: validated quote/outcome writes and verified leverage lookup.
- `services/api/app/orchestration/service.py`: idempotent lifecycle and single/batch/negotiation orchestration.
- `services/api/app/repositories/base.py`: the three repository protocols.
- `services/api/app/repositories/memory.py`: synchronized in-memory backing store satisfying all three protocols.

### ElevenLabs and API

- `services/api/app/integrations/elevenlabs/base.py`: provider-neutral JSON transport boundary.
- `services/api/app/integrations/elevenlabs/mock.py`: deterministic single-call provider.
- `services/api/app/integrations/elevenlabs/live.py`: gated native outbound-call adapter.
- `services/api/app/integrations/elevenlabs/webhook.py`: signature verification and provider payload normalization.
- `services/api/app/core/config.py`: safe mock/live settings.
- `services/api/app/core/errors.py`: provider configuration, request, and webhook authentication errors.
- `services/api/app/api/models.py`: route-local intake, health, and event response models.
- `services/api/app/api/dependencies.py`: mock/live composition without dialing at startup.
- `services/api/app/api/router.py`: frozen routes and raw-body webhook handling.
- `services/api/app/main.py`: stable HTTP mapping for new domain errors.

### Tests, Generated Contracts, and Operations

- `services/api/tests/test_documentation.py`: real-name ownership assertions.
- `services/api/tests/test_repository_and_adapters.py`: split repository behavior and defensive copies.
- `services/api/tests/test_voice_tools.py`: all outcome and leverage rules.
- `services/api/tests/test_live_voice.py`: fail-closed live settings and recorded HTTP requests.
- `services/api/tests/test_webhooks.py`: HMAC, timestamp, normalization, replay, and event behavior.
- `services/api/tests/test_service.py`: lifecycle and idempotency.
- `services/api/tests/test_api.py`: frozen route and full mock-flow behavior.
- `services/api/tests/test_openapi.py`: additive route coverage.
- `services/api/tests/test_project_assets.py`: agent prompt/config honesty checks.
- `.env.example`, `docs/integration-boundaries.md`, `docs/backend-voice-runbook.md`, and `AGENTS.md`: safe configuration and release/smoke guidance.
- `packages/contracts/openapi.json`, `apps/web/src/api/schema.d.ts`: script-generated additive API changes requiring owner review.

---

### Task 1: Repair Role Ownership and Restore the Baseline

**Files:**

- Modify: `services/api/tests/test_documentation.py:7-41`
- Modify: `CONTRIBUTING.md:3-18`
- Modify: `agents/intake/README.md:1-5`
- Modify: `agents/negotiator/README.md:1-5`

**Interfaces:**

- Consumes: the real contributor names and roles already present in `AGENTS.md` and `CODEOWNERS`.
- Produces: a green ownership-document test and role-scoped contribution language.

- [ ] **Step 1: Replace the stale member-number assertion with a failing role-alignment test**

Add the document constants and assert exact role labels plus the agent owner:

```python
CONTRIBUTING = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
INTAKE_AGENT = (ROOT / "agents/intake/README.md").read_text(encoding="utf-8")
NEGOTIATOR_AGENT = (ROOT / "agents/negotiator/README.md").read_text(encoding="utf-8")


def test_agents_declares_final_role_ownership_and_boundaries():
    for owner in (
        "Toheeb (@Olacode01)",
        "Zukhriuddin (@zukhriddingit)",
        "Northeastern teammate",
        "Arsalan (@ars2711)",
    ):
        assert owner in AGENTS
    assert "Do not rewrite another member's subsystem" in AGENTS
    assert "No-secrets rule" in AGENTS
    assert "No-real-PII rule" in AGENTS
    assert "Contract-change process" in AGENTS
    assert "python scripts/check.py" in AGENTS


def test_contributor_and_agent_docs_use_role_ownership():
    assert "role-scoped branch" in CONTRIBUTING
    assert "Owner: Toheeb (@Olacode01)" in INTAKE_AGENT
    assert "Owner: Toheeb (@Olacode01)" in NEGOTIATOR_AGENT
```

- [ ] **Step 2: Run the focused test and verify the new assertion fails**

Run: `python -m pytest services/api/tests/test_documentation.py -q`

Expected: FAIL because `CONTRIBUTING.md` says `member-scoped` and both agent READMEs still say `Owner: Member 2`.

- [ ] **Step 3: Align the stale documents without rewriting AGENTS or CODEOWNERS**

Change the contribution sentence to:

```markdown
Run `python scripts/bootstrap.py` after cloning, create a role-scoped branch from `main`, and
read `AGENTS.md` before editing. Keep changes within the named directory ownership and request
review from every affected owner.
```

Set the owner line in both agent READMEs to:

```markdown
Owner: Toheeb (@Olacode01).
```

- [ ] **Step 4: Prove the incoming main regression is fixed**

Run: `python -m pytest services/api/tests/test_documentation.py -q`

Expected: all documentation tests pass.

Run: `python scripts/check.py`

Expected: Ruff, backend tests, OpenAPI generation, frontend type generation, typecheck, frontend tests, and the Vite build all pass.

- [ ] **Step 5: Commit the isolated ownership repair**

```bash
git add CONTRIBUTING.md agents/intake/README.md agents/negotiator/README.md services/api/tests/test_documentation.py
git commit -m "chore(repo): align ownership with final team plan"
```

### Task 2: Split Internal Call State and Repository Boundaries

**Files:**

- Create: `services/api/app/orchestration/models.py`
- Modify: `services/api/app/repositories/base.py:1-18`
- Modify: `services/api/app/repositories/memory.py:1-56`
- Modify: `services/api/app/repositories/__init__.py`
- Modify: `services/api/tests/test_repository_and_adapters.py:1-70`

**Interfaces:**

- Consumes: canonical `JobRecord`, `JobSpecV1`, `CallRecord`, `CallStatus`, `QuoteV1`, and `Vendor`.
- Produces: `CallAttempt`, `CallKind`, `VoiceCallReference`, `VoiceCallResult`, and `JobEvent`.
- Produces: `JobRepository.create/get/save/reset`.
- Produces: `CallRepository.create_attempt/save_attempt/get_attempt/list_attempts/find_attempt_by_conversation_id/save_call/list_calls/reserve_webhook/append_event/list_events`.
- Produces: `QuoteRepository.save_quote/list_quotes/get_verified_competing_quote`.

- [ ] **Step 1: Add failing repository-boundary tests**

Add tests that require defensive attempt snapshots, call/quote aggregation, atomic replay reservation, and eligible leverage:

```python
def test_repository_preserves_confirmed_snapshot_and_provider_reference(fixtures, job_spec):
    repository = InMemoryRepository()
    record = make_confirmed_record(job_spec)
    repository.create(record)
    vendor = fixtures.load_vendors()[0]
    attempt = CallAttempt(
        call_id=uuid4(),
        job_id=job_spec.job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=record.job_spec,
        status=CallStatus.PENDING,
        started_at=datetime.now(UTC),
    )
    repository.create_attempt(attempt)
    stored = repository.get_attempt(attempt.call_id)
    assert stored is not None
    assert stored.job_spec_snapshot == record.job_spec
    assert stored is not attempt


def test_verified_competitor_excludes_target_and_unverified_quotes(fixtures, job_spec):
    repository = InMemoryRepository()
    repository.create(make_confirmed_record(job_spec))
    quotes = fixtures.load_initial_quotes()
    for quote in quotes:
        repository.save_quote(quote.model_copy(update={"job_id": job_spec.job_id}))
    selected = repository.get_verified_competing_quote(
        job_spec.job_id,
        target_vendor_id=quotes[2].vendor.vendor_id,
        job_spec_version=job_spec.version,
    )
    assert selected is not None
    assert selected.vendor.slug == "clearpath-movers"
```

Add `make_confirmed_record` as a local test helper that sets `confirmed=True`, one UTC `confirmed_at`, and state `CONFIRMED`. Rename current test construction to `InMemoryRepository`.

- [ ] **Step 2: Run the repository tests and verify collection fails**

Run: `python -m pytest services/api/tests/test_repository_and_adapters.py -q`

Expected: collection fails because `CallAttempt`, `CallKind`, and `InMemoryRepository` do not exist.

- [ ] **Step 3: Define focused internal orchestration models**

Create models that represent an honest pending live call without weakening canonical contracts:

```python
class CallKind(StrEnum):
    QUOTE = "quote"
    NEGOTIATION = "negotiation"


class VoiceCallReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = Field(min_length=1, max_length=200)
    provider_call_id: str = Field(min_length=1, max_length=200)


class CallAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: UUID
    job_id: UUID
    kind: CallKind
    vendor: Vendor
    job_spec_snapshot: JobSpecV1
    status: CallStatus
    started_at: datetime
    completed_at: datetime | None = None
    reference: VoiceCallReference | None = None


class VoiceCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: VoiceCallReference
    outcome: CallOutcome | None = None
    recording_url: HttpUrl | None = None
    completed_at: datetime | None = None


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    call_id: UUID | None = None
    event_type: str = Field(min_length=1, max_length=120)
    occurred_at: datetime
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
```

- [ ] **Step 4: Replace the monolithic repository protocol with three protocols**

Declare these exact methods in `repositories/base.py`:

```python
class JobRepository(Protocol):
    def create(self, record: JobRecord) -> JobRecord: ...
    def get(self, job_id: UUID) -> JobRecord | None: ...
    def save(self, record: JobRecord) -> JobRecord: ...
    def reset(self) -> None: ...


class CallRepository(Protocol):
    def create_attempt(self, attempt: CallAttempt) -> CallAttempt: ...
    def save_attempt(self, attempt: CallAttempt) -> CallAttempt: ...
    def get_attempt(self, call_id: UUID) -> CallAttempt | None: ...
    def list_attempts(self, job_id: UUID) -> list[CallAttempt]: ...
    def find_attempt_by_conversation_id(self, conversation_id: str) -> CallAttempt | None: ...
    def save_call(self, call: CallRecord) -> CallRecord: ...
    def list_calls(self, job_id: UUID) -> list[CallRecord]: ...
    def reserve_webhook(self, idempotency_key: str) -> bool: ...
    def append_event(self, event: JobEvent) -> JobEvent: ...
    def list_events(self, job_id: UUID) -> list[JobEvent]: ...


class QuoteRepository(Protocol):
    def save_quote(self, quote: QuoteV1) -> QuoteV1: ...
    def list_quotes(self, job_id: UUID) -> list[QuoteV1]: ...
    def get_verified_competing_quote(
        self,
        job_id: UUID,
        target_vendor_id: UUID,
        job_spec_version: str,
    ) -> QuoteV1 | None: ...
```

- [ ] **Step 5: Implement one synchronized backing store satisfying all protocols**

Rename the implementation to `InMemoryRepository`, keep `InMemoryJobRepository = InMemoryRepository` temporarily for import compatibility, and add locked stores:

```python
def __init__(self) -> None:
    self._jobs: dict[UUID, dict[str, Any]] = {}
    self._attempts: dict[UUID, dict[str, Any]] = {}
    self._events: dict[UUID, list[dict[str, Any]]] = {}
    self._webhook_keys: set[str] = set()
    self._lock = RLock()


def save_call(self, call: CallRecord) -> CallRecord:
    with self._lock:
        payload = self._jobs.get(call.job_id)
        if payload is None:
            raise ResourceNotFound(f"Job {call.job_id} was not found")
        record = JobRecord.model_validate(deepcopy(payload))
        record.calls = [item for item in record.calls if item.call_id != call.call_id]
        record.calls.append(call)
        self._jobs[call.job_id] = record.model_dump(mode="json")
    return CallRecord.model_validate(deepcopy(call.model_dump(mode="json")))


def get_verified_competing_quote(
    self,
    job_id: UUID,
    target_vendor_id: UUID,
    job_spec_version: str,
) -> QuoteV1 | None:
    eligible = [
        quote
        for quote in self.list_quotes(job_id)
        if quote.vendor.vendor_id != target_vendor_id
        and quote.job_spec_version == job_spec_version
        and quote.verification_status is VerificationStatus.VERIFIED
        and quote.verified_data
        and quote.transcript_evidence
    ]
    return min(eligible, key=lambda quote: quote.negotiated_total, default=None)
```

`save_quote` replaces an existing quote with the same ID or appends it to the job. `create_attempt`, `save_attempt`, `list_attempts`, event methods, and reads always round-trip through Pydantic plus `deepcopy`. `reserve_webhook` performs membership check and insertion inside the same lock. `reset` clears all four stores.

- [ ] **Step 6: Run focused repository tests and commit**

Run: `python -m pytest services/api/tests/test_repository_and_adapters.py -q`

Expected: all repository and existing adapter tests pass.

Run: `python -m ruff check services/api/app/orchestration/models.py services/api/app/repositories services/api/tests/test_repository_and_adapters.py`

Expected: `All checks passed!`

```bash
git add services/api/app/orchestration/models.py services/api/app/repositories services/api/tests/test_repository_and_adapters.py
git commit -m "refactor(api): split orchestration repository boundaries"
```

### Task 3: Add Provider Protocols, Deterministic Single Calls, and Voice Tools

**Files:**

- Create: `services/api/app/orchestration/providers.py`
- Create: `services/api/app/orchestration/mock_intelligence.py`
- Create: `services/api/app/orchestration/tools.py`
- Modify: `services/api/app/integrations/elevenlabs/base.py:1-15`
- Modify: `services/api/app/integrations/elevenlabs/mock.py:1-65`
- Create: `agents/intake/prompt.md`
- Create: `agents/intake/agent.yaml`
- Create: `agents/negotiator/prompt.md`
- Create: `agents/negotiator/agent.yaml`
- Create: `agents/tools.yaml`
- Create: `services/api/tests/test_voice_tools.py`
- Modify: `services/api/tests/test_repository_and_adapters.py`
- Modify: `services/api/tests/test_project_assets.py`

**Interfaces:**

- Consumes: Task 2 models and repositories plus existing `NegotiationGateway` and `DemoFixtures`.
- Produces: `VoiceProvider.initiate_quote_call` and `VoiceProvider.initiate_negotiation_call`.
- Produces: `IntelligenceProvider.extract_document` and `IntelligenceProvider.negotiate`.
- Produces: `VoiceTools.save_quote/save_call_outcome/get_verified_competing_quote/request_callback`.

- [ ] **Step 1: Write failing provider and tool tests**

Require one vendor per provider call, a document source context, matching job/call/vendor/version writes, and evidence-backed leverage:

```python
def test_mock_voice_provider_initiates_one_quote_call(fixtures, job_spec):
    provider = MockVoiceProvider(fixtures)
    vendor = fixtures.load_vendors()[0]
    call_id = uuid4()
    result = provider.initiate_quote_call(job_spec, vendor, call_id)
    assert result.outcome is not None
    assert result.outcome.type is CallOutcomeType.ITEMIZED_QUOTE
    assert result.outcome.quote is not None
    assert result.outcome.quote.vendor == vendor
    assert result.outcome.quote.job_id == job_spec.job_id
    assert all(
        evidence.call_id == call_id
        for evidence in result.outcome.quote.transcript_evidence
    )


def test_tools_reject_verified_quote_without_evidence(repository, confirmed_record, fixtures):
    repository.create(confirmed_record)
    vendor = fixtures.load_vendors()[0]
    attempt = make_attempt(confirmed_record.job_spec, vendor)
    repository.create_attempt(attempt)
    quote = fixtures.load_initial_quotes()[0].model_copy(
        update={
            "job_id": confirmed_record.job_spec.job_id,
            "transcript_evidence": [],
        }
    )
    with pytest.raises(DomainConflict, match="Verified quotes require evidence"):
        VoiceTools(repository, repository).save_quote(attempt.call_id, quote)
```

Add parameterized tests that `save_call_outcome` accepts a callback with `callback_at`, a decline with `reason`, and a failure with `reason`, and stores exactly one canonical call for each attempt.

- [ ] **Step 2: Run the focused tests and verify missing interfaces**

Run: `python -m pytest services/api/tests/test_voice_tools.py services/api/tests/test_repository_and_adapters.py -q`

Expected: collection fails because `MockVoiceProvider`, `VoiceTools`, and the provider protocols do not exist.

- [ ] **Step 3: Define the provider protocols and deterministic intelligence adapter**

```python
class VoiceProvider(Protocol):
    initial_call_limit: int

    def initiate_quote_call(
        self,
        job_spec: JobSpecV1,
        vendor: Vendor,
        call_id: UUID,
    ) -> VoiceCallResult: ...

    def initiate_negotiation_call(
        self,
        job_spec: JobSpecV1,
        target_vendor: Vendor,
        verified_competitor: QuoteV1,
        planned_quote: QuoteV1,
        call_id: UUID,
    ) -> VoiceCallResult: ...


class IntelligenceProvider(Protocol):
    def extract_document(self, document_text: str) -> JobSpecV1: ...

    def negotiate(
        self,
        job_spec: JobSpecV1,
        quotes: list[QuoteV1],
        verified_competitor: QuoteV1,
    ) -> QuoteV1: ...
```

`MockIntelligenceProvider.extract_document` rejects blank text, loads the synthetic job, assigns a new `job_id`, clears confirmation, and sets `SourceContext(intake_method="document")`. Its `negotiate` delegates unchanged to Member 2's existing `NegotiationGateway`.

- [ ] **Step 4: Add the mock single-call adapter beside the legacy batch adapter**

Add `MockVoiceProvider` without removing `MockVoiceVendorGateway` yet, because the pre-Task-4 service still imports and calls the legacy batch class. Implement a quote lookup by vendor, rebind job and evidence call IDs, and return a synchronous result:

```python
def initiate_quote_call(
    self,
    job_spec: JobSpecV1,
    vendor: Vendor,
    call_id: UUID,
) -> VoiceCallResult:
    quote = next(
        item
        for item in self._fixtures.load_initial_quotes()
        if item.vendor.vendor_id == vendor.vendor_id
    )
    evidence = [
        item.model_copy(update={"call_id": call_id})
        for item in quote.transcript_evidence
    ]
    quote = quote.model_copy(
        update={
            "job_id": job_spec.job_id,
            "job_spec_version": job_spec.version,
            "transcript_evidence": evidence,
        }
    )
    return VoiceCallResult(
        reference=VoiceCallReference(
            conversation_id=f"synthetic-conversation-{call_id}",
            provider_call_id=f"synthetic-twilio-{job_spec.job_id}-{vendor.slug}",
        ),
        outcome=CallOutcome(type=CallOutcomeType.ITEMIZED_QUOTE, quote=quote),
        recording_url=quote.recording_url,
        completed_at=self._clock(),
    )
```

`initiate_negotiation_call` returns the supplied verified `planned_quote` as a synchronous itemized outcome after rebinding its transcript evidence to `call_id`. Set `MockVoiceProvider.initial_call_limit = 3`. Remove batch creation from the provider after Task 4 migrates the service.

- [ ] **Step 5: Implement the validated tool facade**

```python
def save_quote(self, call_id: UUID, quote: QuoteV1) -> QuoteV1:
    attempt = self._require_attempt(call_id)
    if quote.job_id != attempt.job_id:
        raise DomainConflict("Quote job does not match call attempt")
    if quote.vendor.vendor_id != attempt.vendor.vendor_id:
        raise DomainConflict("Quote vendor does not match call attempt")
    if quote.job_spec_version != attempt.job_spec_snapshot.version:
        raise DomainConflict("Quote JobSpec version does not match call attempt")
    if quote.verification_status is VerificationStatus.VERIFIED:
        if not quote.verified_data or not quote.transcript_evidence:
            raise DomainConflict("Verified quotes require evidence and verified data")
    return self._quotes.save_quote(quote)


def get_verified_competing_quote(
    self,
    job_id: UUID,
    target_vendor_id: UUID,
    job_spec_version: str,
) -> QuoteV1:
    quote = self._quotes.get_verified_competing_quote(
        job_id,
        target_vendor_id,
        job_spec_version,
    )
    if quote is None:
        raise DomainConflict("Negotiation requires a verified competing quote")
    return quote
```

`save_call_outcome` requires an existing attempt, completed timestamp, and recording URL. It constructs one canonical `CallRecord`, saves an attached quote through `save_quote`, marks the attempt `COMPLETED` or `FAILED`, and stores the call. `request_callback` constructs `CallOutcome(type=CALLBACK_COMMITMENT, callback_at=callback_at)` and delegates to `save_call_outcome`.

- [ ] **Step 6: Add agent prompts, configurations, and exact tool schemas**

The intake prompt contains these rules:

```markdown
- Ask only for fields configured in configs/moving.yaml.
- Mark unknown facts as unknown; never infer inventory, access, price, or insurance facts.
- Read the complete structured JobSpecV1 back to the user before confirmation.
- Never confirm a job or place a vendor call yourself.
- Never reveal secrets, internal IDs, or raw document contents.
```

The negotiator prompt contains:

```markdown
- Use get_verified_competing_quote before mentioning a competitor.
- Never invent a price, fee, concession, recording, transcript statement, or vendor policy.
- Ask for an itemized total, deposit, binding status, availability, and every configured fee.
- Finish with exactly one supported CallOutcome type.
- Do not claim authority to book, pay, sign, or accept terms.
```

Use this agent-config shape:

```yaml
version: 1
agent:
  name: veramove-intake
  prompt_file: prompt.md
  tools_file: ../tools.yaml
  tool_names: []
  structured_output: JobSpecV1
```

The negotiator config changes the name to `veramove-negotiator`, sets `structured_output: CallOutcome`, and lists all four tool names. `agents/tools.yaml` uses:

```yaml
version: 1
tools:
  - name: save_quote
    description: Save one structured quote for the active call.
    required: [call_id, quote]
    properties:
      call_id: {type: string, format: uuid}
      quote: {type: object}
  - name: save_call_outcome
    description: Complete one call with a supported structured outcome.
    required: [call_id, outcome, completed_at, recording_url]
    properties:
      call_id: {type: string, format: uuid}
      outcome: {type: object}
      completed_at: {type: string, format: date-time}
      recording_url: {type: string, format: uri}
  - name: get_verified_competing_quote
    description: Retrieve eligible evidence-backed leverage for a different vendor.
    required: [job_id, target_vendor_id, job_spec_version]
    properties:
      job_id: {type: string, format: uuid}
      target_vendor_id: {type: string, format: uuid}
      job_spec_version: {type: string, const: "1.0"}
  - name: request_callback
    description: Complete a call with a callback commitment.
    required: [call_id, callback_at, recording_url]
    properties:
      call_id: {type: string, format: uuid}
      callback_at: {type: string, format: date-time}
      recording_url: {type: string, format: uri}
```

Each config contains no credentials or phone numbers.

- [ ] **Step 7: Validate tools and assets, then commit**

Run: `python -m pytest services/api/tests/test_voice_tools.py services/api/tests/test_repository_and_adapters.py services/api/tests/test_project_assets.py -q`

Expected: all focused tests pass.

Run: `python -m ruff check services/api/app/orchestration services/api/app/integrations/elevenlabs services/api/tests/test_voice_tools.py`

Expected: `All checks passed!`

```bash
git add agents services/api/app/orchestration/providers.py services/api/app/orchestration/mock_intelligence.py services/api/app/orchestration/tools.py services/api/app/integrations/elevenlabs services/api/tests/test_voice_tools.py services/api/tests/test_repository_and_adapters.py services/api/tests/test_project_assets.py
git commit -m "feat(voice): add intake and negotiator agent tools"
```

### Task 4: Refactor the Lifecycle Around Single, Batch, and Negotiation Calls

**Files:**

- Modify: `services/api/app/orchestration/service.py:1-141`
- Modify: `services/api/app/api/dependencies.py:1-28`
- Modify: `services/api/tests/conftest.py:1-55`
- Modify: `services/api/tests/test_service.py:1-54`
- Modify: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**

- Consumes: all Task 2 repositories and Task 3 providers/tools.
- Produces: `create_job_from_document(document_text) -> JobRecord`.
- Produces: idempotent `confirm_job(job_id) -> JobRecord`.
- Produces: `initiate_single_quote_call(job_id, vendor) -> CallAttempt`.
- Produces: `initiate_quote_batch(job_id) -> JobRecord`, with `start_calls` as a compatibility wrapper.
- Produces: `initiate_negotiation_call(job_id) -> JobRecord`, with `negotiate` as a compatibility wrapper.

- [ ] **Step 1: Rewrite lifecycle tests first**

Change double confirmation from an expected exception to an idempotency assertion and add snapshot/batch/retry tests:

```python
def test_confirmation_is_idempotent_and_defensive(service, job_spec):
    service.create_job(job_spec)
    first = service.confirm_job(job_spec.job_id)
    second = service.confirm_job(job_spec.job_id)
    assert second == first
    first.job_spec.origin.address_summary = "Mutated outside repository"
    stored = service.get_job(job_spec.job_id)
    assert stored.job_spec.origin.address_summary != "Mutated outside repository"


def test_batch_uses_exact_confirmed_snapshot_and_does_not_redial(service, job_spec):
    service.create_job(job_spec)
    confirmed = service.confirm_job(job_spec.job_id)
    first = service.initiate_quote_batch(job_spec.job_id)
    second = service.initiate_quote_batch(job_spec.job_id)
    assert first == second
    assert len(first.calls) == 3
    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 3
    assert all(item.job_spec_snapshot == confirmed.job_spec for item in attempts)
```

Add a document-intake test asserting `source_context.intake_method == "document"` and retain calls-before-confirmation/report-before-completion conflict tests.

- [ ] **Step 2: Run service tests and verify constructor/method failures**

Run: `python -m pytest services/api/tests/test_service.py -q`

Expected: failures because the service has one repository argument, double confirmation raises, and the new explicit methods do not exist.

- [ ] **Step 3: Inject all five boundaries and make confirmation idempotent**

```python
def __init__(
    self,
    jobs: JobRepository,
    calls: CallRepository,
    quotes: QuoteRepository,
    voice: VoiceProvider,
    intelligence: IntelligenceProvider,
    discovery: VendorDiscoveryGateway,
    fixtures: DemoFixtures,
    clock: Callable[[], datetime] = utc_now,
) -> None:
    self._jobs = jobs
    self._calls = calls
    self._quotes = quotes
    self._voice = voice
    self._intelligence = intelligence
    self._discovery = discovery
    self._fixtures = fixtures
    self._tools = VoiceTools(calls, quotes)
    self._clock = clock


def confirm_job(self, job_id: UUID) -> JobRecord:
    record = self.get_job(job_id)
    if record.job_spec.confirmed:
        return record
    validate_transition(record.state, JobState.CONFIRMED)
    now = self._clock()
    record.job_spec = record.job_spec.model_copy(
        update={"confirmed": True, "confirmed_at": now},
        deep=True,
    )
    record.state = JobState.CONFIRMED
    record.updated_at = now
    return self._jobs.save(record)
```

Define `utc_now() -> datetime` as `datetime.now(UTC)`. `create_job_from_document` delegates to `IntelligenceProvider.extract_document` and then `create_job`. `list_call_attempts` delegates to `CallRepository.list_attempts` and returns defensive models.

- [ ] **Step 4: Implement one call and compose the three-call batch**

```python
def initiate_single_quote_call(self, job_id: UUID, vendor: Vendor) -> CallAttempt:
    record = self.get_job(job_id)
    if not record.job_spec.confirmed:
        raise DomainConflict("Calls require a confirmed JobSpec")
    attempt = CallAttempt(
        call_id=uuid4(),
        job_id=job_id,
        kind=CallKind.QUOTE,
        vendor=vendor,
        job_spec_snapshot=record.job_spec.model_copy(deep=True),
        status=CallStatus.PENDING,
        started_at=self._clock(),
    )
    attempt = self._calls.create_attempt(attempt)
    result = self._voice.initiate_quote_call(
        attempt.job_spec_snapshot,
        vendor,
        attempt.call_id,
    )
    attempt = attempt.model_copy(
        update={"status": CallStatus.IN_PROGRESS, "reference": result.reference}
    )
    self._calls.save_attempt(attempt)
    if result.outcome and result.recording_url and result.completed_at:
        self._tools.save_call_outcome(
            attempt.call_id,
            result.outcome,
            result.completed_at,
            result.recording_url,
        )
    return self._calls.get_attempt(attempt.call_id) or attempt
```

`initiate_quote_batch` accepts only `CONFIRMED` for its first execution, transitions to `CALLING`, and invokes the single method for `fixtures.load_vendors()[: voice.initial_call_limit]`. The mock provider's limit is three and the live provider's limit is one. Transition to `QUOTES_READY` only when three canonical calls exist. If state is already `CALLING`, `QUOTES_READY`, `NEGOTIATING`, or `COMPLETED`, return the stored aggregate without initiating another call.

- [ ] **Step 5: Implement verified negotiation and evidence-consistent reporting**

Choose the highest initial total as the target, exclude it from competitor lookup, and do not store the planned result until the voice provider completes:

```python
target_quote = max(record.quotes, key=lambda quote: quote.negotiated_total)
competitor = self._tools.get_verified_competing_quote(
    job_id,
    target_quote.vendor.vendor_id,
    record.job_spec.version,
)
planned = self._intelligence.negotiate(record.job_spec, record.quotes, competitor)
attempt = self._new_attempt(record, target_quote.vendor, CallKind.NEGOTIATION)
result = self._voice.initiate_negotiation_call(
    attempt.job_spec_snapshot,
    target_quote.vendor,
    competitor,
    planned,
    attempt.call_id,
)
```

If the result is asynchronous, persist its reference and leave the job in `NEGOTIATING`. If it includes a complete outcome, save it through `VoiceTools`, require lower price or a nonempty concession, build the recommendation fixture with the current job ID and transcript evidence collected from all stored quotes, and transition to `COMPLETED`.
Only `QUOTES_READY` may begin negotiation. Repeated requests in `NEGOTIATING` or `COMPLETED` return the stored aggregate without another provider call or quote.

- [ ] **Step 6: Update dependency/test construction and remove old batch adapters**

Create one `InMemoryRepository` and pass it as `jobs`, `calls`, and `quotes`. Wire `MockVoiceProvider`, `MockIntelligenceProvider`, the current Tavily mock, and fixtures. Update the service fixture identically. Delete `create_calls`, `VoiceVendorGateway`, `TwilioTransport`, the temporary `InMemoryJobRepository` alias, and their old imports/tests now that no caller uses them.

- [ ] **Step 7: Run the full backend suite and commit**

Run: `python -m pytest services/api/tests -q`

Expected: every backend test passes, including three initial calls, four total quotes after negotiation, defensive snapshots, and idempotent repeated operations.

Run: `python -m ruff check services/api/app services/api/tests`

Expected: `All checks passed!`

```bash
git add services/api/app/orchestration/service.py services/api/app/api/dependencies.py services/api/app/integrations/elevenlabs services/api/tests/conftest.py services/api/tests/test_service.py services/api/tests/test_repository_and_adapters.py
git commit -m "feat(api): orchestrate single batch and negotiation calls"
```

### Task 5: Add Fail-Closed Live Settings and the Native ElevenLabs Outbound Adapter

**Files:**

- Modify: `services/api/app/core/config.py:1-24`
- Modify: `services/api/app/core/errors.py:1-21`
- Modify: `services/api/app/integrations/elevenlabs/base.py`
- Create: `services/api/app/integrations/elevenlabs/live.py`
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/requirements.txt`
- Modify: `services/api/requirements-dev.txt`
- Modify: `.env.example:1-14`
- Create: `services/api/tests/test_live_voice.py`

**Interfaces:**

- Consumes: Task 3 `VoiceProvider` and Task 2 call result models.
- Produces: `Settings.require_live_voice_config() -> LiveVoiceConfig`.
- Produces: `JsonHttpTransport.post_json(url, headers, payload, timeout_seconds) -> dict[str, Any]`.
- Produces: `ElevenLabsVoiceProvider` implementing both voice-provider methods.

- [ ] **Step 1: Write fail-closed settings and transport tests**

Use a recording transport that never opens a socket:

```python
class RecordingTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def post_json(self, url, headers, payload, timeout_seconds):
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response


class RaisingTransport:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def post_json(self, url, headers, payload, timeout_seconds):
        del url, headers, payload, timeout_seconds
        raise self.error


def test_live_provider_does_not_send_when_switch_is_disabled(live_settings, fixtures, job_spec):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    disabled = replace(
        live_settings,
        live_voice=replace(
            live_settings.live_voice,
            live_calls_enabled=False,
        ),
    )
    provider = ElevenLabsVoiceProvider(
        disabled,
        transport,
    )
    with pytest.raises(ProviderConfigurationError, match="LIVE_CALLS_ENABLED"):
        provider.initiate_quote_call(job_spec, fixtures.load_vendors()[0], uuid4())
    assert transport.requests == []


def test_live_provider_builds_native_outbound_payload(live_settings, fixtures, job_spec):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    provider = ElevenLabsVoiceProvider(live_settings, transport)
    result = provider.initiate_quote_call(
        job_spec,
        fixtures.load_vendors()[0],
        uuid4(),
    )
    request = transport.requests[0]
    assert request["url"].endswith("/v1/convai/twilio/outbound-call")
    assert request["headers"]["xi-api-key"] == "synthetic-api-key"
    assert request["payload"]["agent_phone_number_id"] == "synthetic-phone-id"
    assert request["payload"]["to_number"] == "+15550100000"
    assert result.reference.conversation_id == "conv-1"
    assert result.outcome is None


def test_live_service_limits_calls_route_to_one_request(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RecordingTransport(
        {"success": True, "conversation_id": "conv-1", "callSid": "CA1"}
    )
    service = build_service(
        live_settings,
        InMemoryRepository(),
        voice_transport=transport,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    result = service.initiate_quote_batch(job_spec.job_id)
    assert result.state is JobState.CALLING
    assert len(transport.requests) == 1


def test_live_transport_failure_preserves_failed_attempt(
    live_settings,
    fixtures,
    job_spec,
):
    transport = RaisingTransport(ProviderRequestError("synthetic failure"))
    service = build_service(
        live_settings,
        InMemoryRepository(),
        voice_transport=transport,
    )
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)
    with pytest.raises(ProviderRequestError, match="synthetic failure"):
        service.initiate_quote_batch(job_spec.job_id)
    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 1
    assert attempts[0].status is CallStatus.FAILED
    assert service.get_job(job_spec.job_id).state is JobState.FAILED
```

- [ ] **Step 2: Run the live tests and verify missing configuration classes**

Run: `python -m pytest services/api/tests/test_live_voice.py -q`

Expected: collection fails because `LiveVoiceConfig` and `ElevenLabsVoiceProvider` do not exist.

- [ ] **Step 3: Extend settings with explicit mock/live parsing**

Add a frozen `LiveVoiceConfig` and these `Settings` fields:

```python
@dataclass(frozen=True, slots=True)
class LiveVoiceConfig:
    api_key: str | None = None
    quote_agent_id: str | None = None
    negotiator_agent_id: str | None = None
    phone_number_id: str | None = None
    test_to_number: str | None = None
    webhook_secret: str | None = None
    live_calls_enabled: bool = False
    api_base_url: str = "https://api.elevenlabs.io"


@dataclass(frozen=True, slots=True)
class Settings:
    app_mode: str = "mock"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    live_voice: LiveVoiceConfig = field(default_factory=LiveVoiceConfig)

    def require_live_voice_config(self) -> LiveVoiceConfig:
        if self.app_mode != "live":
            raise ProviderConfigurationError("Live voice requires APP_MODE=live")
        config = self.live_voice
        if not config.live_calls_enabled:
            raise ProviderConfigurationError("Live calls require LIVE_CALLS_ENABLED=true")
        required = {
            "ELEVENLABS_API_KEY": config.api_key,
            "ELEVENLABS_QUOTE_AGENT_ID": config.quote_agent_id,
            "ELEVENLABS_NEGOTIATOR_AGENT_ID": config.negotiator_agent_id,
            "ELEVENLABS_PHONE_NUMBER_ID": config.phone_number_id,
            "ELEVENLABS_WEBHOOK_SECRET": config.webhook_secret,
            "LIVE_TEST_TO_NUMBER": config.test_to_number,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ProviderConfigurationError(
                f"Missing live voice configuration: {', '.join(missing)}"
            )
        return config
```

`from_env` accepts only `mock` and `live`, converts empty provider strings to `None`, parses booleans from `1/true/yes/on`, and never calls `require_live_voice_config` at startup. Add `ProviderConfigurationError` and `ProviderRequestError` as typed domain errors. Tests import `field` and `replace` from `dataclasses` and use:

```python
@pytest.fixture
def live_settings() -> Settings:
    return Settings(
        app_mode="live",
        live_voice=LiveVoiceConfig(
            api_key="synthetic-api-key",
            quote_agent_id="synthetic-quote-agent",
            negotiator_agent_id="synthetic-negotiator-agent",
            phone_number_id="synthetic-phone-id",
            test_to_number="+15550100000",
            webhook_secret="synthetic-webhook-secret",
            live_calls_enabled=True,
        ),
    )
```

- [ ] **Step 4: Add a small injected HTTP transport and the live provider**

Move `httpx>=0.28,<1` into runtime requirements and use it only inside `HttpxJsonTransport`:

```python
class JsonHttpTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


class HttpxJsonTransport:
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
```

Build quote-call payloads through one private method:

```python
def _initiate(
    self,
    agent_id: str,
    job_spec: JobSpecV1,
    vendor: Vendor,
    call_id: UUID,
    dynamic_variables: dict[str, str],
) -> VoiceCallResult:
    config = self._settings.require_live_voice_config()
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
        f"{config.api_base_url}/v1/convai/twilio/outbound-call",
        {"xi-api-key": config.api_key, "content-type": "application/json"},
        payload,
        timeout_seconds=10.0,
    )
    if body.get("success") is not True:
        raise ProviderRequestError("ElevenLabs rejected the outbound call")
    conversation_id = body.get("conversation_id")
    provider_call_id = body.get("callSid")
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ProviderRequestError("ElevenLabs response omitted conversation_id")
    if not isinstance(provider_call_id, str) or not provider_call_id:
        raise ProviderRequestError("ElevenLabs response omitted callSid")
    return VoiceCallResult(
        reference=VoiceCallReference(
            conversation_id=conversation_id,
            provider_call_id=provider_call_id,
        )
    )
```

`initiate_quote_call` chooses the quote agent. `initiate_negotiation_call` chooses the negotiator agent and adds verified competitor ID, competitor total, target vendor, and planned objective as dynamic variables. Set `ElevenLabsVoiceProvider.initial_call_limit = 1` so the controlled route cannot fan out three real calls. Never log headers, destination numbers, raw job payloads, or provider response bodies.

Wrap the provider invocation in `initiate_single_quote_call` with:

```python
try:
    result = self._voice.initiate_quote_call(
        attempt.job_spec_snapshot,
        vendor,
        attempt.call_id,
    )
except (ProviderConfigurationError, ProviderRequestError):
    failed_at = self._clock()
    self._calls.save_attempt(
        attempt.model_copy(
            update={"status": CallStatus.FAILED, "completed_at": failed_at}
        )
    )
    record = self.get_job(job_id)
    record.state = JobState.FAILED
    record.updated_at = failed_at
    self._jobs.save(record)
    raise
```

This preserves a structured internal failure without fabricating the recording URL required by canonical `CallRecord`.

- [ ] **Step 5: Wire live mode without dialing and document safe variables**

Add `build_service(settings, repository, voice_transport=None)` to dependencies. It selects `MockVoiceProvider` for mock and constructs `ElevenLabsVoiceProvider(settings, voice_transport or HttpxJsonTransport())` for live; construction performs no network call. `get_service` calls it without the optional transport. Intelligence and Tavily remain deterministic in both modes for this Member 1 slice.

Add safe empty values to `.env.example`:

```dotenv
APP_MODE=mock
LIVE_CALLS_ENABLED=false
ELEVENLABS_API_KEY=
ELEVENLABS_QUOTE_AGENT_ID=
ELEVENLABS_NEGOTIATOR_AGENT_ID=
ELEVENLABS_PHONE_NUMBER_ID=
ELEVENLABS_WEBHOOK_SECRET=
ELEVENLABS_API_BASE_URL=https://api.elevenlabs.io
LIVE_TEST_TO_NUMBER=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
```

The Twilio account values support dashboard setup but are not sent by this adapter; ElevenLabs uses the imported phone-number ID.

- [ ] **Step 6: Prove no test can dial and commit**

Run: `python -m pytest services/api/tests/test_live_voice.py services/api/tests/test_service.py -q`

Expected: all tests pass; the recording transport receives exactly one request only in the explicitly enabled adapter test, and a live-composed service batch also records exactly one request and stays `CALLING`.

Run: `python -m ruff check services/api/app/core services/api/app/integrations/elevenlabs services/api/app/api/dependencies.py services/api/tests/test_live_voice.py`

Expected: `All checks passed!`

```bash
git add .env.example services/api/requirements.txt services/api/requirements-dev.txt services/api/app/core services/api/app/integrations/elevenlabs services/api/app/orchestration/service.py services/api/app/api/dependencies.py services/api/tests/test_live_voice.py
git commit -m "feat(voice): add gated ElevenLabs outbound calling"
```

### Task 6: Verify, Normalize, and Deduplicate ElevenLabs Webhooks

**Files:**

- Modify: `services/api/app/orchestration/models.py`
- Create: `services/api/app/integrations/elevenlabs/webhook.py`
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/core/errors.py`
- Modify: `services/api/app/api/dependencies.py`
- Create: `services/api/tests/test_webhooks.py`

**Interfaces:**

- Consumes: raw request bytes, `ElevenLabs-Signature`, webhook secret, call repository, and `CallAttempt`.
- Produces: `ElevenLabsWebhookProcessor.process(raw_body, signature_header) -> NormalizedVoiceEvent`.
- Produces: `VeraMoveService.handle_elevenlabs_webhook(raw_body, signature_header) -> WebhookAck`.
- Produces: `VeraMoveService.get_events(job_id) -> list[JobEvent]`.

- [ ] **Step 1: Write signature, timestamp, normalization, and replay tests**

Use the documented signature format `t={unix},v0={hex HMAC}` over `{timestamp}.{body}`:

```python
def sign(body: bytes, secret: str, timestamp: int) -> str:
    signed = str(timestamp).encode() + b"." + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


def test_processor_rejects_invalid_and_stale_signatures(webhook_body):
    processor = ElevenLabsWebhookProcessor(
        secret="synthetic-secret",
        clock=lambda: datetime.fromtimestamp(1_750_000_000, UTC),
    )
    with pytest.raises(WebhookAuthenticationError, match="signature"):
        processor.process(webhook_body, "t=1750000000,v0=bad")
    stale = sign(webhook_body, "synthetic-secret", 1_749_999_000)
    with pytest.raises(WebhookAuthenticationError, match="timestamp"):
        processor.process(webhook_body, stale)


def test_webhook_replay_creates_one_event(service_with_webhook, webhook_body, job_spec):
    signature = sign(webhook_body, "synthetic-secret", 1_750_000_000)
    first = service_with_webhook.handle_elevenlabs_webhook(webhook_body, signature)
    second = service_with_webhook.handle_elevenlabs_webhook(webhook_body, signature)
    assert first == WebhookAck(accepted=True, duplicate=False)
    assert second == WebhookAck(accepted=False, duplicate=True)
    assert len(service_with_webhook.get_events(job_spec.job_id)) == 1
```

`service_with_webhook` creates, confirms, and starts the synthetic job with a service whose processor uses `secret="synthetic-secret"` and a clock fixed at Unix `1_750_000_000`. The `webhook_body` fixture JSON-encodes a `post_call_transcription` object containing only synthetic identifiers, the first stored attempt's `conversation_id`, status `done`, and `event_timestamp=1_750_000_000`.

- [ ] **Step 2: Run webhook tests and verify the processor is missing**

Run: `python -m pytest services/api/tests/test_webhooks.py -q`

Expected: collection fails because `ElevenLabsWebhookProcessor`, `NormalizedVoiceEvent`, `WebhookAuthenticationError`, and `WebhookPayloadError` do not exist.

- [ ] **Step 3: Add the safe normalized event model**

```python
class NormalizedVoiceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    event_timestamp: datetime
    conversation_id: str | None = Field(default=None, max_length=200)
    call_id: UUID | None = None
    call_status: CallStatus | None = None
    provider_status: str | None = Field(default=None, max_length=80)
```

This model deliberately excludes transcript text, phone numbers, audio, full analysis, and arbitrary raw metadata.

Add exact domain error codes:

```python
class WebhookAuthenticationError(DomainError):
    code = "webhook_authentication_error"


class WebhookPayloadError(DomainError):
    code = "webhook_payload_error"
```

- [ ] **Step 4: Implement HMAC and timestamp validation before JSON parsing**

```python
def _verify(self, raw_body: bytes, signature_header: str | None) -> int:
    if not signature_header:
        raise WebhookAuthenticationError("Missing ElevenLabs signature")
    try:
        parts = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = int(parts["t"])
        supplied = parts["v0"]
    except (KeyError, ValueError):
        raise WebhookAuthenticationError("Malformed ElevenLabs signature") from None
    now = int(self._clock().timestamp())
    if abs(now - timestamp) > self._tolerance_seconds:
        raise WebhookAuthenticationError("ElevenLabs webhook timestamp is stale")
    signed = str(timestamp).encode() + b"." + raw_body
    expected = hmac.new(
        self._secret.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise WebhookAuthenticationError("Invalid ElevenLabs signature")
    return timestamp
```

After verification, parse JSON and raise `WebhookPayloadError` when the body is not a JSON object. Map `done` to `CallStatus.COMPLETED` and `failed` to `CallStatus.FAILED`, and leave unknown statuses as `None`. Build the replay key as SHA-256 of `event_type:conversation_id:event_timestamp`. Retain backward-compatible synthetic webhook normalization only when the body contains the existing explicit `idempotency_key`; use the verified header timestamp when that payload has no `event_timestamp`.

- [ ] **Step 5: Apply normalized events atomically in the service**

Add `webhooks: ElevenLabsWebhookProcessor` to `VeraMoveService.__init__` and assign `self._webhooks = webhooks`. Then implement:

```python
def handle_elevenlabs_webhook(
    self,
    raw_body: bytes,
    signature_header: str | None,
) -> WebhookAck:
    event = self._webhooks.process(raw_body, signature_header)
    if not self._calls.reserve_webhook(event.idempotency_key):
        return WebhookAck(accepted=False, duplicate=True)
    attempt = self._calls.get_attempt(event.call_id) if event.call_id else None
    if attempt is None and event.conversation_id:
        attempt = self._calls.find_attempt_by_conversation_id(event.conversation_id)
    if attempt and event.call_status:
        attempt = attempt.model_copy(
            update={
                "status": event.call_status,
                "completed_at": (
                    event.event_timestamp
                    if event.call_status in {CallStatus.COMPLETED, CallStatus.FAILED}
                    else None
                ),
            }
        )
        self._calls.save_attempt(attempt)
    if attempt:
        self._calls.append_event(
            JobEvent(
                job_id=attempt.job_id,
                call_id=attempt.call_id,
                event_type=event.event_type,
                occurred_at=event.event_timestamp,
                metadata={"provider_status": event.provider_status},
            )
        )
    return WebhookAck(accepted=True, duplicate=False)
```

For unmatched conversations, acknowledge and reserve the replay key but do not fabricate a job event. `get_events` first calls `get_job` so unknown jobs remain 404. In dependencies, construct the processor with `ELEVENLABS_WEBHOOK_SECRET` in live mode and the constant `synthetic-webhook-secret` in mock mode; API tests sign with that explicit synthetic secret.

- [ ] **Step 6: Run security/idempotency tests and commit**

Run: `python -m pytest services/api/tests/test_webhooks.py services/api/tests/test_service.py -q`

Expected: valid delivery passes, invalid/stale signatures fail, duplicate delivery is acknowledged once, and no raw transcript field appears in normalized models or events.

Run: `python -m ruff check services/api/app/integrations/elevenlabs/webhook.py services/api/app/orchestration services/api/tests/test_webhooks.py`

Expected: `All checks passed!`

```bash
git add services/api/app/orchestration/models.py services/api/app/orchestration/service.py services/api/app/integrations/elevenlabs/webhook.py services/api/app/core/errors.py services/api/app/api/dependencies.py services/api/tests/test_webhooks.py
git commit -m "feat(api): normalize idempotent ElevenLabs webhooks"
```

### Task 7: Expose the Frozen Intake, Event, Health, and Webhook Routes

**Files:**

- Create: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py:1-79`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/main.py:1-41`
- Modify: `services/api/tests/test_api.py:1-79`
- Modify: `services/api/tests/test_openapi.py:8-25`
- Generate: `packages/contracts/openapi.json`
- Generate: `apps/web/src/api/schema.d.ts`

**Interfaces:**

- Consumes: Task 4 intake/lifecycle methods, Task 6 raw webhook method and events, and current settings.
- Produces: `POST /api/intake/document` and `GET /api/jobs/{job_id}/events`.
- Preserves: confirm, calls, webhook, negotiate, report, health, job read, structured job creation, and vendor discovery routes.

- [ ] **Step 1: Write failing frozen-route API and OpenAPI tests**

```python
def test_document_intake_and_events_routes(client):
    intake = client.post(
        "/api/intake/document",
        json={"document_text": "Synthetic two-bedroom move inventory."},
    )
    assert intake.status_code == 201
    job_id = intake.json()["job_spec"]["job_id"]
    assert intake.json()["job_spec"]["source_context"]["intake_method"] == "document"
    events = client.get(f"/api/jobs/{job_id}/events")
    assert events.status_code == 200
    assert events.json() == {"events": []}


def test_invalid_webhook_signature_is_401(client, signed_webhook_payload):
    body, _signature = signed_webhook_payload
    response = client.post(
        "/api/webhooks/elevenlabs",
        content=body,
        headers={"content-type": "application/json", "elevenlabs-signature": "bad"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "webhook_authentication_error"
```

Add `/api/intake/document` and `/api/jobs/{job_id}/events` to `test_openapi.py`'s required path tuple.

- [ ] **Step 2: Run route tests and verify 404/validation failures**

Run: `python -m pytest services/api/tests/test_api.py services/api/tests/test_openapi.py -q`

Expected: intake and events return 404, the current webhook route cannot validate a raw signature, and OpenAPI lacks both paths.

- [ ] **Step 3: Define route-local additive models**

```python
class DocumentIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    document_text: str = Field(min_length=1, max_length=50_000)


class RuntimeHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"] = "ok"
    mode: Literal["mock", "live"]
    service: Literal["veramove-api"] = "veramove-api"


class JobEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[JobEvent]


class PostCallWebhookData(BaseModel):
    model_config = ConfigDict(extra="allow")
    agent_id: str
    conversation_id: str
    status: str


class ElevenLabsPostCallWebhook(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["post_call_transcription"]
    event_timestamp: int
    data: PostCallWebhookData
```

Keep these models outside Member 2's canonical domain package. Define `WebhookRequest = ElevenLabsWebhookEvent | ElevenLabsPostCallWebhook` so OpenAPI remains typed while provider fields unrelated to orchestration are allowed and discarded.

- [ ] **Step 4: Implement the frozen handlers and raw-body webhook**

```python
@router.post(
    "/api/intake/document",
    response_model=JobRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["intake"],
)
def create_job_from_document(
    request: DocumentIntakeRequest,
    service: Service,
) -> JobRecord:
    return service.create_job_from_document(request.document_text)


@router.get(
    "/api/jobs/{job_id}/events",
    response_model=JobEventsResponse,
    tags=["jobs"],
)
def get_job_events(job_id: UUID, service: Service) -> JobEventsResponse:
    return JobEventsResponse(events=service.get_events(job_id))


@router.post(
    "/api/webhooks/elevenlabs",
    response_model=WebhookAck,
    tags=["webhooks"],
)
async def elevenlabs_webhook(
    request: Request,
    _event: Annotated[WebhookRequest, Body()],
    service: Service,
) -> WebhookAck:
    return service.handle_elevenlabs_webhook(
        await request.body(),
        request.headers.get("elevenlabs-signature"),
    )
```

FastAPI validates the typed body but Starlette retains the exact cached bytes used for HMAC verification. Replace the existing unsigned API idempotency test with two posts of the same byte string and valid synthetic signature. Make health return `RuntimeHealthResponse(mode=settings.app_mode)` through a `get_settings` dependency. Map `WebhookAuthenticationError` to 401, `WebhookPayloadError` to 400, `ProviderConfigurationError` to 409, and `ProviderRequestError` to 502 while preserving current 404/409 mappings.

- [ ] **Step 5: Run route tests, regenerate contracts, and verify generated diffs**

Run: `python -m pytest services/api/tests/test_api.py services/api/tests/test_openapi.py -q`

Expected: all route and OpenAPI tests pass.

Run: `python scripts/export_openapi.py`

Expected: `packages/contracts/openapi.json` contains both new paths and route-local schemas.

Run: `npm --prefix apps/web run generate:api`

Expected: `apps/web/src/api/schema.d.ts` changes only through generation and contains `DocumentIntakeRequest`, `RuntimeHealthResponse`, `JobEventsResponse`, and `ElevenLabsPostCallWebhook`.

Review: `git diff -- packages/contracts/openapi.json apps/web/src/api/schema.d.ts`

Expected: additive routes/schemas only; no canonical field deletion or type change.

- [ ] **Step 6: Run backend/frontend contract checks and commit**

Run: `python -m pytest services/api/tests -q`

Expected: all backend tests pass.

Run: `npm --prefix apps/web run typecheck`

Expected: TypeScript typecheck passes without handwritten frontend models.

```bash
git add services/api/app/api services/api/app/main.py services/api/tests/test_api.py services/api/tests/test_openapi.py packages/contracts/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat(api): expose intake events and signed webhooks"
```

### Task 8: Prove Outcome Coverage, Leverage Honesty, and the Full Mock Workflow

**Files:**

- Modify: `services/api/tests/test_voice_tools.py`
- Modify: `services/api/tests/test_service.py`
- Modify: `services/api/tests/test_api.py`
- Modify: `services/api/tests/test_webhooks.py`
- Modify only if a new test exposes a named invariant violation:
  - `services/api/app/orchestration/tools.py`
  - `services/api/app/orchestration/service.py`
  - `services/api/app/integrations/elevenlabs/webhook.py`

**Interfaces:**

- Consumes: the complete mock API, repositories, tools, and signed webhook path from Tasks 1-7.
- Produces: regression coverage for all four outcomes, fake leverage rejection, immutability, idempotency, and the complete intake-to-report sequence.

- [ ] **Step 1: Add all-outcome and fake-leverage tests**

Parameterize the three non-quote outcomes and assert exact canonical storage:

```python
@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (
            CallOutcome(
                type=CallOutcomeType.CALLBACK_COMMITMENT,
                callback_at=datetime(2026, 7, 19, 14, 0, tzinfo=UTC),
            ),
            CallStatus.COMPLETED,
        ),
        (
            CallOutcome(
                type=CallOutcomeType.DOCUMENTED_DECLINE,
                reason="Synthetic vendor declined the service area.",
            ),
            CallStatus.COMPLETED,
        ),
        (
            CallOutcome(
                type=CallOutcomeType.FAILED,
                reason="Synthetic transport failure.",
            ),
            CallStatus.FAILED,
        ),
    ],
)
def test_tools_store_every_non_quote_outcome(
    outcome,
    expected_status,
    repository,
    confirmed_record,
    fixtures,
):
    repository.create(confirmed_record)
    attempt = make_attempt(confirmed_record.job_spec, fixtures.load_vendors()[0])
    repository.create_attempt(attempt)
    call = VoiceTools(repository, repository).save_call_outcome(
        attempt.call_id,
        outcome,
        datetime(2026, 7, 18, 17, 0, tzinfo=UTC),
        "https://recordings.example.com/synthetic-outcome.mp3",
    )
    assert call.outcome == outcome
    assert repository.get_attempt(attempt.call_id).status is expected_status
```

Create leverage cases by `model_copy`: same target vendor, `PARTIALLY_VERIFIED`, empty evidence, empty verified data, wrong job ID, and a nonvalidating copy with `job_spec_version="0.9"`. Assert every case is absent from `get_verified_competing_quote` and therefore raises `DomainConflict` through `VoiceTools`.

- [ ] **Step 2: Add repeated-call and full API workflow tests**

```python
def test_complete_document_to_report_flow_is_idempotent(client):
    intake = client.post(
        "/api/intake/document",
        json={"document_text": "Synthetic inventory for the VeraMove demo."},
    )
    job_id = intake.json()["job_spec"]["job_id"]

    first_confirm = client.post(f"/api/jobs/{job_id}/confirm")
    second_confirm = client.post(f"/api/jobs/{job_id}/confirm")
    assert first_confirm.json() == second_confirm.json()

    first_calls = client.post(f"/api/jobs/{job_id}/calls")
    second_calls = client.post(f"/api/jobs/{job_id}/calls")
    assert first_calls.json() == second_calls.json()
    assert len(first_calls.json()["calls"]) == 3
    assert {
        item["outcome"]["type"] for item in first_calls.json()["calls"]
    } == {"itemized_quote"}
    assert {
        item["outcome"]["quote"]["job_spec_version"]
        for item in first_calls.json()["calls"]
    } == {"1.0"}

    completed = client.post(f"/api/jobs/{job_id}/negotiate")
    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"
    assert len(completed.json()["quotes"]) == 4
    repeated = client.post(f"/api/jobs/{job_id}/negotiate")
    assert repeated.json() == completed.json()

    report = client.get(f"/api/jobs/{job_id}/report")
    assert report.status_code == 200
    assert report.json()["rankings"][0]["evidence_ids"]
    assert all(item["recording_url"] for item in report.json()["transcript_evidence"])
```

Add a service assertion that all three `CallAttempt.job_spec_snapshot` values equal the confirmed snapshot, not only its version string.

- [ ] **Step 3: Add webhook edge tests**

Test a valid signed event with an unknown provider status. Assert it is accepted, creates one safe event, leaves the attempt status unchanged, and includes neither `transcript` nor `phone` keys after JSON serialization. Test the same bytes twice and assert one event. At the processor unit boundary, test signed malformed JSON and assert `WebhookPayloadError` occurs before a replay key can be reserved.

- [ ] **Step 4: Run the new tests red, then make only named invariant corrections**

Run: `python -m pytest services/api/tests/test_voice_tools.py services/api/tests/test_service.py services/api/tests/test_api.py services/api/tests/test_webhooks.py -q`

Expected before corrections: any failure identifies one of these exact defects:

- quote eligibility fails to exclude one listed fake-leverage case;
- repeated confirm/calls creates a different aggregate;
- a call attempt stores a mutable rather than defensive JobSpec snapshot;
- unknown webhook status changes a call to completed;
- replay creates more than one event.

Correct only the corresponding predicate, state guard, `model_copy(deep=True)` call, status mapping, or replay reservation order. Do not alter canonical contracts or add new outcome values.

- [ ] **Step 5: Re-run the focused and complete backend suites**

Run: `python -m pytest services/api/tests/test_voice_tools.py services/api/tests/test_service.py services/api/tests/test_api.py services/api/tests/test_webhooks.py -q`

Expected: all focused tests pass.

Run: `python -m pytest services/api/tests -q`

Expected: the entire backend suite passes with no external network request.

Run: `python -m ruff check services/api/app services/api/tests`

Expected: `All checks passed!`

- [ ] **Step 6: Commit the safety regression suite**

```bash
git add services/api/tests/test_voice_tools.py services/api/tests/test_service.py services/api/tests/test_api.py services/api/tests/test_webhooks.py services/api/app/orchestration/tools.py services/api/app/orchestration/service.py services/api/app/integrations/elevenlabs/webhook.py
git commit -m "test(api): cover voice lifecycle and safety invariants"
```

### Task 9: Add the Backend Runbook, Contract Handoff, and Release Evidence

**Files:**

- Create: `docs/backend-voice-runbook.md`
- Create: `docs/backend-voice-pr-summary.md`
- Modify: `docs/integration-boundaries.md:1-30`
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md:14-25,62-79`
- Modify: `services/api/tests/test_documentation.py`
- Verify generated: `packages/contracts/openapi.json`
- Verify generated: `apps/web/src/api/schema.d.ts`

**Interfaces:**

- Consumes: all implemented routes, settings, tests, and generated schemas.
- Produces: exact mock smoke commands, a manual-only live checklist, release gates, PR summary, contract-impact note, and known limitations.

- [ ] **Step 1: Write a failing runbook-completeness test**

```python
RUNBOOK = (ROOT / "docs/backend-voice-runbook.md").read_text(encoding="utf-8")
PR_SUMMARY = (ROOT / "docs/backend-voice-pr-summary.md").read_text(encoding="utf-8")


def test_backend_voice_runbook_documents_safety_and_release_gates():
    for text in (
        "APP_MODE=mock",
        "LIVE_CALLS_ENABLED=true",
        "LIVE_TEST_TO_NUMBER",
        "python scripts/check.py",
        "Do not run the live smoke test from CI",
        "No release tag before code freeze",
    ):
        assert text in RUNBOOK
    for heading in (
        "Summary",
        "Routes",
        "Safety controls",
        "Test evidence",
        "Contract impact",
        "Known limitations",
    ):
        assert f"## {heading}" in PR_SUMMARY
```

- [ ] **Step 2: Run the documentation test and verify the files are missing**

Run: `python -m pytest services/api/tests/test_documentation.py -q`

Expected: collection fails because both backend voice documents do not exist.

- [ ] **Step 3: Write exact mock and manual-only live procedures**

The runbook's mock section uses:

```bash
python scripts/bootstrap.py
python scripts/check.py
APP_MODE=mock python scripts/dev.py
```

It then lists the HTTP order: document intake, confirm, calls, negotiate, report, and events. It states that repeated confirm/calls are safe and that all demo records are synthetic.

The live checklist requires a human to:

1. confirm the destination owner has opted in;
2. export all ElevenLabs IDs, secret, and `LIVE_TEST_TO_NUMBER` without writing them to a file;
3. configure the ElevenLabs webhook URL and imported Twilio number;
4. start with `APP_MODE=live` and `LIVE_CALLS_ENABLED=true`;
5. create and confirm one synthetic job;
6. invoke one call only;
7. inspect provider dashboards and the provider-neutral events route;
8. unset live variables immediately afterward.

State verbatim: `Do not run the live smoke test from CI` and `No release tag before code freeze`. Do not include a dialable example number or a command that automatically invokes the calls route.

- [ ] **Step 4: Update integration and architecture truth without changing ownership**

Change `docs/integration-boundaries.md` to state:

- mock providers remain the default;
- the optional live adapter uses ElevenLabs' native Twilio outbound endpoint through HTTPX;
- Twilio credentials are not sent by VeraMove because the imported phone-number ID is managed in ElevenLabs;
- signed webhooks are normalized without retaining raw transcripts;
- OpenAI and Tavily remain deterministic in this slice;
- Supabase remains unwired.

Update `AGENTS.md` from “only mocks are wired” to “mock adapters are wired by default; live voice is fail-closed behind explicit settings.” Replace the starter-era statement prohibiting all real adapters with the actual rule that real adapters may never silently activate. Do not change contributor names, directories, or narrative gates.

Update `docs/architecture.md` with the internal `CallAttempt` boundary and the two additive frozen routes.

- [ ] **Step 5: Prepare the PR summary with concrete evidence slots already resolved**

Write:

- **Summary:** five injected boundaries, single-call composition, gated native live voice, signed webhook/event storage, and verified negotiation.
- **Routes:** list all frozen endpoints and retained compatibility routes.
- **Safety controls:** default mock, three live gates, no test dialing, no raw transcript logs, HMAC/timestamp/replay checks.
- **Test evidence:** exact final `python scripts/check.py` result and focused test files.
- **Contract impact:** additive intake, events, and runtime-health schemas; no canonical field change; generated artifacts require Member 2/frontend owner review.
- **Known limitations:** in-memory persistence, the controlled live path intentionally places at most one test call and does not produce a live report, live intelligence remains deterministic, no automatic booking/payment, post-call raw transcript is intentionally not persisted, and no release tag.

- [ ] **Step 6: Run the repository validation pipeline**

Run: `python scripts/check.py`

Expected in order:

1. Ruff passes.
2. All backend pytest tests pass.
3. OpenAPI export succeeds without an uncommitted post-export diff.
4. TypeScript API generation succeeds without an uncommitted post-generation diff.
5. Frontend typecheck passes.
6. Frontend tests pass.
7. Vite production build passes.

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short`

Expected: only the runbook, PR summary, architecture/integration guidance, AGENTS wording, and their documentation test are uncommitted.

- [ ] **Step 7: Commit release hygiene without tagging**

```bash
git add AGENTS.md docs/architecture.md docs/integration-boundaries.md docs/backend-voice-runbook.md docs/backend-voice-pr-summary.md services/api/tests/test_documentation.py
git commit -m "docs(repo): add backend smoke and release runbook"
```

- [ ] **Step 8: Produce the final branch handoff**

Run: `git log --oneline main..HEAD`

Expected: the approved design commit plus focused ownership, repository, agent/tool, orchestration, live voice, webhook, API, safety-test, and runbook commits.

Run: `git status --short --branch`

Expected: `## feat/member-1-backend-voice` with no modified or untracked files.

Do not push, merge, create a release, tag a commit, or place a live call unless the user separately asks for that external action.
