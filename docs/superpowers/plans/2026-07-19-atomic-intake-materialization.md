# Atomic Intake Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist successful voice intake and intake initiation failures with the same leased, exactly-once transaction boundary used for outbound voice results.

**Architecture:** Add discriminated Pydantic materialization models and one `finalize_voice_intake_webhook` repository method. The in-memory repository applies each intake mutation under its existing `RLock`; the Supabase adapter calls one allowlisted `veramove_finalize_voice_intake_webhook` function that validates the lease and atomically persists the session, optional job/event, and processed receipt.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI service layer, PostgreSQL/PLpgSQL, Supabase PostgREST RPC, pytest.

## Global Constraints

- `APP_MODE=mock` must run without credentials or Supabase.
- Never persist provider envelopes, transcripts, analysis, phone numbers, audio, secrets, or populated credentials.
- Completion creates one unconfirmed `JobSpecV1` and one audit event; initiation failure creates no job because the event-log job foreign key requires a canonical job.
- A byte-equivalent pre-existing job may be accepted for recovery; a divergent job is rejected.
- Preserve the legacy `reserve_webhook` method for compatibility, but do not use it for new intake materialization.
- Do not stage or commit this implementation.

---

### Task 1: Define the typed intake transaction boundary

**Files:**
- Modify: `services/api/app/repositories/base.py`
- Test: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**
- Consumes: `IntakeSession`, `JobRecord`, `JobEvent`, `VoiceWebhookFinalizeResult`.
- Produces: `VoiceIntakeCompletion`, `VoiceIntakeFailure`, `VoiceIntakeMaterialization`, and `VoiceMaterializationRepository.finalize_voice_intake_webhook(idempotency_key, lease_token, materialization, now)`.

- [ ] **Step 1: Write model tests that reject session/job/event identity mismatches and unsafe nested values.**
- [ ] **Step 2: Run the focused model tests and verify they fail because the types are absent.**
- [ ] **Step 3: Implement frozen, extra-forbid discriminated models with timezone, lifecycle, identity, and recursive no-PII validation.**
- [ ] **Step 4: Run the focused model tests and verify they pass.**

### Task 2: Implement atomic mock behavior

**Files:**
- Modify: `services/api/app/repositories/memory.py`
- Test: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**
- Consumes: `VoiceIntakeMaterialization` from Task 1 and an active `VoiceWebhookLease`.
- Produces: an all-or-nothing session/job/event/receipt transition under `RLock`.

- [ ] **Step 1: Write tests for completion, failure, duplicate acknowledgment, wrong/expired tokens, and rollback on a divergent job.**
- [ ] **Step 2: Run those tests and verify the method is absent.**
- [ ] **Step 3: Pre-validate all candidate state, build deep-copied replacement payloads, then assign all stores and process the receipt while holding one lock.**
- [ ] **Step 4: Run the focused tests and verify no partial mutation remains after any rejected finalization.**

### Task 3: Add the Supabase intake RPC and adapter

**Files:**
- Modify: `services/api/app/repositories/supabase_client.py`
- Modify: `services/api/app/repositories/supabase.py`
- Create: `supabase/migrations/202607190004_atomic_voice_intake.sql`
- Test: `services/api/tests/test_supabase_client.py`
- Test: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- Consumes: the Task 1 typed union.
- Produces: allowlisted RPC `veramove_finalize_voice_intake_webhook(p_idempotency_key, p_lease_token, p_kind, p_session, p_job, p_event, p_now)` returning `{processed: true, duplicate: bool}`.

- [ ] **Step 1: Write adapter tests for the exact RPC shape and recursive forbidden-key/phone rejection.**
- [ ] **Step 2: Run them and verify the RPC is not allowlisted and the adapter method is absent.**
- [ ] **Step 3: Add the allowlist entry and adapter serialization from validated models only.**
- [ ] **Step 4: Add one security-definer function that locks the receipt/session, rejects expired or mismatched leases and identities, applies completion or failure, then marks the receipt processed in the same transaction.**
- [ ] **Step 5: Revoke public/anon/authenticated execution, grant only `service_role`, and run focused adapter tests.**

### Task 4: Route intake webhook paths through the transaction

**Files:**
- Modify: `services/api/app/orchestration/voice_materializer.py`
- Test: `services/api/tests/test_async_voice_orchestration.py`
- Test: `services/api/tests/test_webhooks.py`

**Interfaces:**
- Consumes: `VoiceMaterializationRepository.finalize_voice_intake_webhook`.
- Produces: leased exactly-once completion and initiation-failure handling without `reserve_webhook`.

- [ ] **Step 1: Extend service tests to assert completed/failed receipts are duplicate-safe and that transient finalizer failures remain retryable without partial aggregate writes.**
- [ ] **Step 2: Run the tests and verify the current separate writes fail the new expectations.**
- [ ] **Step 3: Build typed completion/failure values in `VoiceMaterializer`, claim first, finalize once, and mark validation failures nonretryable or persistence failures retryable.**
- [ ] **Step 4: Run repository, Supabase, orchestration, and webhook tests.**
- [ ] **Step 5: Run Ruff and `git diff --check` on every changed file.**
