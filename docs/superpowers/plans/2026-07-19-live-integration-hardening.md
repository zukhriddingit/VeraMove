# VeraMove Live Integration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make simultaneously enabled OpenAI, Tavily, and Supabase complete VeraMove's evidence-backed mock workflow with canonical document metadata and explicitly role-play outcomes for discovered vendors.

**Architecture:** Normalize only OpenAI-owned completeness metadata after validating the returned JobSpec, leaving all move facts unmodified. Extend the mock voice boundary—not discovery or ranking—to create neutral role-play quote evidence for unfamiliar vendors, and harden orchestration so provider-domain failures persist a failed attempt and failed job.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, existing injected provider protocols, Supabase PostgREST repository, Ruff, OpenAPI generation, TypeScript/Vitest/Vite repository gates.

## Global Constraints

- `APP_MODE=mock` remains the credential-free default.
- Exactly three initial mock calls use the same confirmed `JobSpecV1` snapshot.
- Tavily supplies vendor identity and discovery provenance only; simulated quote facts are `role_play` and explicitly disclaimed.
- OpenAI normalization may compute `missing_fields` but may not invent, confirm, or lock move facts.
- No real phone calls, contact details, customer PII, recordings, or raw transcripts are added.
- No route or public schema changes are introduced.
- Enabled-provider failures never silently fall back.

---

### Task 1: Canonicalize OpenAI Missing-Field Metadata

**Files:**
- Modify: `services/api/app/integrations/openai/document.py`
- Test: `services/api/tests/test_openai_live.py`
- Test: `services/api/tests/test_intelligence.py`

**Interfaces:**
- Consumes: `StructuredDocumentClient.parse(...) -> DocumentParseResult | dict[str, Any]`, `JobSpecV1.missing_required_fields() -> list[str]`.
- Produces: `OpenAIDocumentParser.parse_document(...) -> DocumentParseResult` whose `missing_fields` exactly matches the validated JobSpec.

- [ ] **Step 1: Write the failing normalization test**

```python
from copy import deepcopy


def test_document_parser_normalizes_model_missing_fields_without_mutating_response(fixtures):
    response = document_result(fixtures)
    response["missing_fields"] = []
    response["warnings"] = ["Synthetic warning remains."]
    original = deepcopy(response)
    parser = OpenAIDocumentParser(
        OpenAIResponsesClient(
            api_key="synthetic",
            transport=RecordingTransport(completed_response(response)),
        ),
        model="gpt-5.6-luna",
    )

    parsed = parser.parse_document(b"synthetic", "text/plain", "synthetic.txt")

    assert parsed.missing_fields == parsed.job_spec.missing_required_fields()
    assert parsed.warnings == ["Synthetic warning remains."]
    assert response == original
```

- [ ] **Step 2: Run the test and verify the current strict final validation fails**

Run: `.venv/bin/pytest services/api/tests/test_openai_live.py::test_document_parser_normalizes_model_missing_fields_without_mutating_response -v`

Expected: FAIL with `missing_fields must exactly match the incomplete JobSpec fields`.

- [ ] **Step 3: Implement two-stage validation**

```python
from copy import deepcopy

from services.api.app.contracts import DocumentParseResult, IntakeSource, JobSpecV1


def _normalize_document_result(
    response: DocumentParseResult | dict[str, object],
) -> DocumentParseResult:
    payload = (
        response.model_dump(mode="python")
        if isinstance(response, DocumentParseResult)
        else deepcopy(response)
    )
    job_spec = JobSpecV1.model_validate(payload.get("job_spec"))
    payload["job_spec"] = job_spec.model_dump(mode="python")
    payload["missing_fields"] = job_spec.missing_required_fields()
    return DocumentParseResult.model_validate(payload)
```

Call the helper immediately after the structured client returns. Keep the existing document-source, confirmation, and lock postconditions unchanged.

- [ ] **Step 4: Add invalid-envelope coverage and run focused tests**

Add assertions that an unexpected top-level field and invalid `job_spec` still raise Pydantic `ValidationError`.

Run: `.venv/bin/pytest services/api/tests/test_openai_live.py services/api/tests/test_intelligence.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the OpenAI fix**

```bash
git add services/api/app/integrations/openai/document.py services/api/tests/test_openai_live.py services/api/tests/test_intelligence.py
git commit -m "fix(openai): normalize document completeness metadata"
```

---

### Task 2: Generate Honest Role-Play Quotes for Discovered Vendors

**Files:**
- Modify: `services/api/app/integrations/elevenlabs/mock.py`
- Test: `services/api/tests/test_voice_tools.py`
- Test: `services/api/tests/test_service.py`

**Interfaces:**
- Consumes: any validated `Vendor`, the locked `JobSpecV1`, and persisted `call_id`.
- Produces: a synchronous `VoiceCallResult` with an itemized `QuoteV1`, role-play evidence, and synthetic recording URL for vendors without exact fixtures.

- [ ] **Step 1: Write failing arbitrary-vendor adapter tests**

Create a role-play vendor with a fresh UUID and Tavily provenance, then assert:

```python
from services.api.app.contracts import (
    DataClassification,
    ProvenanceReference,
    ProvenanceType,
)


vendor = fixtures.load_vendors()[0].model_copy(
    update={
        "vendor_id": uuid4(),
        "name": "Example Moving Cooperative",
        "slug": "example-moving-cooperative",
        "behavior_summary": (
            "Role-play discovery candidate; no real behavior is inferred."
        ),
        "contact_label": "Role-play channel; no contact details stored.",
        "data_classification": DataClassification.ROLE_PLAY,
        "provenance": [
            ProvenanceReference(
                source_type=ProvenanceType.TAVILY,
                source_id="vendor.example.com",
                location="https://vendor.example.com/moving",
            )
        ],
    },
    deep=True,
)
call_id = uuid4()
result = MockVoiceProvider(fixtures).initiate_quote_call(job_spec, vendor, call_id)
quote = result.outcome.quote

assert quote.vendor.vendor_id == vendor.vendor_id
assert quote.job_id == job_spec.job_id
assert quote.job_spec_version == job_spec.version
assert quote.data_classification is DataClassification.ROLE_PLAY
assert quote.red_flags == []
assert quote.quote_id != fixtures.load_initial_quotes()[0].quote_id
assert all(item.call_id == call_id for item in quote.transcript_evidence)
assert all(
    item.data_classification is DataClassification.ROLE_PLAY
    for item in quote.transcript_evidence
)
assert all(
    "not a claim" in item.excerpt.casefold()
    for item in quote.transcript_evidence
)
assert str(quote.recording_url).startswith(
    "https://recordings.example.com/role-play/"
)
```

Add a second call and assert quote IDs, evidence IDs, recording URLs, and provider IDs are distinct.

- [ ] **Step 2: Run adapter tests and verify `ResourceNotFound`**

Run: `.venv/bin/pytest services/api/tests/test_voice_tools.py -k 'role_play or arbitrary_vendor' -v`

Expected: FAIL because the current provider only accepts fixture vendor IDs.

- [ ] **Step 3: Implement role-play rebinding**

In `MockVoiceProvider`:

```python
from uuid import NAMESPACE_URL, UUID, uuid5

from services.api.app.contracts import DataClassification

ROLE_PLAY_NOTICE = (
    "Role-play simulation only; this is not a claim about the company's "
    "actual pricing, availability, or conduct."
)
```

Use the existing exact fixture when one matches. Otherwise use the transparent first quote as a neutral template and route through `_rebind_quote`. When the vendor is role play, rebind:

```python
recording_url = f"https://recordings.example.com/role-play/{call_id}"
role_play_vendor = vendor.model_copy(
    update={"data_classification": DataClassification.ROLE_PLAY},
    deep=True,
)
evidence = [
    item.model_copy(
        update={
            "evidence_id": uuid5(
                NAMESPACE_URL,
                f"role-play-evidence:{call_id}:{index}",
            ),
            "call_id": call_id,
            "excerpt": (
                f"{ROLE_PLAY_NOTICE} The synthetic comparable total is "
                f"{quote.comparable_total} USD."
            ),
            "claim": "Synthetic role-play quote evidence only; not a company claim.",
            "recording_url": recording_url,
            "data_classification": DataClassification.ROLE_PLAY,
        },
        deep=True,
    )
    for index, item in enumerate(quote.transcript_evidence)
]
```

Also derive a unique quote ID from `call_id`, clear red flags, prefix concessions as role-play, add `role_play_notice` to verified metadata, update availability with the notice, set quote classification to role play, and preserve Tavily provenance only inside the vendor record.

- [ ] **Step 4: Exercise three unfamiliar discovery vendors**

Extend the service test to inject three distinct role-play vendors. Assert three calls and quotes, identical locked snapshots, distinct IDs, `quotes_ready`, and no hidden-fee/company-behavior claims.

Run: `.venv/bin/pytest services/api/tests/test_voice_tools.py services/api/tests/test_service.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the mock-provider behavior**

```bash
git add services/api/app/integrations/elevenlabs/mock.py services/api/tests/test_voice_tools.py services/api/tests/test_service.py
git commit -m "fix(voice): role-play discovered vendor quotes"
```

---

### Task 3: Persist Failure Recovery and Role-Play Aggregates

**Files:**
- Modify: `services/api/app/orchestration/service.py`
- Test: `services/api/tests/test_service.py`
- Test: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- Consumes: a persisted pending `CallAttempt` and a provider-raised `DomainError`.
- Produces: the same re-raised error plus persisted `CallStatus.FAILED` and `JobState.FAILED` state.

- [ ] **Step 1: Write the failure-recovery test**

```python
from services.api.app.core.errors import ResourceNotFound


class FailingDomainVoice:
    initial_call_limit = 3

    def initiate_quote_call(self, job_spec, vendor, call_id):
        del job_spec, vendor, call_id
        raise ResourceNotFound("Synthetic provider-domain failure")


def test_provider_domain_failure_does_not_leave_job_calling(service, job_spec):
    service._voice = FailingDomainVoice()
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    with pytest.raises(ResourceNotFound, match="Synthetic provider-domain failure"):
        service.start_calls(job_spec.job_id)

    attempts = service.list_call_attempts(job_spec.job_id)
    assert len(attempts) == 1
    assert attempts[0].status is CallStatus.FAILED
    assert attempts[0].completed_at is not None
    assert service.get_job(job_spec.job_id).state is JobState.FAILED
```

- [ ] **Step 2: Run the test and verify the job remains `calling`**

Run: `.venv/bin/pytest services/api/tests/test_service.py::test_provider_domain_failure_does_not_leave_job_calling -v`

Expected: FAIL because `ResourceNotFound` is not in the current provider catch tuple.

- [ ] **Step 3: Catch provider-boundary domain errors**

Import `DomainError` and change only the provider-call handler after attempt creation:

```python
try:
    result = self._voice.initiate_quote_call(
        attempt.job_spec_snapshot,
        vendor,
        attempt.call_id,
    )
except DomainError:
    self._record_provider_failure(attempt)
    raise
```

Do not catch arbitrary exceptions or validation/programming failures.

- [ ] **Step 4: Verify Supabase can round-trip a role-play outcome**

Add a fake-table-client test that persists an unfamiliar role-play vendor attempt, mock result, canonical call, quote, and evidence. Assert the reconstructed aggregate matches and the vendor, quote, and evidence rows retain `data_classification=role_play`.

Run: `.venv/bin/pytest services/api/tests/test_service.py services/api/tests/test_supabase_repository.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit recovery and persistence coverage**

```bash
git add services/api/app/orchestration/service.py services/api/tests/test_service.py services/api/tests/test_supabase_repository.py
git commit -m "fix(orchestration): fail completed call attempts safely"
```

---

### Task 4: Repository Gates, Deployment, and Live Verification

**Files:**
- Verify: `openapi/openapi.json`
- Verify: `apps/web/src/api/generated/schema.d.ts`
- Verify: `render.yaml`

**Interfaces:**
- Consumes: the three focused implementation commits and existing Render-managed secrets.
- Produces: a pushed deployment with live OpenAI/Tavily/Supabase smoke-test evidence.

- [ ] **Step 1: Run focused integration suites**

Run:

```bash
.venv/bin/pytest services/api/tests/test_openai_live.py services/api/tests/test_voice_tools.py services/api/tests/test_service.py services/api/tests/test_supabase_repository.py -q
```

Expected: all selected tests pass without external requests.

- [ ] **Step 2: Run the mandatory repository gate**

Run: `.venv/bin/python scripts/check.py`

Expected: Ruff, all backend tests, OpenAPI export, frontend API generation, TypeScript typecheck, Vitest, and Vite production build pass.

- [ ] **Step 3: Run evaluation fixtures**

Run: `.venv/bin/python -m evals.run`

Expected: `14/14` scenarios pass or better.

- [ ] **Step 4: Confirm no secret or generated-contract drift**

Run:

```bash
git diff --check
git status --short
git diff -- openapi/openapi.json apps/web/src/api/generated/schema.d.ts
```

Expected: no secrets, no whitespace errors, and no unexpected public schema change.

- [ ] **Step 5: Push and monitor Render**

Run: `git push origin deploy/veramove-demo`

Verify Render reports the new commit live and `/health` returns HTTP 200.

- [ ] **Step 6: Run the live synthetic workflow**

1. Call `GET /api/vendors/discover` with synthetic Boston-area inputs and assert `source=tavily` with at least three provenance-bearing vendors.
2. Call `POST /api/intake/document` with a fully synthetic moving brief and assert HTTP 201, `intake_source=document`, and `confirmed=false`.
3. Read the job back through `GET /api/jobs/{job_id}` to prove Supabase persistence.
4. Confirm the job and call `POST /api/jobs/{job_id}/calls`.
5. Assert `state=quotes_ready`, exactly three calls/quotes, identical locked JobSpec version, role-play classification, unique evidence IDs, and synthetic recording URLs.
6. Call negotiation and report endpoints; assert completion, measurable price/term improvement, and evidence-backed rankings.

- [ ] **Step 7: Record final evidence**

Report the deployed commit, test counts, evaluation result, synthetic job ID, Tavily source, call/quote counts, and any remaining unrelated live-ElevenLabs webhook limitation.
