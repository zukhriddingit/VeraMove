# Live Intake Reliability and Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every new live ElevenLabs intake materialize automatically and let users persistently edit the unconfirmed canonical JobSpec before locking it.

**Architecture:** Normalize only bounded, known ElevenLabs variations at the provider-to-domain boundary while keeping `JobSpecV1` strict. Add a typed full-replacement operation for unconfirmed JobSpecs, then let the frontend merge its review draft into the current canonical record before confirmation. Keep FastAPI OpenAPI as the generated frontend contract and retain credential-free mock behavior.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, React, TypeScript, TanStack Query/Router, Vitest, Vite, ElevenLabs Agents.

## Global Constraints

- FastAPI-generated OpenAPI remains the canonical API contract.
- `APP_MODE=mock` must run without credentials or Supabase.
- Do not persist or log provider envelopes, transcripts, phone numbers, credentials, or real PII.
- Confirmation must lock the exact saved `JobSpecV1` version before any vendor call.
- Frontend code uses generated API types and one centralized client.
- Preserve strict rejection of unknown, ambiguous, or conflicting provider values.

---

### Task 1: Normalize bounded ElevenLabs intake variations

**Files:**
- Modify: `services/api/app/integrations/elevenlabs/analysis.py`
- Modify: `services/api/app/orchestration/voice_materializer.py`
- Test: `services/api/tests/test_elevenlabs_payloads.py`
- Test: `services/api/tests/test_async_voice_orchestration.py`

**Interfaces:**
- Consumes: ElevenLabs `analysis.data_collection_results` and `data_collection_results_list`.
- Produces: `normalize_collected_data(data) -> dict[str, PrimitiveValue]` with at most 40 unique identifiers and `_intake_job_spec(...) -> JobSpecV1` accepting only documented legacy variations.

- [ ] **Step 1: Add failing duplicate-representation tests**

Create a provider payload containing the same 24 identifiers in map and list forms and assert parsing succeeds, then change one duplicate value and assert `WebhookPayloadError`.

```python
payload["data"]["analysis"]["data_collection_results_list"] = [
    {"data_collection_id": key, "value": entry["value"]}
    for key, entry in payload["data"]["analysis"]["data_collection_results"].items()
]
assert len(parse_post_call_transcription(payload, NOW).collected_data) == 24

payload["data"]["analysis"]["data_collection_results_list"][0]["value"] = False
with pytest.raises(WebhookPayloadError, match="conflicting duplicate"):
    parse_post_call_transcription(payload, NOW)
```

- [ ] **Step 2: Verify the regression fails**

Run:

```bash
PYTHONPATH=. .venv/bin/pytest services/api/tests/test_elevenlabs_payloads.py -q
```

Expected: the identical dual representation fails with `ElevenLabs Data Collection has too many items`.

- [ ] **Step 3: Count unique collection identifiers**

Keep both entries so existing conflicting-duplicate validation still runs, but enforce the limit on unique identifiers:

```python
unique_identifiers = {identifier for identifier, _value in entries}
if len(unique_identifiers) > MAX_COLLECTION_ITEMS:
    raise WebhookPayloadError("ElevenLabs Data Collection has too many items")
```

- [ ] **Step 4: Add failing legacy inventory and dwelling tests**

Use an intake result containing:

```python
"inventory_json": json.dumps([
    {"item": "Synthetic sofa", "quantity": 1},
]),
"origin_dwelling_type": "two-bedroom apartment",
```

Assert the canonical item has `name == "Synthetic sofa"`, `room == "Unspecified"`, and the dwelling enum is `DwellingType.APARTMENT`. Add ambiguous and unsupported dwelling phrases that must still raise `DomainConflict`.

- [ ] **Step 5: Implement intake-only canonicalization**

Before `InventoryItem.model_validate(payload)`, move the legacy alias and supply a bounded room default:

```python
if "name" not in payload and isinstance(payload.get("item"), str):
    payload["name"] = payload.pop("item")
payload.setdefault("room", "Unspecified")
```

Normalize one unambiguous dwelling token from an allowlist; do not map unknown phrases to `other`.

- [ ] **Step 6: Run focused backend tests**

```bash
PYTHONPATH=. .venv/bin/pytest \
  services/api/tests/test_elevenlabs_payloads.py \
  services/api/tests/test_async_voice_orchestration.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit provider normalization**

```bash
git add services/api/app/integrations/elevenlabs/analysis.py \
  services/api/app/orchestration/voice_materializer.py \
  services/api/tests/test_elevenlabs_payloads.py \
  services/api/tests/test_async_voice_orchestration.py
git commit -m "fix: normalize live intake provider payloads"
```

---

### Task 2: Add canonical unconfirmed JobSpec replacement

**Files:**
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/api/router.py`
- Test: `services/api/tests/test_api.py`
- Test: `services/api/tests/test_service.py`

**Interfaces:**
- Consumes: `replace_job_spec(job_id: UUID, replacement: JobSpecV1) -> JobRecord`.
- Produces: `PUT /api/jobs/{job_id}` with generated `JobSpecV1` request and `JobRecord` response.

- [ ] **Step 1: Add failing service and HTTP tests**

Cover one successful unconfirmed replacement and rejection when the body job ID differs, an immutable source field changes, the job is confirmed, or the job has entered calling.

```python
replacement = record.job_spec.model_copy(update={"bedroom_count": 3}, deep=True)
response = client.put(f"/api/jobs/{record.job_spec.job_id}", json=replacement.model_dump(mode="json"))
assert response.status_code == 200
assert response.json()["job_spec"]["bedroom_count"] == 3
```

- [ ] **Step 2: Verify the route does not exist**

```bash
PYTHONPATH=. .venv/bin/pytest services/api/tests/test_api.py services/api/tests/test_service.py -q
```

Expected: replacement tests fail with HTTP 405 or a missing service method.

- [ ] **Step 3: Implement immutable and state checks**

Add a service method that requires `JobState.INTAKE_COMPLETE`, no calls, and unconfirmed current/replacement specs. Compare these immutable fields:

```python
immutable = ("job_id", "version", "intake_source", "source_context", "data_classification")
if any(getattr(current.job_spec, key) != getattr(replacement, key) for key in immutable):
    raise DomainConflict("Unconfirmed JobSpec identity cannot be changed")
```

Preserve the record timestamps except for `updated_at`, replace only `job_spec`, and save through the existing repository.

- [ ] **Step 4: Add the typed FastAPI route**

```python
@router.put("/api/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
def replace_job_spec(job_id: UUID, job_spec: JobSpecV1, service: Service) -> JobRecord:
    return service.replace_job_spec(job_id, job_spec)
```

- [ ] **Step 5: Run focused service and API tests**

```bash
PYTHONPATH=. .venv/bin/pytest services/api/tests/test_api.py services/api/tests/test_service.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Export OpenAPI and regenerate types**

```bash
PYTHONPATH=. .venv/bin/python scripts/export_openapi.py
npm --prefix apps/web run generate:api
```

Expected: `packages/contracts/openapi.json` and `apps/web/src/api/schema.d.ts` contain `put` for `/api/jobs/{job_id}`.

- [ ] **Step 7: Commit the canonical update API**

```bash
git add services/api/app/orchestration/service.py services/api/app/api/router.py \
  services/api/tests/test_api.py services/api/tests/test_service.py \
  packages/contracts/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat: persist unconfirmed job spec edits"
```

---

### Task 3: Persist confirmation editors and fix review correctness

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Modify: `apps/web/src/lib/api/adapters.ts`
- Modify: `apps/web/src/lib/api/types.ts`
- Modify: `apps/web/src/routes/confirm.$jobId.tsx`
- Modify: `apps/web/src/components/veramove/JobSpecSummary.tsx`
- Modify: `apps/web/src/lib/format.ts`
- Test: `apps/web/src/lib/api/adapters.test.ts`
- Test: `apps/web/src/lib/api/workflow.smoke.test.ts`
- Create: `apps/web/src/lib/format.test.ts`

**Interfaces:**
- Consumes: generated `JobSpecV1`, `JobRecord`, and `PUT /api/jobs/{job_id}`.
- Produces: `apiClient.replaceJobSpec(jobId, jobSpec)`, a live `updateJob(...)` that persists canonical data, and date-only formatting without UTC drift.

- [ ] **Step 1: Add failing adapter and date tests**

Assert a review draft maps back onto the current canonical spec without discarding unexposed fields, and:

```typescript
expect(longDate("2026-08-16")).toBe("August 16, 2026");
```

Run the date test under `TZ=America/New_York`.

- [ ] **Step 2: Add the generated client operation**

```typescript
replaceJobSpec: (jobId: string, jobSpec: JobSpecV1) =>
  apiFetch<JobRecord>(`/api/jobs/${jobId}`, {
    method: "PUT",
    body: JSON.stringify(jobSpec),
  }),
```

- [ ] **Step 3: Merge editable view fields into the canonical spec**

Create a focused adapter that starts from the fetched `JobSpecV1`, applies route/date/home/access,
inventory/services/extras/notes edits, preserves unexposed values, and returns `JobSpecV1`. New
inventory entries receive a browser-generated UUID and default room `Unspecified`.

- [ ] **Step 4: Persist live updates before confirmation**

Remove the live-mode skip. `onConfirm` must always call `update.mutateAsync(...)`, wait for success,
then call `confirm.mutateAsync(...)`. A failed update sets the existing confirmation error and does
not invoke confirmation.

- [ ] **Step 5: Make editor Save and Cancel truthful**

Each `FieldRow` snapshots the relevant value when opening. Cancel restores the snapshot; Save keeps
the new draft value and closes the editor. Patch handling records field-specific edited keys and
clears matching missing keys for valid values.

- [ ] **Step 6: Align completeness with visible editors**

Do not require destination parking or other hidden facts. Require only route, move date,
flexibility, one dwelling selection, editable origin/destination floor and elevator information,
origin long-carry distance, bedroom count, inventory, services, and insurance.

- [ ] **Step 7: Parse date-only strings as local calendar dates**

```typescript
const [year, month, day] = iso.split("-").map(Number);
return new Date(year, month - 1, day).toLocaleDateString("en-US", options);
```

- [ ] **Step 8: Run frontend tests and build**

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix apps/web run build
```

Expected: TypeScript, Vitest, and the production build pass.

- [ ] **Step 9: Commit frontend persistence**

```bash
git add apps/web/src
git commit -m "fix: persist live confirmation edits"
```

---

### Task 4: Tighten the reviewed intake-agent extraction contract

**Files:**
- Modify: `agents/intake/agent.yaml`
- Modify: `agents/intake/prompt.md`
- Modify: `agents/intake/data-collection.json`
- Modify: generated intake assets if `scripts/generate_agent_assets.py` owns them
- Test: `services/api/tests/test_project_assets.py`

**Interfaces:**
- Consumes: the canonical dwelling enum and `InventoryItem` shape.
- Produces: reviewed ElevenLabs configuration version `2026-07-20.1`.

- [ ] **Step 1: Add or update asset assertions**

Assert the version is `2026-07-20.1`, inventory instructions contain `name`, `quantity`, `room`,
and dwelling descriptions list the exact canonical values.

- [ ] **Step 2: Update agent prompt and collection descriptions**

Require one-at-a-time questions for both dwelling types, floor/stairs/elevator, and parking distance.
Explicitly permit `unknown` without fabrication. Define inventory JSON exactly and use
`Unspecified` for an unprovided room.

- [ ] **Step 3: Regenerate and check reviewed assets**

```bash
PYTHONPATH=. .venv/bin/python scripts/generate_agent_assets.py
PYTHONPATH=. .venv/bin/python scripts/generate_agent_assets.py --check
PYTHONPATH=. .venv/bin/pytest services/api/tests/test_project_assets.py -q
```

Expected: asset generation is clean and project-asset tests pass.

- [ ] **Step 4: Commit agent contract updates**

```bash
git add agents services/api/tests/test_project_assets.py
git commit -m "fix: align intake agent with canonical job spec"
```

---

### Task 5: Full verification, deployment, and fresh live proof

**Files:**
- Verify: entire repository
- Deploy: `main` and `deploy/veramove-demo`
- Configure: ElevenLabs intake-agent prompt/data collection in the existing production branch

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: a deployed build where a new interview completes and edits persist without operator repair.

- [ ] **Step 1: Run the required repository gate**

```bash
PYTHONPATH=. .venv/bin/python scripts/check.py
```

Expected: Ruff, pytest, OpenAPI export, API generation, TypeScript, Vitest, and Vite build all pass.

- [ ] **Step 2: Confirm a clean worktree and push**

```bash
git status --short
git push origin main
git push origin main:deploy/veramove-demo
```

Expected: both remote branches point at the verified commit.

- [ ] **Step 3: Synchronize ElevenLabs dashboard configuration**

Update the existing VeraMove Intake production branch from the reviewed prompt and data-collection
assets, publish the new provider version, and update Render's `ELEVENLABS_AGENT_CONFIG_VERSION` to
`2026-07-20.1` without revealing credentials.

- [ ] **Step 4: Verify a fresh live interview**

Start from `/intake`, complete one fictional interview, and verify:

1. the webhook returns HTTP 200 without replay;
2. the intake session becomes `completed`;
3. the frontend navigates to `/confirm/{real_job_id}`;
4. the displayed date matches the spoken date;
5. a visible editor changes a missing field;
6. confirmation persists the edit and locks version 1;
7. the calls page receives the real job ID.

- [ ] **Step 5: Record final evidence**

Report the deployed commits, commands run, test counts, live job/session IDs, webhook status, and any
remaining demo risk without including credentials, phone numbers, or transcript content.
