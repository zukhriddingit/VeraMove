# Outbound Result Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all three delivered ElevenLabs outbound results and render them in the live Calls screen without placing replacement calls.

**Architecture:** Normalize untrusted provider data only inside `outbound_materializer.py`, before the unchanged canonical Pydantic contracts and evidence verifier run. Deploy the tested backend, then replay the three stored provider conversations through VeraMove's existing authenticated and idempotent repair boundary.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, ElevenLabs post-call webhooks, Supabase repositories, Render deployment.

## Global Constraints

- Exactly three initial vendor calls must use the same confirmed `JobSpecV1`.
- Canonical outcomes remain `itemized_quote`, `callback_commitment`, `documented_decline`, or `failed`.
- Never invent prices, fees, evidence, recordings, consent, or vendor outcomes.
- Preserve correlation, recording-consent, transcript-evidence, and idempotency validation.
- `APP_MODE=mock` must continue working without credentials or Supabase.
- Do not expose or commit provider secrets or real PII.

---

### Task 1: Lock the Provider-Variation Behavior with Regression Tests

**Files:**
- Modify: `services/api/tests/test_voice_materialization.py`

**Interfaces:**
- Consumes: `materialize_outbound_event(...) -> MaterializedOutboundOutcome`
- Produces: regression coverage for provider defaults, safe fee normalization, and strict conflicts

- [ ] **Step 1: Add a non-quote provider-default regression test**

```python
def test_non_quote_ignores_provider_quote_defaults(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(attempt).model_copy(
        update={
            "has_audio": False,
            "collected_data": {
                "recording_consent": False,
                "outcome_type": "failed",
                "outcome_reason": "The synthetic participant did not answer.",
                "availability": "Unknown",
                "availability_status": "unknown",
                "addressed_fee_categories_json": "[]",
            },
            "transcript_turns": (),
        },
        deep=True,
    )

    result = materialize(event, attempt)

    assert result.outcome.type is CallOutcomeType.FAILED
    assert result.outcome.reason == "The synthetic participant did not answer."
```

- [ ] **Step 2: Add safe fee-normalization tests**

```python
def test_quote_normalizes_unknown_fee_amount_and_category(job_spec, fixtures):
    attempt = make_attempt(job_spec, fixtures.load_live_role_play_vendors()[0])
    event = make_event(
        attempt,
        collected_data={
            "fee_items_json": json.dumps([
                {
                    "category": "service_fee",
                    "description": "Synthetic service fee; amount not stated.",
                    "amount": None,
                    "mandatory": True,
                }
            ]),
            "addressed_fee_categories_json": json.dumps(["service_fee"]),
        },
    )

    result = materialize(event, attempt)

    fee = result.outcome.quote.fee_line_items[0]
    assert fee.category is FeeCategory.OTHER
    assert fee.amount is None
    assert fee.amount_status.value == "unknown"
```

- [ ] **Step 3: Run the new tests and verify they fail for the current strict materializer**

Run: `.venv/bin/pytest services/api/tests/test_voice_materialization.py -q`

Expected: the provider-default and fee-normalization regressions fail, while existing tests remain unchanged.

### Task 2: Normalize Only the ElevenLabs Boundary

**Files:**
- Modify: `services/api/app/orchestration/outbound_materializer.py`
- Test: `services/api/tests/test_voice_materialization.py`

**Interfaces:**
- Consumes: provider `collected_data: dict[str, Any]`
- Produces: `_normalize_fee_item(value: Any) -> dict[str, Any]` and outcome-specific conflict validation

- [ ] **Step 1: Narrow mixed-outcome validation**

Keep itemized quotes strict about `callback_at` and `outcome_reason`. Ignore quote-field defaults for
non-quote outcomes, but reject `outcome_reason` on callbacks and `callback_at` on failed/declined
outcomes.

```python
conflicting_fields = {
    CallOutcomeType.ITEMIZED_QUOTE: {"callback_at", "outcome_reason"},
    CallOutcomeType.CALLBACK_COMMITMENT: {"outcome_reason"},
    CallOutcomeType.DOCUMENTED_DECLINE: {"callback_at"},
    CallOutcomeType.FAILED: {"callback_at"},
}[outcome_type]
```

- [ ] **Step 2: Normalize bounded fee objects before Pydantic validation**

```python
def _normalize_fee_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainConflict("fee_items_json contains an invalid fee")
    normalized = dict(value)
    try:
        normalized["category"] = FeeCategory(normalized.get("category")).value
    except (TypeError, ValueError):
        normalized["category"] = FeeCategory.OTHER.value
    if normalized.get("amount") is None and normalized.get("unit_rate") is None:
        normalized["amount_status"] = AmountStatus.UNKNOWN.value
    return normalized
```

The existing `FeeLineItem` model remains the final validator, so negative, non-finite, over-precision,
missing-description, and inconsistent amount/status inputs still fail closed.

- [ ] **Step 3: Normalize addressed fee categories consistently**

Map unrecognized bounded category strings to `FeeCategory.OTHER`, deduplicate them, and continue to
reject non-string or oversized inputs.

- [ ] **Step 4: Run focused materialization tests**

Run: `.venv/bin/pytest services/api/tests/test_voice_materialization.py -q`

Expected: all materialization tests pass, including existing mixed-outcome, consent, correlation,
and evidence assertions.

- [ ] **Step 5: Run the full repository gate**

Run: `PYTHONPATH=. .venv/bin/python scripts/check.py`

Expected: Ruff, pytest, OpenAPI export, API type generation, TypeScript checking, Vitest, and the Vite
production build all pass.

- [ ] **Step 6: Commit the tested implementation**

```bash
git add services/api/app/orchestration/outbound_materializer.py \
  services/api/tests/test_voice_materialization.py \
  docs/superpowers/plans/2026-07-20-outbound-result-recovery.md
git commit -m "fix: recover provider call outcomes"
```

### Task 3: Deploy, Repair, and Verify the Existing Job

**Files:**
- No source changes expected

**Interfaces:**
- Consumes: stored `CallAttempt` records and existing `POST /api/calls/{call_id}/repair`
- Produces: exactly three canonical call records for job `3ce80a6d-ea55-4b1d-a11e-943a90bf8516`

- [ ] **Step 1: Push the tested commit to the collaboration and Render deployment branches**

Run: `git push origin main`

Run: `git push origin main:deploy/veramove-demo`

Expected: both remote branches advance to the tested implementation commit.

- [ ] **Step 2: Wait for the new Render deployment to report healthy**

Verify the deployed revision matches the implementation commit and `GET /api/health` returns a
successful live-mode response.

- [ ] **Step 3: Replay the three stored attempts through the operator repair endpoint**

Use server-side environment credentials without printing them. For each attempt belonging to the
job, invoke `POST /api/calls/{call_id}/repair` once. Do not initiate a new call.

Expected: idempotent repair returns the canonical call outcome or its already-materialized result.

- [ ] **Step 4: Verify the canonical API state**

Run a read-only `GET /api/jobs/3ce80a6d-ea55-4b1d-a11e-943a90bf8516`.

Expected: `calls` contains exactly three distinct call records, including the answered outcome and
the missed/no-answer outcome(s); the job no longer has an empty Calls step.

- [ ] **Step 5: Verify the published Calls screen**

Open the live job in the published frontend and confirm that all three cards render with truthful
status, evidence links only where consent permits, and no replacement calls were placed.
