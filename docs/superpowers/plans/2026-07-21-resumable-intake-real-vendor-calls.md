# Resumable Intake and Consent-Gated Real Vendor Calls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make interrupted browser voice intake resumable or manually finishable, and connect exactly three reviewed real-vendor contacts to research-aware ElevenLabs quote calls without weakening consent, privacy, or JobSpec locking.

**Architecture:** Signed ElevenLabs results materialize either a complete or incomplete canonical intake session; incomplete sessions store only an unlocked `JobSpecV1` base and permit one compare-and-set recovery action. Selected official websites yield deterministic public business contact candidates; exactly three server-owned, recipient-consented authorizations produce bounded vendor call plans that the voice adapter resolves at dispatch time without persisting phone numbers in attempts or events.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, Supabase/PostgreSQL RPCs, httpx, ElevenLabs Conversational AI/Twilio, Tavily Extract, React 19, TanStack Router/Query, TypeScript 5.8, Vitest, Ruff, pytest.

## Global Constraints

- FastAPI-generated OpenAPI is the canonical browser contract.
- `APP_MODE=mock` must work without provider credentials or Supabase.
- `REAL_VENDOR_CALLS_ENABLED=false` is the default.
- Voice, document, resumed, and manual intake all produce `JobSpecV1`; only the existing confirmation endpoint locks it.
- Exactly three initial quote attempts use one locked JobSpec version and SHA-256 snapshot.
- Website claims remain `unverified_website_claim` and never become quote or negotiation evidence.
- Real-vendor dispatch accepts only `data_classification=real_redacted` and city/state-level route facts.
- A public business number is not recipient consent. Official-business calls require current affirmative opt-in for the AI call and recording, suppression clearance, and a permitted local call time.
- Never persist raw transcripts, provider analysis, audio, API secrets, customer phone numbers, or destination numbers in jobs, events, call attempts, fixtures, or logs.
- Tests and deployment verification use only synthetic `+1555...` numbers or the user's already approved test destinations; never place an unsolicited real-business call.
- Presentation components use the centralized typed client and never call `fetch` directly.
- Every public contract change follows Pydantic -> `python scripts/export_openapi.py` -> `npm --prefix apps/web run generate:api`.

---

## File Structure

### New focused files

- `services/api/app/contracts/vendor_calls.py` — contact, consent, authorization, suppression, and bounded call-plan contracts.
- `services/api/app/orchestration/intake_recovery.py` — provider-result recovery plus one-action resume/manual orchestration.
- `services/api/app/orchestration/vendor_contacts.py` — official-host contact extraction, normalization, authorization, and suppression checks.
- `services/api/app/orchestration/vendor_call_plans.py` — deterministic, capped research-aware quote agenda.
- `supabase/migrations/202607210007_resumable_intake_vendor_calls.sql` — additive intake columns/status, authorization/suppression tables, and atomic RPCs.
- `services/api/tests/test_intake_recovery.py` — resume/manual/recovery service tests.
- `services/api/tests/test_vendor_contacts.py` — extraction, authorization, suppression, and calling-window tests.
- `services/api/tests/test_vendor_call_plans.py` — research-aware agenda tests.
- `apps/web/src/lib/voice/browserVoiceState.ts` — pure intake phase transition/poll-decision helpers.
- `apps/web/src/components/veramove/VendorContactReview.tsx` — exactly-three contact/consent review.

### Existing files modified

- `services/api/app/orchestration/intake_sessions.py` — incomplete state, immutable intake mode, partial/base snapshots, lineage, and views.
- `services/api/app/orchestration/models.py` — authorization reference on call attempts.
- `services/api/app/orchestration/voice_materializer.py` — complete-versus-incomplete intake branching and base-snapshot merge.
- `services/api/app/orchestration/providers.py` — provider-neutral `VoiceCallDestination` and `VendorCallPlanV1` quote signature.
- `services/api/app/orchestration/service.py` — exactly-three official-business dispatch gates.
- `services/api/app/orchestration/vendor_research.py` — contact extraction/authorization entry points and call-plan persistence.
- `services/api/app/repositories/base.py`, `memory.py`, `supabase.py`, `supabase_client.py` — new protocol and persistence operations.
- `services/api/app/api/models.py`, `router.py`, `dependencies.py` — typed intake recovery and contact routes.
- `services/api/app/core/config.py` — real-call feature flag and strong contact-hash secret.
- `services/api/app/integrations/elevenlabs/live.py`, `mock.py`, `models.py` — destination object, call-plan variables, recording flag, and opt-out parsing.
- `services/api/app/integrations/elevenlabs/conversations.py` — reusable terminal intake repair snapshot.
- `services/api/app/contracts/__init__.py` — public contract exports.
- `agents/intake/prompt.md`, `agent.yaml`, `README.md` — redacted-real/resume variables and behavior.
- `agents/negotiator/prompt.md`, `agent.yaml`, `README.md`, `data-collection.json` — call context, targeted agenda, and opt-out collection.
- `agents/elevenlabs-dashboard-checklist.md`, `scripts/live_voice_preflight.py` — exact provider schema checks.
- `apps/web/src/api/client.ts`, generated `schema.d.ts`, `lib/api/endpoints.ts`, `lib/api/hooks.ts` — typed methods and mutations.
- `apps/web/src/lib/voice/useBrowserVoiceIntake.ts`, `components/veramove/LiveVoiceIntakePanel.tsx`, `routes/intake.tsx` — mode selection and terminal recovery UX.
- `apps/web/src/components/veramove/VendorResearchPanel.tsx`, `routes/calls.$jobId.tsx` — contact review, plan preview, and dispatch readiness.
- `.env.example`, `docs/backend-voice-runbook.md` — new fail-closed settings and operational steps.

---

### Task 1: Contract the incomplete intake lifecycle

**Files:**
- Modify: `services/api/app/orchestration/intake_sessions.py`
- Modify: `services/api/app/orchestration/models.py`
- Modify: `services/api/app/api/models.py`
- Test: `services/api/tests/test_intake_sessions.py`
- Test: `services/api/tests/test_contracts.py`

**Interfaces:**
- Produces: `IntakeDataMode`, `IntakeRecoveryAction`, `IntakeSessionStatus.INCOMPLETE`,
  expanded `IntakeSession`, `IntakeSessionView`, and `CreateIntakeSessionRequest`.
- Consumes: existing `JobSpecV1.missing_required_fields()` and `DataClassification`.

- [ ] **Step 1: Add failing contract and state tests**

```python
def test_incomplete_intake_requires_partial_spec_and_missing_fields(job_spec):
    partial = job_spec.model_copy(update={"move_date": None, "confirmed": False})
    session = intake_session(
        status=IntakeSessionStatus.INCOMPLETE,
        data_mode=IntakeDataMode.SUPERVISED_ROLE_PLAY,
        partial_job_spec=partial,
        missing_fields=partial.missing_required_fields(),
        terminal_reason="user_ended_before_summary",
    )
    assert session.partial_job_spec == partial
    assert session.missing_fields == partial.missing_required_fields()


def test_incomplete_intake_rejects_raw_transcript_shape(job_spec):
    with pytest.raises(ValidationError):
        intake_session(
            status="incomplete",
            partial_job_spec=job_spec.model_dump() | {"transcript": []},
            missing_fields=job_spec.missing_required_fields(),
        )
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_intake_sessions.py services/api/tests/test_contracts.py -q`
Expected: FAIL because `IntakeDataMode`, `INCOMPLETE`, and partial fields do not exist.

- [ ] **Step 3: Add the strict lifecycle types**

```python
class IntakeDataMode(StrEnum):
    SUPERVISED_ROLE_PLAY = "supervised_role_play"
    REAL_REDACTED = "real_redacted"


class IntakeRecoveryAction(StrEnum):
    RESUME = "resume"
    MANUAL = "manual"


class IntakeSessionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_INTAKE_STATUSES = frozenset(
    {
        IntakeSessionStatus.INCOMPLETE,
        IntakeSessionStatus.COMPLETED,
        IntakeSessionStatus.FAILED,
    }
)
```

Add `data_mode`, `partial_job_spec`, `base_job_spec`, `missing_fields`, `terminal_reason`,
`recovery_action`, `recovery_target_id`, and `resumed_from_session_id` with validators that enforce
the mutually exclusive completed/incomplete/failed shapes. Add `CreateIntakeSessionRequest` with
`data_mode=supervised_role_play` and expose only safe partial/recovery fields through
`IntakeSessionResponse`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_intake_sessions.py services/api/tests/test_contracts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/orchestration/intake_sessions.py services/api/app/orchestration/models.py services/api/app/api/models.py services/api/tests/test_intake_sessions.py services/api/tests/test_contracts.py
git commit -m "feat: contract incomplete voice intake"
```

### Task 2: Persist incomplete sessions and atomic recovery actions

**Files:**
- Create: `supabase/migrations/202607210007_resumable_intake_vendor_calls.sql`
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase.py`
- Modify: `services/api/app/repositories/supabase_client.py`
- Test: `services/api/tests/test_supabase_repository.py`
- Test: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**
- Consumes: Task 1 session and materialization types.
- Produces: `VoiceIntakeIncomplete`, the expanded discriminated `VoiceIntakeMaterialization`,
  `finalize_voice_intake_webhook(... VoiceIntakeIncomplete ...)`,
  `claim_intake_resume(session_id, child)`, and `finish_intake_manually(session_id, job)` repository
  operations.

- [ ] **Step 1: Add failing repository tests for incomplete and compare-and-set recovery**

```python
def test_repository_finalizes_incomplete_without_job(repository, incomplete_materialization):
    result = repository.finalize_voice_intake_webhook(
        "receipt-incomplete", UUID(int=7), incomplete_materialization, NOW
    )
    assert result.processed is True
    assert repository.get(incomplete_materialization.session.job_id) is None
    assert repository.get_intake_session(
        incomplete_materialization.session.intake_session_id
    ).status is IntakeSessionStatus.INCOMPLETE


def test_resume_and_manual_finish_are_mutually_exclusive(repository, incomplete_session, child):
    repository.claim_intake_resume(incomplete_session.intake_session_id, child, NOW)
    with pytest.raises(DomainConflict):
        repository.finish_intake_manually(
            incomplete_session.intake_session_id, manual_job(incomplete_session), NOW
        )
```

- [ ] **Step 2: Run repository tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_repository.py services/api/tests/test_repository_and_adapters.py -q`
Expected: FAIL because the status/check constraints and atomic operations are absent.

- [ ] **Step 3: Add the additive migration**

The migration must:

```sql
alter table public.intake_sessions
    add column if not exists data_mode text not null default 'supervised_role_play',
    add column if not exists partial_job_spec jsonb,
    add column if not exists base_job_spec jsonb,
    add column if not exists missing_fields jsonb,
    add column if not exists terminal_reason text,
    add column if not exists recovery_action text,
    add column if not exists recovery_target_id uuid,
    add column if not exists resumed_from_session_id uuid;

alter table public.intake_sessions drop constraint if exists intake_sessions_status_check;
alter table public.intake_sessions add constraint intake_sessions_status_check
    check (status in ('pending','in_progress','incomplete','completed','failed'));
```

Replace `veramove_finalize_voice_intake_webhook` so `p_kind='incomplete'` atomically stores the
strict partial spec and processes the receipt without inserting a job. Add security-definer RPCs
`veramove_claim_intake_resume` and `veramove_finish_intake_manually`; both lock the source row,
require `status='incomplete'`, and set exactly one `recovery_action`.

- [ ] **Step 4: Implement memory and Supabase repository methods**

```python
def claim_intake_resume(self, session_id: UUID, child: IntakeSession, now: datetime) -> IntakeSession:
    source = self._require_intake_session(session_id)
    if source.recovery_action is IntakeRecoveryAction.RESUME:
        return self._require_intake_session(source.recovery_target_id)
    if source.recovery_action is not None:
        raise DomainConflict("Incomplete intake already has a recovery action")
    return self._atomic_store_resume(source, child, now)
```

Mirror the same result validation around the two Supabase RPC responses. Keep exact destination and
transcript-shaped keys forbidden.

- [ ] **Step 5: Run repository tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_supabase_repository.py services/api/tests/test_repository_and_adapters.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/202607210007_resumable_intake_vendor_calls.sql services/api/app/repositories services/api/tests/test_supabase_repository.py services/api/tests/test_repository_and_adapters.py
git commit -m "feat: persist resumable intake sessions"
```

### Task 3: Materialize complete versus incomplete voice intake

**Files:**
- Modify: `services/api/app/orchestration/voice_materializer.py`
- Modify: `services/api/app/integrations/elevenlabs/models.py`
- Test: `services/api/tests/test_voice_materialization.py`
- Test: `services/api/tests/test_async_voice_orchestration.py`

**Interfaces:**
- Consumes: Task 2 `VoiceIntakeIncomplete` and atomic finalizer.
- Produces: `_intake_job_spec(event, session, require_summary: bool)` and `_merge_intake_specs(base, collected)`.

- [ ] **Step 1: Add failing partial-materialization tests**

```python
def test_post_call_without_summary_materializes_incomplete(service, intake_event):
    partial_event = intake_event.model_copy(
        update={"collected_data": intake_event.collected_data | {"summary_confirmed": False}}
    )
    ack = service.materialize(partial_event)
    session = service.find_intake_session_by_conversation_id(partial_event.conversation_id)
    assert ack.accepted is True
    assert session.status is IntakeSessionStatus.INCOMPLETE
    assert session.partial_job_spec.move_date == date(2026, 8, 27)
    assert "destination.address_summary" in session.missing_fields


def test_resumed_completion_preserves_known_base_fields(service, resumed_event):
    service.materialize(resumed_event)
    job = service.get_job(resumed_event.dynamic_variables.job_id)
    assert job.job_spec.move_date == date(2026, 8, 27)
    assert job.job_spec.destination.address_summary == "Boston, MA"
```

- [ ] **Step 2: Run materializer tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_voice_materialization.py services/api/tests/test_async_voice_orchestration.py -q`
Expected: FAIL because `summary_confirmed=False` currently raises `DomainConflict`.

- [ ] **Step 3: Split consent, partial, and complete paths**

```python
data = event.collected_data
if data.get("recording_consent") is not True:
    return self._materialize_intake_failure(event, "consent_unavailable")

candidate = _intake_job_spec(event, session, require_summary=False)
candidate = _merge_intake_specs(session.base_job_spec, candidate)
if data.get("summary_confirmed") is True:
    return self._finalize_completed_intake(event, session, candidate)
return self._finalize_incomplete_intake(event, session, candidate)
```

The incomplete branch requires at least one collected move fact, derives missing fields, excludes
turns/analysis, and uses a replay-stable event key. The complete branch retains all existing
JobRecord invariants. Both branches derive `JobSpecV1.data_classification` from the session's
explicit `data_mode`: supervised role-play becomes `role_play`, and real-redacted becomes
`real_redacted`; the browser may not override the classification independently.

- [ ] **Step 4: Run materializer tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_voice_materialization.py services/api/tests/test_async_voice_orchestration.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/orchestration/voice_materializer.py services/api/app/integrations/elevenlabs/models.py services/api/tests/test_voice_materialization.py services/api/tests/test_async_voice_orchestration.py
git commit -m "feat: materialize interrupted intake drafts"
```

### Task 4: Add recovery, resume, and manual-finish services and routes

**Files:**
- Create: `services/api/app/orchestration/intake_recovery.py`
- Modify: `services/api/app/orchestration/intake_sessions.py`
- Modify: `services/api/app/integrations/elevenlabs/conversations.py`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/api/models.py`
- Test: `services/api/tests/test_intake_recovery.py`
- Test: `services/api/tests/test_api.py`

**Interfaces:**
- Consumes: repository operations from Task 2 and materializer from Task 3.
- Produces: public `IntakeSessionService.require_session(session_id)`,
  `IntakeRecoveryService.recover(session_id)`, `.resume(session_id)`, and
  `.finish_manually(session_id)`; dependency alias `IntakeRecovery`; and three POST routes.

- [ ] **Step 1: Add failing service/API tests**

```python
def test_recover_routes_done_snapshot_through_materializer(recovery, provider, session):
    provider.snapshot = done_snapshot(session, summary_confirmed=False)
    view = recovery.recover(session.intake_session_id)
    assert view.status is IntakeSessionStatus.INCOMPLETE


def test_resume_is_idempotent_and_inherits_mode(recovery, incomplete_session):
    first = recovery.resume(incomplete_session.intake_session_id)
    second = recovery.resume(incomplete_session.intake_session_id)
    assert first.intake_session_id == second.intake_session_id
    assert first.data_mode is IntakeDataMode.REAL_REDACTED
    assert first.base_job_spec == incomplete_session.partial_job_spec
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_intake_recovery.py services/api/tests/test_api.py -q`
Expected: FAIL because the service and routes do not exist.

- [ ] **Step 3: Implement the focused recovery service**

```python
class IntakeRecoveryService:
    def recover(self, session_id: UUID) -> IntakeSessionView:
        session = self._sessions.require_session(session_id)
        if session.status in TERMINAL_INTAKE_STATUSES:
            return self._sessions.get_session(session_id)
        if session.conversation_id is None:
            raise DomainConflict("Intake session has no provider conversation")
        snapshot = self._conversations.fetch_for_repair(session.conversation_id)
        self._validate_snapshot(snapshot, session)
        if snapshot.status != "done" or snapshot.completed_event is None:
            raise DomainConflict("Provider intake result is not repairable yet")
        self._materializer.materialize(snapshot.completed_event)
        return self._sessions.get_session(session_id)
```

`resume()` creates a new session with fresh reserved job ID, inherited mode/base snapshot, and
lineage. `finish_manually()` creates the normal unconfirmed JobRecord and atomically claims the
manual action. Expose the existing private lookup as a bounded public `require_session()` method;
do not let the recovery service reach into repository internals. In `api/dependencies.py`, add:

```python
IntakeRecovery = Annotated[IntakeRecoveryService, Depends(get_intake_recovery_service)]
```

- [ ] **Step 4: Wire strict routes**

```python
@router.post("/api/intake/sessions/{session_id}/recover", response_model=IntakeSessionResponse)
def recover_intake_session(session_id: UUID, recovery: IntakeRecovery) -> IntakeSessionResponse:
    return IntakeSessionResponse.model_validate(recovery.recover(session_id).model_dump())


@router.post("/api/intake/sessions/{session_id}/resume", response_model=IntakeSessionResponse)
def resume_intake_session(session_id: UUID, recovery: IntakeRecovery) -> IntakeSessionResponse:
    return IntakeSessionResponse.model_validate(recovery.resume(session_id).model_dump())


@router.post("/api/intake/sessions/{session_id}/finish-manually", response_model=JobRecord)
def finish_intake_manually(session_id: UUID, recovery: IntakeRecovery) -> JobRecord:
    return recovery.finish_manually(session_id)
```

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_intake_recovery.py services/api/tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/orchestration/intake_recovery.py services/api/app/orchestration/intake_sessions.py services/api/app/integrations/elevenlabs/conversations.py services/api/app/api services/api/tests/test_intake_recovery.py services/api/tests/test_api.py
git commit -m "feat: add voice intake recovery actions"
```

### Task 5: Replace delayed intake UI with terminal recovery choices

**Files:**
- Create: `apps/web/src/lib/voice/browserVoiceState.ts`
- Modify: `apps/web/src/lib/voice/useBrowserVoiceIntake.ts`
- Modify: `apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx`
- Modify: `apps/web/src/routes/intake.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Test: `apps/web/src/lib/api/voice.test.ts`

**Interfaces:**
- Consumes: Task 4 typed API routes and Task 1 intake mode/status.
- Produces: `BrowserVoicePhase` without `delayed`, bounded automatic repair, `continueSpeaking()`, `finishManually()`, and `startOver()`.

- [ ] **Step 1: Add failing pure-state and API tests**

```ts
it("maps an incomplete session to recovery choices", () => {
  expect(nextVoicePhase({ status: "incomplete", job_spec: partialSpec })).toBe("incomplete");
});

it("requests one repair after bounded polling", () => {
  expect(pollDecision(8, "in_progress")).toEqual({ kind: "recover" });
  expect(pollDecision(9, "in_progress")).toEqual({ kind: "unavailable" });
});
```

- [ ] **Step 2: Run frontend test and verify failure**

Run: `npm --prefix apps/web test -- --run src/lib/api/voice.test.ts`
Expected: FAIL because the pure state helpers and recovery endpoints are absent.

- [ ] **Step 3: Implement the bounded hook state machine**

```ts
export type BrowserVoicePhase =
  | "ready" | "requesting_microphone" | "connecting" | "connected"
  | "finalizing" | "incomplete" | "completed" | "unavailable" | "failed";

const POLL_ATTEMPTS_BEFORE_RECOVERY = 8;

async function finalizeResult(sessionId: string) {
  for (let attempt = 0; attempt < POLL_ATTEMPTS_BEFORE_RECOVERY; attempt += 1) {
    const session = await getIntakeSession(sessionId);
    if (isTerminal(session.status)) return applySession(session);
    await wait(POLL_INTERVAL_MS);
  }
  try {
    return applySession(await recoverIntakeSession(sessionId));
  } catch {
    setPhase("unavailable");
  }
}
```

Starting intake sends the selected `data_mode`. Resume replaces the active session ID with the child
session, issues a new token, and preserves the displayed structured preview. Manual finish navigates
to the returned job ID.

- [ ] **Step 4: Render the three incomplete actions and explicit data mode**

Add non-prechecked radio choices **Demo role-play** and **My real move (redacted)** before Start.
For `incomplete`, render known values, missing count, Continue speaking, Finish manually, and Start
over. For `unavailable`, render Retry result and Start over. Remove all `delayed` copy.

```tsx
{voice.phase === "incomplete" && (
  <div role="status" className="space-y-3">
    <p>Interview incomplete · {voice.missingFields.length} details still needed</p>
    <Button onClick={() => void voice.continueSpeaking()}>Continue speaking</Button>
    <Button variant="outline" onClick={() => void voice.finishManually()}>
      Finish manually
    </Button>
    <Button variant="ghost" onClick={voice.startOver}>Start over</Button>
  </div>
)}
```

- [ ] **Step 5: Run frontend tests and typecheck**

Run: `npm --prefix apps/web test -- --run src/lib/api/voice.test.ts && npm --prefix apps/web run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/voice apps/web/src/components/veramove/LiveVoiceIntakePanel.tsx apps/web/src/routes/intake.tsx apps/web/src/api/client.ts apps/web/src/lib/api/endpoints.ts apps/web/src/lib/api/voice.test.ts
git commit -m "feat: add resumable intake experience"
```

### Task 6: Contract and extract official-site contact candidates

**Files:**
- Create: `services/api/app/contracts/vendor_calls.py`
- Create: `services/api/app/orchestration/vendor_contacts.py`
- Modify: `services/api/app/contracts/vendor_research.py`
- Modify: `services/api/app/contracts/__init__.py`
- Modify: `services/api/app/orchestration/vendor_research.py`
- Test: `services/api/tests/test_vendor_contacts.py`
- Test: `services/api/tests/test_vendor_research_contracts.py`

**Interfaces:**
- Produces: `CallContext`, `VendorContactCandidateV1`, `VendorContactSelectionV1`,
  `extract_official_us_contacts(vendor, page)`, and dossier contact candidates.
- Consumes: existing selected vendor official URL provenance and Tavily extracted page text.

- [ ] **Step 1: Add failing contact extraction tests**

```python
def test_extracts_tel_and_visible_us_numbers_from_official_host(vendor, page):
    page = ExtractedWebPage(
        url=page.url,
        content='<a href="tel:+16175550101">Call</a> (617) 555-0102',
        truncated=False,
    )
    contacts = extract_official_us_contacts(vendor, page)
    assert [item.normalized_number for item in contacts] == ["+16175550101", "+16175550102"]
    assert all(str(item.source_url).startswith("https://official.example") for item in contacts)


def test_rejects_number_from_third_party_host(vendor, page):
    page = ExtractedWebPage(
        url="https://directory.example/vendor",
        content=page.content,
        truncated=page.truncated,
    )
    with pytest.raises(DomainConflict):
        extract_official_us_contacts(vendor, page)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_contacts.py services/api/tests/test_vendor_research_contracts.py -q`
Expected: FAIL because contact contracts/extractor do not exist.

- [ ] **Step 3: Add strict contact contracts**

```python
class VendorContactCandidateV1(ContractModel):
    contact_id: UUID
    vendor_id: UUID
    normalized_number: str = Field(pattern=r"^\+1[2-9]\d{9}$", exclude=True, repr=False)
    display_number: str = Field(min_length=12, max_length=24)
    source_url: HttpUrl
    source_excerpt: str = Field(min_length=1, max_length=160)
    source_excerpt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CallContext(StrEnum):
    SUPERVISED_ROLE_PLAY = "supervised_role_play"
    OFFICIAL_BUSINESS = "official_business"
```

The API model may return the public display number, but `model_dump()` used for events/attempts must
exclude `normalized_number`.

- [ ] **Step 4: Implement deterministic same-host parsing**

Normalize only US 10-digit or `+1` numbers, strip punctuation, reject extensions without a base,
deduplicate, cap at five contacts per vendor, and create stable IDs from vendor/number/source URL.
Do not use OpenAI or Tavily search snippets.

```python
def extract_official_us_contacts(
    vendor: Vendor,
    page: ExtractedWebPage,
) -> list[VendorContactCandidateV1]:
    official = official_website_url(vendor)
    if urlsplit(str(page.url)).hostname != urlsplit(str(official)).hostname:
        raise DomainConflict("Vendor contact source must use the official website host")
    matches = _TEL_LINK.findall(page.content) + _VISIBLE_US_PHONE.findall(page.content)
    normalized = list(dict.fromkeys(_normalize_us_phone(value) for value in matches))[:5]
    return [_contact_candidate(vendor, page, number) for number in normalized]
```

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_contacts.py services/api/tests/test_vendor_research_contracts.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/contracts/vendor_calls.py services/api/app/contracts/vendor_research.py services/api/app/contracts/__init__.py services/api/app/orchestration/vendor_contacts.py services/api/app/orchestration/vendor_research.py services/api/tests/test_vendor_contacts.py services/api/tests/test_vendor_research_contracts.py
git commit -m "feat: extract official vendor contacts"
```

### Task 7: Persist consented authorizations and suppression state

**Files:**
- Modify: `supabase/migrations/202607210007_resumable_intake_vendor_calls.sql`
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase.py`
- Modify: `services/api/app/core/config.py`
- Modify: `.env.example`
- Test: `services/api/tests/test_vendor_contacts.py`
- Test: `services/api/tests/test_live_integrations_config.py`
- Test: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- Consumes: Task 6 contact IDs.
- Produces: `VendorCallAuthorizationV1`, `VendorSuppressionV1`, authorization repository protocol, `real_vendor_calls_enabled`, and strong `contact_hash_secret`.

- [ ] **Step 1: Add failing authorization/config tests**

```python
def test_authorization_requires_ai_and_recording_opt_in(contact, locked_job):
    with pytest.raises(ValidationError):
        VendorCallAuthorizationV1(
            contact=contact,
            job_spec_sha256=job_spec_sha256(locked_job.job_spec),
            ai_call_consented=False,
            recording_consented=True,
        )


def test_real_vendor_calls_default_disabled(monkeypatch):
    monkeypatch.delenv("REAL_VENDOR_CALLS_ENABLED", raising=False)
    assert Settings.from_env().live_voice.real_vendor_calls_enabled is False
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_contacts.py services/api/tests/test_live_integrations_config.py services/api/tests/test_supabase_repository.py -q`
Expected: FAIL because authorization persistence/config do not exist.

- [ ] **Step 3: Add authorization and suppression tables**

```sql
create table if not exists public.vendor_call_authorizations (
    id uuid primary key,
    job_id uuid not null references public.jobs(id),
    job_spec_version text not null,
    job_spec_sha256 text not null check (job_spec_sha256 ~ '^[a-f0-9]{64}$'),
    vendor_id uuid not null,
    contact_id uuid not null,
    normalized_number text not null check (normalized_number ~ '^\+1[2-9][0-9]{9}$'),
    number_hash text not null check (number_hash ~ '^[a-f0-9]{64}$'),
    recipient_timezone text not null,
    consent_method text not null,
    consent_evidence_reference text not null,
    consented_at timestamptz not null,
    ai_call_consented boolean not null check (ai_call_consented),
    recording_consented boolean not null check (recording_consented),
    source_url text not null,
    created_at timestamptz not null,
    unique(job_id, job_spec_version, vendor_id),
    unique(job_id, job_spec_version, number_hash)
);

alter table public.vendor_call_authorizations enable row level security;
revoke all on public.vendor_call_authorizations from anon, authenticated;
grant select, insert, update, delete on public.vendor_call_authorizations to service_role;
```

Add `vendor_call_suppressions(number_hash, reason, created_at)` with the same RLS boundary.

- [ ] **Step 4: Implement HMAC hashing, timezone, consent-age, and suppression checks**

```python
def destination_hash(secret: str, number: str) -> str:
    return hmac.new(secret.encode(), number.encode(), hashlib.sha256).hexdigest()


def permitted_call_time(now: datetime, timezone_name: str) -> bool:
    local = now.astimezone(ZoneInfo(timezone_name))
    return time(8, 0) <= local.time() < time(21, 0)
```

Validate IANA zones through `ZoneInfo`, cap consent age to the configured policy, and never include
the normalized number in public error text. Constrain `consent_method` to a reviewed enum and
`consent_evidence_reference` to a bounded opaque identifier; reject free-form notes, phone-shaped
values, and customer PII.

- [ ] **Step 5: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_contacts.py services/api/tests/test_live_integrations_config.py services/api/tests/test_supabase_repository.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/202607210007_resumable_intake_vendor_calls.sql services/api/app/repositories services/api/app/core/config.py .env.example services/api/tests/test_vendor_contacts.py services/api/tests/test_live_integrations_config.py services/api/tests/test_supabase_repository.py
git commit -m "feat: authorize consented vendor destinations"
```

### Task 8: Build bounded research-aware vendor call plans

**Files:**
- Create: `services/api/app/orchestration/vendor_call_plans.py`
- Modify: `services/api/app/contracts/vendor_calls.py`
- Modify: `services/api/app/orchestration/vendor_research_questions.py`
- Test: `services/api/tests/test_vendor_call_plans.py`
- Test: `services/api/tests/test_vendor_research_questions.py`

**Interfaces:**
- Produces: `VendorCallPlanV1` and `build_vendor_call_plan(job_spec, dossier)`.
- Consumes: existing claims/questions and required fee categories.

- [ ] **Step 1: Add failing agenda tests**

```python
def test_plan_confirms_published_price_once_and_asks_missing_fees(job_spec, dossier):
    plan = build_vendor_call_plan(job_spec, dossier)
    assert sum("website lists" in item.question.lower() for item in plan.questions) == 1
    assert FeeCategory.TRAVEL in {item.category for item in plan.questions}
    assert len(plan.questions) <= 20


def test_plan_contains_no_phone_or_raw_page(job_spec, dossier):
    payload = build_vendor_call_plan(job_spec, dossier).model_dump_json()
    assert "+1" not in payload
    assert "raw_content" not in payload
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_call_plans.py services/api/tests/test_vendor_research_questions.py -q`
Expected: FAIL because `VendorCallPlanV1` and the capped builder do not exist.

- [ ] **Step 3: Implement the deterministic priority order**

```python
def build_vendor_call_plan(job_spec: JobSpecV1, dossier: VendorResearchDossierV1) -> VendorCallPlanV1:
    fee_questions = first_question_per_required_fee(dossier.verification_questions)
    ambiguity = first_distinct_questions(dossier.verification_questions, reason="ambiguous_claim", limit=3)
    services = relevant_service_claim_confirmations(job_spec, dossier.claims, limit=2)
    questions = tuple((fee_questions + ambiguity + services)[:20])
    return VendorCallPlanV1(
        plan_version="1.0",
        vendor_id=dossier.vendor.vendor_id,
        job_spec_version=job_spec.version,
        job_spec_sha256=job_spec_sha256(job_spec),
        website_claims=bounded_relevant_claims(dossier.claims, limit=5),
        source_urls=official_source_urls(dossier.claims, limit=5),
        questions=questions,
        require_all_in_total=True,
        require_deposit=True,
        require_availability=True,
        require_binding_status=True,
        require_readback=True,
    )
```

Each required applicable fee receives one question. A website claim replaces, rather than adds to,
the direct question for that category. Preserve unknown values. `website_claims` and source URLs
are audit/confirmation context only: they must never materialize as a quote, fee, competing offer,
or negotiation evidence unless the recipient verifies them during the call.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_vendor_call_plans.py services/api/tests/test_vendor_research_questions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/contracts/vendor_calls.py services/api/app/orchestration/vendor_call_plans.py services/api/app/orchestration/vendor_research_questions.py services/api/tests/test_vendor_call_plans.py services/api/tests/test_vendor_research_questions.py
git commit -m "feat: build targeted vendor call plans"
```

### Task 9: Dispatch exactly three authorized real-vendor quote calls

**Files:**
- Modify: `services/api/app/orchestration/providers.py`
- Modify: `services/api/app/orchestration/models.py`
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/integrations/elevenlabs/live.py`
- Modify: `services/api/app/integrations/elevenlabs/mock.py`
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/orchestration/outbound_materializer.py`
- Test: `services/api/tests/test_live_voice.py`
- Test: `services/api/tests/test_async_voice_orchestration.py`

**Interfaces:**
- Consumes: Task 7 authorizations and Task 8 plans.
- Produces: `VoiceCallDestination`, new `VoiceProvider.initiate_quote_call(..., destination, plan)`, and authorization references on attempts.

- [ ] **Step 1: Add failing orchestration and payload tests**

```python
def test_real_dispatch_persists_three_attempts_before_network(service, provider, authorized_job):
    provider.fail_on_index = 1
    service.initiate_quote_batch(authorized_job.job_spec.job_id)
    attempts = service.list_call_attempts(authorized_job.job_spec.job_id)
    assert len(attempts) == 3
    assert len({item.vendor_call_authorization_id for item in attempts}) == 3


def test_quote_payload_uses_authorized_number_and_vendor_plan(live_provider, authorization, plan):
    live_provider.initiate_quote_call(JOB_SPEC, VENDOR, CALL_ID, authorization.destination(), plan)
    payload = live_provider.transport.requests[0]["payload"]
    assert payload["to_number"] == authorization.normalized_number
    variables = payload["conversation_initiation_client_data"]["dynamic_variables"]
    assert json.loads(variables["vendor_call_plan_json"])["vendor_id"] == str(VENDOR.vendor_id)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_voice.py services/api/tests/test_async_voice_orchestration.py -q`
Expected: FAIL because quote calls still resolve fixed destination slots and have no plans.

- [ ] **Step 3: Change the provider-neutral quote signature**

```python
class VoiceCallDestination(BaseModel):
    authorization_id: UUID | None = None
    normalized_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$", exclude=True, repr=False)
    call_context: CallContext
    recording_enabled: bool


def initiate_quote_call(
    self,
    job_spec: JobSpecV1,
    vendor: Vendor,
    call_id: UUID,
    destination: VoiceCallDestination,
    plan: VendorCallPlanV1,
) -> VoiceCallResult: ...
```

Keep negotiation on the already authorized target attempt/destination; do not re-resolve a browser
number.

- [ ] **Step 4: Gate and persist all attempts before provider calls**

Official-business dispatch must verify the feature flag, `real_redacted`, current locked hash,
exactly three distinct authorizations, consent, suppression, local time, and plan match. Create all
three attempts first, then invoke sequentially. Role-play creates synthetic destination objects from
the three configured test slots.

```python
if call_context is CallContext.OFFICIAL_BUSINESS:
    self._settings.require_real_vendor_calls_config()
    if record.job_spec.data_classification is not DataClassification.REAL_REDACTED:
        raise DomainConflict("Official-business calls require a real_redacted JobSpec")
    resolved = self._authorizations.require_ready_batch(record.job_spec, now=self._clock())
else:
    resolved = self._role_play_destinations(record.job_spec)
attempts = [self._new_authorized_attempt(record, item) for item in resolved]
for attempt, item in zip(attempts, resolved, strict=True):
    self._dispatch_quote_attempt(attempt, item.destination, item.call_plan)
```

- [ ] **Step 5: Pass bounded dynamic variables and the correct recording flag**

```python
dynamic_variables.update({
    "call_context": destination.call_context,
    "vendor_call_plan_json": plan.model_dump_json(exclude_none=True),
    "website_claims_json": json.dumps(plan.website_claims, separators=(",", ":")),
    "verification_questions_json": json.dumps(
        [item.model_dump(mode="json") for item in plan.questions], separators=(",", ":")
    ),
})
payload["call_recording_enabled"] = destination.recording_enabled
```

When a verified terminal event contains `recipient_opt_out=true`, call the suppression repository
with the authorization's number hash before returning the terminal call. Persist only the hash and
supported reason.

- [ ] **Step 6: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_live_voice.py services/api/tests/test_async_voice_orchestration.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/orchestration/providers.py services/api/app/orchestration/models.py services/api/app/orchestration/service.py services/api/app/orchestration/outbound_materializer.py services/api/app/integrations/elevenlabs/live.py services/api/app/integrations/elevenlabs/mock.py services/api/app/repositories/base.py services/api/tests/test_live_voice.py services/api/tests/test_async_voice_orchestration.py
git commit -m "feat: dispatch authorized vendor call plans"
```

### Task 10: Update both ElevenLabs agent source packages and preflight

**Files:**
- Modify: `agents/intake/prompt.md`
- Modify: `agents/intake/agent.yaml`
- Modify: `agents/intake/README.md`
- Modify: `agents/negotiator/prompt.md`
- Modify: `agents/negotiator/agent.yaml`
- Modify: `agents/negotiator/data-collection.json`
- Modify: `agents/negotiator/README.md`
- Modify: `agents/elevenlabs-dashboard-checklist.md`
- Modify: `scripts/live_voice_preflight.py`
- Test: `services/api/tests/test_scripts.py`
- Test: `services/api/tests/test_documentation.py`

**Interfaces:**
- Consumes: Task 5 intake variables and Task 9 quote variables.
- Produces: reviewed prompt/config version `2026-07-21.2` and exact preflight schema checks.

- [ ] **Step 1: Add failing preflight/documentation tests**

```python
def test_preflight_requires_resume_and_call_plan_variables():
    result = inspect_agent_sources()
    assert {
        "intake_data_mode", "resume_mode", "partial_job_spec_json", "missing_fields_json"
    } <= result.intake_dynamic_variables
    assert {
        "call_context", "vendor_call_plan_json", "website_claims_json",
        "verification_questions_json"
    } <= result.outbound_dynamic_variables
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_scripts.py services/api/tests/test_documentation.py -q`
Expected: FAIL because source packages omit the variables and branches.

- [ ] **Step 3: Update the Intake prompt**

The prompt must treat `partial_job_spec_json` as read-only system context, confirm known values once,
ask only `missing_fields_json`, never replay a transcript, and perform a complete final readback.
`real_redacted` must forbid names, street addresses, unit numbers, email, and customer phone data.

```markdown
If `resume_mode=structured_partial`, briefly confirm the known facts in
`partial_job_spec_json`, then ask only the unresolved facts listed in `missing_fields_json`.
Never ask for, speak, or store a name, street address, unit number, email address, or customer phone
number when `intake_data_mode=real_redacted`.
```

- [ ] **Step 4: Update the Outbound prompt**

Official-business mode identifies VeraMove's AI assistant, asks consent before move facts, follows
`vendor_call_plan_json`, records a verbal stop/opt-out, and never calls a role-play participant a
real company. Role-play mode preserves the current synthetic disclosure. Static fee probes are used
only when the plan is empty.

```markdown
When `call_context=official_business`, identify yourself as VeraMove's AI assistant and ask whether
the recipient consents to the AI call and recording before discussing move facts. On refusal or any
reasonable stop request, set `recipient_opt_out=true`, acknowledge it, and end immediately.
Ask each item in `vendor_call_plan_json.questions` once. Do not repeat a published-claim question as
a generic fee probe.
```

- [ ] **Step 5: Tighten preflight**

Require exact agent IDs, config version, dynamic variables, post-call transcription webhook, data
collection fields, and no attached provider tools. Official-business readiness is false on any
mismatch.

```python
REQUIRED_INTAKE_VARIABLES = frozenset({
    "job_id", "intake_session_id", "agent_config_version", "intake_data_mode",
    "resume_mode", "partial_job_spec_json", "missing_fields_json",
})
REQUIRED_OUTBOUND_VARIABLES = frozenset({
    "job_id", "call_id", "vendor_id", "vendor_name", "job_spec_json",
    "call_context", "vendor_call_plan_json", "website_claims_json",
    "verification_questions_json",
})
```

- [ ] **Step 6: Run focused tests**

Run: `.venv/bin/python -m pytest services/api/tests/test_scripts.py services/api/tests/test_documentation.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add agents scripts/live_voice_preflight.py services/api/tests/test_scripts.py services/api/tests/test_documentation.py
git commit -m "feat: configure resumable and research-aware agents"
```

### Task 11: Expose contact authorization APIs and review UI

**Files:**
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/orchestration/vendor_research.py`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Modify: `apps/web/src/lib/api/hooks.ts`
- Create: `apps/web/src/components/veramove/VendorContactReview.tsx`
- Modify: `apps/web/src/components/veramove/VendorResearchPanel.tsx`
- Modify: `apps/web/src/routes/calls.$jobId.tsx`
- Test: `services/api/tests/test_api.py`
- Test: `apps/web/src/api/client.test.ts`
- Test: `apps/web/src/lib/api/workflow.smoke.test.ts`

**Interfaces:**
- Consumes: Tasks 6-9 service operations.
- Produces: contact discovery/authorization endpoints, `authorization_ready`, and frontend review flow.

- [ ] **Step 1: Add failing backend and client tests**

```python
def test_contact_authorization_requires_exactly_three(client, researched_job):
    response = client.put(
        f"/api/jobs/{researched_job}/vendor-research/call-authorizations",
        json={"selections": [authorized_selection(0), authorized_selection(1)]},
    )
    assert response.status_code == 422


def test_start_calls_rejects_unready_official_contacts(client, researched_job):
    response = client.post(f"/api/jobs/{researched_job}/calls")
    assert response.status_code == 409
```

```ts
it("sends only server-issued contact ids and consent metadata", async () => {
  await apiClient.saveVendorCallAuthorizations(jobId, request);
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/vendor-research/call-authorizations"),
    expect.objectContaining({ method: "PUT" }),
  );
});
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `.venv/bin/python -m pytest services/api/tests/test_api.py -q && npm --prefix apps/web test -- --run src/api/client.test.ts src/lib/api/workflow.smoke.test.ts`
Expected: FAIL because the APIs and client methods are absent.

- [ ] **Step 3: Add typed routes**

```python
@router.post("/api/jobs/{job_id}/vendor-research/contacts", response_model=JobVendorResearchV1)
def extract_vendor_contacts(job_id: UUID, research: VendorResearch) -> JobVendorResearchV1:
    return research.extract_contacts(job_id)


@router.put("/api/jobs/{job_id}/vendor-research/call-authorizations", response_model=JobVendorResearchV1)
def authorize_vendor_calls(
    job_id: UUID, request: VendorCallAuthorizationRequest, research: VendorResearch
) -> JobVendorResearchV1:
    return research.authorize_calls(job_id, request)
```

Add DELETE to clear unreferenced authorizations. Normalize all failures through existing API errors.

- [ ] **Step 4: Add centralized client methods and hooks**

Add `extractVendorContacts`, `saveVendorCallAuthorizations`, and
`clearVendorCallAuthorizations`; mutation success updates `qk.vendorResearch(jobId)`.

- [ ] **Step 5: Build the contact review component**

Render one card per selected vendor with official source, same-site contact radio options,
recipient timezone, non-prechecked AI-call and recording opt-in confirmations, consent method/time,
and concise call-plan preview. Submit exactly three contact IDs. Never render a free-form destination
field. Disable Start calls until `authorization_ready` is true and require the final exactly-three
acknowledgement.

```tsx
<Checkbox
  checked={selection.aiCallConsented}
  onCheckedChange={(checked) => updateSelection({ aiCallConsented: checked === true })}
  aria-label={`Recipient at ${vendor.name} affirmatively opted in to an AI call`}
/>
<Checkbox
  checked={selection.recordingConsented}
  onCheckedChange={(checked) => updateSelection({ recordingConsented: checked === true })}
  aria-label={`Recipient at ${vendor.name} affirmatively opted in to recording`}
/>
<Button disabled={!research.authorization_ready || !batchAcknowledged} onClick={startCalls}>
  Start three authorized calls
</Button>
```

- [ ] **Step 6: Run focused tests and typecheck**

Run: `.venv/bin/python -m pytest services/api/tests/test_api.py -q && npm --prefix apps/web test -- --run src/api/client.test.ts src/lib/api/workflow.smoke.test.ts && npm --prefix apps/web run typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/api services/api/app/orchestration/vendor_research.py apps/web/src/api/client.ts apps/web/src/lib/api apps/web/src/components/veramove/VendorContactReview.tsx apps/web/src/components/veramove/VendorResearchPanel.tsx 'apps/web/src/routes/calls.$jobId.tsx' services/api/tests/test_api.py apps/web/src/api/client.test.ts apps/web/src/lib/api/workflow.smoke.test.ts
git commit -m "feat: review and authorize vendor calls"
```

### Task 12: Regenerate contracts and run the full integration suite

**Files:**
- Modify: `packages/contracts/openapi.json`
- Modify: `apps/web/src/api/schema.d.ts`
- Modify: `.env.example`
- Modify: `docs/backend-voice-runbook.md`
- Modify: `README.md` only if setup commands or environment variables are incomplete.
- Test: all repository checks.

**Interfaces:**
- Consumes: all earlier public API changes.
- Produces: fresh canonical OpenAPI/types and operational documentation.

- [ ] **Step 1: Export OpenAPI and regenerate TypeScript**

Run:

```bash
.venv/bin/python scripts/export_openapi.py
npm --prefix apps/web run generate:api
```

Expected: `packages/contracts/openapi.json` and `apps/web/src/api/schema.d.ts` include incomplete
intake, recovery routes, contact candidates, authorizations, and call plans.

- [ ] **Step 2: Run the full check suite**

Run: `.venv/bin/python scripts/check.py`
Expected: Ruff PASS, pytest PASS, OpenAPI freshness PASS, TypeScript PASS, Vitest PASS, Vite/Nitro
production build PASS.

- [ ] **Step 3: Exercise the credential-free mock workflow**

Run the repository's mock smoke command or API test for create -> edit -> confirm -> exactly three
calls -> negotiate -> report.
Expected: all four supported call outcomes remain valid and the recommendation still cites
transcript evidence and recording URLs.

- [ ] **Step 4: Scan generated and persisted shapes for prohibited data**

Run:

```bash
rg -n 'transcript|raw_content|normalized_number|to_number|phone_number' packages/contracts/openapi.json data agents services/api/tests/fixtures
```

Expected: only reviewed contract descriptions/provider adapter references; no real number, raw
transcript, populated secret, or forbidden fixture.

- [ ] **Step 5: Update runbook and environment documentation**

Document `REAL_VENDOR_CALLS_ENABLED`, `CONTACT_HASH_SECRET`, agent config `2026-07-21.2`, migration
order, check-only preflight, role-play fallback, consent/suppression/calling-window gate, and the rule
that no production business is called during verification.

- [ ] **Step 6: Commit**

```bash
git add packages/contracts/openapi.json apps/web/src/api/schema.d.ts .env.example docs/backend-voice-runbook.md README.md
git commit -m "docs: publish resumable real-call contract"
```

### Task 13: Apply, deploy, synchronize agents, and verify production safely

**Files:**
- No new source files unless production verification reveals a defect; any defect gets its own test
  and focused fix commit.

**Interfaces:**
- Consumes: green Task 12 artifacts.
- Produces: migrated Supabase, deployed Render API, published Lovable frontend, synchronized
  ElevenLabs agents, and evidence of safe production behavior.

- [ ] **Step 1: Apply the additive migration before backend deploy**

Apply `supabase/migrations/202607210007_resumable_intake_vendor_calls.sql` through the authenticated
Supabase SQL editor or migration runner.
Expected: new intake columns/RPCs and authorization/suppression tables exist with RLS enabled.

- [ ] **Step 2: Deploy the backend with real-business dispatch disabled**

Push the reviewed branch to the Render-connected deployment branch. Keep
`REAL_VENDOR_CALLS_ENABLED=false`; add a strong `CONTACT_HASH_SECRET` without printing it.
Expected: `/health` and `/api/integrations/status` report live/configured without exposing values.

- [ ] **Step 3: Synchronize both ElevenLabs agents**

Update the Intake and Outbound agent prompts, dynamic variables, data collection, and config version
through the authenticated dashboard/API. Run:

```bash
.venv/bin/python scripts/live_voice_preflight.py --check-only
```

Expected: both agents, webhook, dynamic variables, and retention/recording settings pass; no call is
placed.

- [ ] **Step 4: Publish the Lovable frontend**

Sync the reviewed `apps/web` changes to the GitHub-connected Lovable repo and deploy project
`6d8ed1ea-bbda-4540-bb3f-8e866e3b7a77`.
Expected: public `deal-mover-ai.lovable.app` serves the new bundle.

- [ ] **Step 5: Verify interrupted intake end-to-end**

Using fictional role-play facts, start browser intake, provide a few answers, end before readback,
and verify:

- terminal **Interview incomplete** appears;
- no `Processing is delayed` appears;
- Continue speaking starts a new session with known facts retained;
- Finish manually opens the confirmation editor with missing fields;
- Start over creates a fresh unrelated session.

- [ ] **Step 6: Verify official contacts and call-plan readiness without real dispatch**

On a `real_redacted` locked synthetic test job, research three movers, extract official contacts,
inspect source links, and confirm the backend refuses authorization without recipient opt-in. Use
only approved test destinations for the final provider payload check.
Expected: exactly three call plans are correct; no public business is dialed.

- [ ] **Step 7: Enable real-business dispatch only after explicit final approval**

Ask the user before changing `REAL_VENDOR_CALLS_ENABLED` to true. If approved, enable it without
placing a call and re-run check-only preflight.
Expected: readiness is true; actual dispatch still requires three current consent records and an
explicit Start action.

- [ ] **Step 8: Final completion audit**

For every acceptance criterion in
`docs/superpowers/specs/2026-07-21-resumable-intake-real-vendor-calls-design.md`, record the exact
test, API response, browser state, migration state, or provider preflight proving it. If any evidence
is missing or indirect, keep the goal active and fix or verify the gap.

- [ ] **Step 9: Push the branch**

```bash
git push -u origin codex/resumable-intake-real-calls
```

Expected: remote branch contains the committed design, plan, implementation, generated contracts,
tests, and documentation.
