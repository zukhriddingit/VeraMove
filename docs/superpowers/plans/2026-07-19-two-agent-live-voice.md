# VeraMove Two-Agent Live Voice Implementation Plan

> **For agentic workers:** Execute task-by-task with tests first. Independent tasks may run in
> parallel only when their file ownership does not overlap. Keep `APP_MODE=mock` as the default and
> do not place a real call until the supervised rollout task.

**Goal:** Ship two professional ElevenLabs roles—one Intake Agent and one shared Outbound
Negotiator—that create the canonical voice JobSpec, call exactly three consenting fictional vendors
with identical locked facts, materialize signed call evidence, perform verified negotiation, and
produce a playable evidence-backed recommendation.

**Architecture:** ElevenLabs performs conversation and primitive post-call extraction; VeraMove owns
truth. Provider payloads are authenticated and parsed into internal models, transcript turns are used
transiently for bounded evidence, a hardened verification gateway creates canonical quotes, and one
transactional materialization boundary updates receipt, attempt, calls, quotes, evidence, and job
state. Inbound intake uses a separate idempotent session. The live call workflow uses a fictional
roster and three secret destination slots, never Tavily company identities.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, httpx, pytest, Ruff, Supabase/PostgreSQL RPC,
ElevenLabs Agents/Twilio, OpenAI Responses API, Tavily, TypeScript/OpenAPI generation, Vitest, Vite.

## Global Invariants

- `APP_MODE=mock` runs without credentials, Supabase, network calls, or live agent configuration.
- No secret, real phone number, caller ID, home address, raw transcript, analysis envelope, or audio
  bytes enter source control, fixtures, logs, public contracts, or normal persistence.
- The supervised demo uses fictional customer facts and three consenting role-play destinations.
- Only the confirmation API can set `confirmed`, `confirmed_at`, or `locked_version`.
- Exactly three initial attempts use deep-equal snapshots of one confirmed JobSpec version.
- One outbound agent ID handles both `quote` and `negotiation` modes.
- Call results are exactly `itemized_quote`, `callback_commitment`, `documented_decline`, or `failed`.
- A verified quote requires per-material-claim transcript evidence and a playable recording.
- Negotiation requires a verified different-vendor quote for the same JobSpec and a measurable delta.
- Provider failures never fall back to mock behavior.
- Public API changes regenerate and commit OpenAPI plus frontend types.
- Every implementation task ends with focused tests and a narrow commit.

---

### Task 0: Capture the Clean Baseline

**Files:** None.

- [ ] **Step 1: Confirm branch and worktree**

```bash
git status --short --branch
git log -3 --oneline
```

- [ ] **Step 2: Run the high-risk regression oracle**

```bash
.venv/bin/pytest services/api/tests/test_contracts.py services/api/tests/test_intelligence.py services/api/tests/test_service.py services/api/tests/test_webhooks.py services/api/tests/test_supabase_repository.py -q
```

Expected: current tests pass before implementation. Record the count; do not hide or reclassify an
existing failure.

---

### Task 1: Harden Canonical Call and Outcome Contracts

**Files:**
- Modify: `services/api/app/contracts/models.py`
- Test: `services/api/tests/test_contracts.py`
- Test: `services/api/tests/test_voice_tools.py`

**Interfaces:**
- `CallOutcome` forbids fields belonging to another outcome type.
- `CallRecord.recording_url` is optional only for non-quote outcomes without saved audio.
- Terminal status, completion time, quote/evidence/call recording identity, and callback timing are
  internally consistent.

- [ ] **Step 1: Write failing strict-outcome tests**

Add parameterized tests proving:

```python
CallOutcome(type="itemized_quote", quote=quote, reason="mixed")
CallOutcome(type="callback_commitment", callback_at=future, quote=quote)
CallOutcome(type="documented_decline", reason="Declined", callback_at=future)
CallOutcome(type="failed", reason="No answer", quote=quote)
```

all fail validation, while each exact supported shape passes.

- [ ] **Step 2: Write failing CallRecord consistency tests**

Cover completed status without `completed_at`, in-progress status with a terminal outcome, an itemized
quote without `recording_url`, and a timezone-naive/past callback. Assert a failed never-connected
call may omit the URL.

- [ ] **Step 3: Run focused failures**

Run:

```bash
.venv/bin/pytest services/api/tests/test_contracts.py services/api/tests/test_voice_tools.py -q
```

Expected: new tests fail under the permissive current validators.

- [ ] **Step 4: Implement model validators**

Keep `QuoteV1` and `TranscriptEvidence.recording_url` required. Make only
`CallRecord.recording_url: HttpUrl | None`, require it for `itemized_quote`, and enforce exact
outcome-detail combinations. Validate callback timestamps at orchestration completion time rather
than with wall-clock work inside a pure contract.

- [ ] **Step 5: Run focused tests and commit**

```bash
.venv/bin/pytest services/api/tests/test_contracts.py services/api/tests/test_voice_tools.py -q
git add services/api/app/contracts/models.py services/api/tests/test_contracts.py services/api/tests/test_voice_tools.py
git commit -m "feat(contracts): harden live call outcomes"
```

---

### Task 2: Generate the Two Professional Agent Configurations

**Files:**
- Modify: `agents/intake/prompt.md`
- Modify: `agents/intake/agent.yaml`
- Modify: `agents/intake/README.md`
- Modify: `agents/negotiator/prompt.md`
- Modify: `agents/negotiator/agent.yaml`
- Modify: `agents/negotiator/README.md`
- Modify: `agents/tools.yaml`
- Create: `agents/intake/data-collection.json`
- Create: `agents/negotiator/data-collection.json`
- Create: `agents/negotiator/generated-fee-probes.md`
- Create: `agents/elevenlabs-dashboard-checklist.md`
- Create: `scripts/generate_agent_assets.py`
- Test: `services/api/tests/test_project_assets.py`
- Test: `services/api/tests/test_scripts.py`

**Interfaces:**
- Exactly two role directories remain: intake and negotiator.
- Generated analysis identifiers match the backend allowlists and stay below 25 per agent.
- The outbound prompt branches on `call_mode=quote|negotiation` and all fee probes come from
  `configs/moving.yaml`.

- [ ] **Step 1: Replace exact starter assertions with failing professional-agent assertions**

Assert AI/recording disclosure, consent/stop behavior, readback without confirmation, required custom
dynamic variables, exact four outcomes, verified leverage rules, no booking, and quote/negotiation
branches. Assert no phone-number pattern or secret placeholder value is present.

- [ ] **Step 2: Add a failing deterministic-generation test**

Run the generator into a temporary directory and compare its JSON/Markdown bytes with the committed
assets. Assert all configured mandatory fee categories appear exactly once in the generated probe
fragment.

- [ ] **Step 3: Implement the generator**

Read `configs/moving.yaml`, emit the 24-field intake schema and 14-field outbound schema from the
approved design, and emit the fee-probe Markdown. Use stable sorting/indentation and `--check` mode.
The script must not call ElevenLabs or read environment secrets.

- [ ] **Step 4: Expand prompts and YAML**

Add repository `agent_config_version`, dynamic-variable declarations, data-collection file reference,
first-message disclosure, role-play truth boundary, missing-field loop, and exact termination rules.
Keep dashboard sync manual/API-explicit; do not imply YAML auto-deploys itself.

The dashboard checklist records exact display names, dynamic variables, Data Collection schema,
success evaluation, first messages, prompt/config version, Audio Saving, retention, call limits,
pre-call toggle, post-call transcription webhook, retries, and the deliberate absence of the audio
webhook. It contains no actual IDs, secrets, or numbers.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/python scripts/generate_agent_assets.py --check
.venv/bin/pytest services/api/tests/test_project_assets.py services/api/tests/test_scripts.py -q
git add agents scripts/generate_agent_assets.py services/api/tests/test_project_assets.py services/api/tests/test_scripts.py
git commit -m "feat(agents): define intake and outbound roles"
```

---

### Task 3: Add Fail-Closed Two-Agent and Three-Destination Settings

**Files:**
- Modify: `services/api/app/core/config.py`
- Modify: `.env.example`
- Modify: `render.yaml`
- Test: `services/api/tests/test_live_integrations_config.py`
- Test: `services/api/tests/test_live_integrations_wiring.py`

**Interfaces:**
- `LiveVoiceConfig` exposes intake/outbound IDs, exactly three destinations, public origin, recording
  signing secret, pre-call secret, operator-repair secret, and repository agent-config version.
- Full live mode requires Supabase and rejects ambiguous legacy settings.

- [ ] **Step 1: Write failing configuration tests**

Cover missing agent IDs, divergent old quote/negotiator aliases, missing/duplicate/malformed E.164
destinations, one or four values, HTTP public origin, short signing/pre-call secrets, live without
Supabase, missing/short `VOICE_OPERATOR_SECRET`, and populated live values in mock mode. Prove mock
construction remains credential-free.

- [ ] **Step 2: Implement strict parsing**

Parse `LIVE_TEST_TO_NUMBERS` as exactly three trimmed unique E.164 values. Prefer
`ELEVENLABS_OUTBOUND_AGENT_ID`; accept the two legacy IDs only when both exist and are equal. Remove
the singular live destination from the full workflow. Validate `PUBLIC_API_BASE_URL` as HTTPS.

- [ ] **Step 3: Keep enablement explicit**

`require_live_voice_config()` must require `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`,
`SUPABASE_ENABLED=true`, both agents, phone-number ID, HMAC/pre-call/signing/operator secrets, public
origin, agent config version, and three destinations. Loading settings may not initiate network
traffic.

- [ ] **Step 4: Update secret-name declarations only**

Add new Render keys with `sync:false`; keep values absent. Keep Blueprint defaults at mock/disabled.
Remove obsolete singular destination documentation without touching actual dashboard values.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_live_integrations_config.py services/api/tests/test_live_integrations_wiring.py -q
git add services/api/app/core/config.py .env.example render.yaml services/api/tests/test_live_integrations_config.py services/api/tests/test_live_integrations_wiring.py
git commit -m "feat(config): require two agents and three live targets"
```

---

### Task 3A: Build Stable Signed Recording Capability URLs

**Files:**
- Create: `services/api/app/orchestration/recording_capability.py`
- Test: `services/api/tests/test_recordings.py`

**Interfaces:**
- `RecordingCapabilitySigner.build_url(call_id, job_id) -> HttpUrl`
- `RecordingCapabilitySigner.verify(call_id, job_id, signature) -> None`

- [ ] **Step 1: Write failing deterministic signing tests**

Assert URLs use validated `PUBLIC_API_BASE_URL`, contain the canonical call ID and an HMAC capability,
verify with constant-time comparison, reject call/job/signature tampering, contain no provider key,
and are revoked when `RECORDING_SIGNING_SECRET` rotates.

- [ ] **Step 2: Implement the pure signer**

Sign a versioned canonical message containing job and call UUIDs with SHA-256. Do not access a
repository, provider, network, clock, or audio bytes. This primitive exists before evidence mapping so
every canonical `TranscriptEvidence` and verified `QuoteV1` receives its real final URL, never a
placeholder.

- [ ] **Step 3: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_recordings.py -q
git add services/api/app/orchestration/recording_capability.py services/api/tests/test_recordings.py
git commit -m "feat(voice): sign canonical recording URLs"
```

---

### Task 4: Extend Internal Call Models and the ElevenLabs Outbound Adapter

**Files:**
- Modify: `services/api/app/orchestration/models.py`
- Modify: `services/api/app/orchestration/providers.py`
- Modify: `services/api/app/integrations/elevenlabs/base.py`
- Modify: `services/api/app/integrations/elevenlabs/live.py`
- Modify: `services/api/app/integrations/elevenlabs/mock.py`
- Test: `services/api/tests/test_live_voice.py`
- Test: `services/api/tests/test_voice_tools.py`

**Interfaces:**
- `CallAttempt` persists destination slot, expected agent/config, mode, snapshot hash, provider version,
  and optional negotiation context.
- `VoiceProvider` receives an explicit stable destination slot.
- Both modes call one outbound agent and pass `call_mode` dynamically.

- [ ] **Step 1: Add failing model and request-payload tests**

Assert three quote calls produce three payloads with distinct `to_number`, the same `agent_id`,
`call_mode=quote`, deep-equal `job_spec_json`, matching job/call/vendor/version fields, and recording
enabled. Assert negotiation uses the same agent, `call_mode=negotiation`, the target slot, and
`comparable_total if comparable_total is not None else negotiated_total` leverage rather than
truthiness or the string `None`.

- [ ] **Step 2: Add snapshot hashing and negotiation-context models**

Hash canonical sorted `JobSpecV1.model_dump_json()` with SHA-256. Add strict bounded internal fields;
do not add phone values. Store provider `version_id` only after completion.

- [ ] **Step 3: Change the provider protocol**

Add `destination_slot: Literal[0, 1, 2]` to quote initiation and reuse the original quote slot for
negotiation. Set live `initial_call_limit=3`; mock ignores the destination value but keeps the same
signature.

- [ ] **Step 4: Update the live adapter**

Resolve the number only inside `_initiate`. Pass supported primitive dynamic variables, keep the
locked JSON identical, and fail before transport on invalid slot/config. Never expose a destination
in `VoiceCallReference`, exceptions, or logs.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_live_voice.py services/api/tests/test_voice_tools.py -q
git add services/api/app/orchestration/models.py services/api/app/orchestration/providers.py services/api/app/integrations/elevenlabs services/api/tests/test_live_voice.py services/api/tests/test_voice_tools.py
git commit -m "feat(voice): route three calls through one agent"
```

---

### Task 5: Separate the Fictional Call Roster from Tavily Discovery

**Files:**
- Create: `services/api/app/orchestration/role_play.py`
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/api/dependencies.py`
- Modify: `data/demo/vendors.json` only if classification/labels require correction
- Test: `services/api/tests/test_service.py`
- Test: `services/api/tests/test_live_integrations_wiring.py`
- Test: `services/api/tests/test_tavily_live.py`

**Interfaces:**
- `RolePlayVendorRoster.list_initial_vendors() -> tuple[Vendor, Vendor, Vendor]` is the only call-list
  source.
- Tavily remains available through the discovery API and never determines who the teammate calls
  represent.

- [ ] **Step 1: Write a failing all-integrations-enabled test**

Inject Tavily candidates with recognizable real-company labels, start calls, and assert none appears
in any attempt. Assert exactly the three fictional role-play fixture vendors appear and Tavily's
separate discovery source still reports `tavily`.

- [ ] **Step 2: Implement and inject the roster**

Validate exactly three distinct role-play vendors at construction. Remove `_initial_vendors()` use of
the discovery gateway for call execution. Keep discovery code and API unchanged.

- [ ] **Step 3: Enumerate stable destination slots**

Create all three attempts before provider invocation, zip vendors with slots 0..2, and preserve their
deep-equal locked snapshots. A synchronous initiation failure becomes one failed outcome and the loop
continues; arbitrary programming/validation exceptions remain visible.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_service.py services/api/tests/test_live_integrations_wiring.py services/api/tests/test_tavily_live.py -q
git add services/api/app/orchestration/role_play.py services/api/app/orchestration/service.py services/api/app/api/dependencies.py data/demo/vendors.json services/api/tests/test_service.py services/api/tests/test_live_integrations_wiring.py services/api/tests/test_tavily_live.py
git commit -m "feat(orchestration): isolate fictional live call roster"
```

---

### Task 6: Add Idempotent Intake Sessions and Pre-Call Personalization

**Files:**
- Create: `services/api/app/orchestration/intake_sessions.py`
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase.py`
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/api/dependencies.py`
- Test: `services/api/tests/test_service.py`
- Test: `services/api/tests/test_api.py`
- Test: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- `IntakeSession` exists before a `JobRecord`; post-call completion atomically creates the normal
  unconfirmed voice job.
- Pre-call replay by provider call key returns the same session/job IDs without retaining phones.

- [ ] **Step 1: Write failing repository/session tests**

Cover web-session creation, pre-call creation, same-call replay, different-call isolation, strict
agent validation, safe hashed provider key, status transitions, and lookup by session/conversation.
Inspect serialized storage and assert caller/called number strings are absent.

- [ ] **Step 2: Implement the internal model and repository protocol**

Use statuses `pending`, `in_progress`, `completed`, `failed`. Store expected intake agent ID, repo
agent-config version, reserved job ID, optional conversation ID, timestamps, and no `JobSpec` until
completion.

- [ ] **Step 3: Add pre-call API models and route**

Validate the dedicated header secret before using body data. Accept provider `caller_id` and
`called_number` only as ignored fields. Return the exact ElevenLabs
`conversation_initiation_client_data` envelope containing all three defined variables and no prompt
override. Keep work bounded and synchronous.

- [ ] **Step 4: Add typed session retrieval**

Implement POST create, GET by session, and GET by conversation. Incomplete sessions return safe
status/IDs; completed sessions return the canonical unconfirmed JobSpec. No route lists all sessions.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_api.py services/api/tests/test_service.py services/api/tests/test_supabase_repository.py -q
git add services/api/app/orchestration/intake_sessions.py services/api/app/repositories services/api/app/api services/api/tests/test_api.py services/api/tests/test_service.py services/api/tests/test_supabase_repository.py
git commit -m "feat(intake): add idempotent voice sessions"
```

---

### Task 7: Parse Signed ElevenLabs Completion and Initiation-Failure Events

**Files:**
- Create: `services/api/app/integrations/elevenlabs/models.py`
- Create: `services/api/app/integrations/elevenlabs/analysis.py`
- Modify: `services/api/app/integrations/elevenlabs/webhook.py`
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py`
- Test: `services/api/tests/test_webhooks.py`
- Test: `services/api/tests/test_api.py`

**Interfaces:**
- HMAC verification still occurs over raw bytes before JSON parsing.
- Provider envelopes tolerate extra fields but retain only allowlisted typed values and bounded
  transcript turns during request processing.
- Data Collection accepts documented map/list wrappers and never converts missing/null to zero/false.

- [ ] **Step 1: Add realistic failing provider fixtures**

Create synthetic signed payloads for `post_call_transcription` with nested dynamic variables,
map-shaped results, list-shaped results, transcript timestamps, version/agent fields, and `has_audio`;
plus `call_initiation_failure` for busy/no-answer/unknown. Include arbitrary phones, summaries,
rationales, and tool metadata and assert none survives normalization.

- [ ] **Step 2: Add invalid/mismatch coverage**

Test stale/bad signature, unsupported type, structurally invalid agent/correlation fields, missing
value, duplicate identifier, oversize JSON string, invalid decimals/enums, and malformed transcript
turn timing. Repository-aware mismatches against the expected call/job/vendor/version/mode belong to
Task 10, not this provider parser.

- [ ] **Step 3: Implement typed envelopes and collection extraction**

Model only required top-level/data fields with tolerant extras. Normalize map/list collection entries
to `dict[str, primitive | None]`. Parse list JSON with explicit byte/item limits. Return an internal
authenticated event containing transient transcript turns, never the provider's arbitrary dict.

Change the FastAPI handler to accept only `Request`, read raw bytes, verify them, and only then parse.
Do not declare a `Body()` model that allows FastAPI to parse first. Preserve request-body OpenAPI
documentation with route metadata/schema references rather than runtime pre-validation.

- [ ] **Step 4: Preserve failure-event metadata minimization**

Keep only the safe failure reason and correlation fields. Do not retain Twilio/SIP bodies.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_webhooks.py services/api/tests/test_api.py -q
git add services/api/app/integrations/elevenlabs/models.py services/api/app/integrations/elevenlabs/analysis.py services/api/app/integrations/elevenlabs/webhook.py services/api/app/api/models.py services/api/app/api/router.py services/api/tests/test_webhooks.py services/api/tests/test_api.py
git commit -m "feat(webhooks): parse signed voice completion data"
```

---

### Task 8: Harden Per-Claim Quote Verification and Ranking Eligibility

**Files:**
- Modify: `services/api/app/intelligence/quotes.py`
- Modify: `services/api/app/intelligence/ranking.py`
- Modify: `services/api/app/orchestration/providers.py`
- Modify: `services/api/app/api/dependencies.py`
- Create: `services/api/app/orchestration/evidence.py`
- Test: `services/api/tests/test_intelligence.py`
- Test: `services/api/tests/test_service.py`

**Interfaces:**
- Injected `QuoteVerificationGateway` consumes provisional fee facts and timestamped evidence.
- Every material known amount/term is supported by matching call evidence.
- Ranking accepts only verified, nonfabricated, same-version quotes.

- [ ] **Step 1: Write failing evidence-granularity tests**

Provide a total supported by one excerpt but an unsupported known stairs fee, binding claim, or
availability claim. Assert the quote is partially verified and ineligible. Add passing cases with
per-claim evidence IDs.

- [ ] **Step 2: Write failing ranking filters**

Mix verified, partial, fabricated, wrong-version, and missing-recording quotes. Assert only eligible
quotes can rank or supply leverage.

- [ ] **Step 3: Implement evidence mapping**

Create deterministic bounded excerpts from transcript turns using `time_in_call_secs`; derive end
time from the next turn or bounded duration; require the material phrase/amount to appear; and attach
the same canonical recording URL. Do not persist the full transcript.

- [ ] **Step 4: Inject and harden the verifier**

Expose a small protocol in orchestration and wire `QuoteVerifier`; do not import external SDKs in the
service. Strengthen measurable negotiation comparison to price, deposit, binding status, or newly
added configured concessions only.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_intelligence.py services/api/tests/test_service.py -q
git add services/api/app/intelligence services/api/app/orchestration/providers.py services/api/app/orchestration/evidence.py services/api/app/api/dependencies.py services/api/tests/test_intelligence.py services/api/tests/test_service.py
git commit -m "feat(intelligence): require per-claim quote evidence"
```

---

### Task 9: Add Leased Webhook Receipts and Atomic Materialization RPC

**Files:**
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase_client.py`
- Modify: `services/api/app/repositories/supabase.py`
- Create: `supabase/migrations/202607190003_live_voice_materialization.sql`
- Test: `services/api/tests/test_repository_and_adapters.py`
- Test: `services/api/tests/test_supabase_client.py`
- Test: `services/api/tests/test_supabase_repository.py`

**Interfaces:**
- `claim_voice_webhook_receipt`, `finalize_voice_webhook`, and `fail_voice_webhook_receipt` have
  compare-and-set/lease semantics.
- Finalization atomically writes safe canonical rows and one aggregate transition.

- [ ] **Step 1: Write failing in-memory concurrency tests**

Use threads/barriers to prove one unexpired lease winner, failed/expired reclaim, wrong-token finalize
rejection, processed duplicate acknowledgement, and exactly-once result under three concurrent
out-of-order completions.

- [ ] **Step 2: Write failing Supabase transport/RPC tests**

Add an allowlisted `rpc(name, payload)` client method. Reject arbitrary function names. Assert no raw
transcript, analysis, phone, audio, or secret key can appear in the finalize payload.

- [ ] **Step 3: Add schema columns and constraints**

Add intake sessions, receipt status/lease columns, first-class call-attempt kind/spec-version/slot,
expected agent/config/mode/hash fields, negotiation context, aggregate revision, and the unique
`(job_id, vendor_id, kind, job_spec_version)` constraint. Preserve existing data through safe defaults
or backfill before `NOT NULL`.

- [ ] **Step 4: Implement the PostgreSQL functions**

Functions validate lease ownership, use one transaction, update normalized tables, rebuild/advance
the job aggregate without lost updates, and mark the receipt processed. Grant execute only to the
server-side role used by VeraMove.

- [ ] **Step 5: Implement repository adapters**

Mirror RPC behavior under `RLock` in memory. Supabase sends only model-validated JSON. Replace the old
permanent boolean `reserve_webhook` path after compatibility tests migrate.

- [ ] **Step 6: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_repository_and_adapters.py services/api/tests/test_supabase_client.py services/api/tests/test_supabase_repository.py -q
git add services/api/app/repositories supabase/migrations/202607190003_live_voice_materialization.sql services/api/tests/test_repository_and_adapters.py services/api/tests/test_supabase_client.py services/api/tests/test_supabase_repository.py
git commit -m "feat(persistence): finalize voice events atomically"
```

---

### Task 10: Materialize Intake, Three Calls, and Negotiation Asynchronously

**Files:**
- Create: `services/api/app/orchestration/voice_materializer.py`
- Modify: `services/api/app/orchestration/service.py`
- Modify: `services/api/app/orchestration/tools.py`
- Modify: `services/api/app/api/dependencies.py`
- Test: `services/api/tests/test_webhooks.py`
- Test: `services/api/tests/test_service.py`
- Test: `services/api/tests/test_voice_tools.py`

**Interfaces:**
- Authenticated provider events route by agent role/mode into intake, quote, negotiation, or failure
  materialization.
- Three terminal initial outcomes advance to `quotes_ready`; negotiation needs two eligible quotes.

- [ ] **Step 1: Write a live-shaped fake end-to-end test**

Exercise intake webhook -> unconfirmed voice JobSpec -> confirmation -> three accepted call references
-> three signed out-of-order completion events -> two verified quotes plus one supported non-quote ->
negotiation event -> measurable improvement -> completed recommendation.

- [ ] **Step 2: Add negative workflow tests**

Cover one/zero eligible quotes, partially verified itemized quote, replay, transient finalize failure
and repair, repository mismatches for expected agent/call/job/vendor/version/mode/conversation,
wrong snapshot hash, call failure without recording, callback future validation, no-improvement
negotiation, and provider failure after accepted reference not redialing.

- [ ] **Step 3: Implement the materializer**

Cross-check stored expected agent/config/mode/hash, call/job/vendor/version and conversation. Claim a
receipt, build safe canonical models, invoke atomic finalize, and mark bounded failure status when
needed. Never pass the raw provider envelope to repositories.

- [ ] **Step 4: Add asynchronous reconciliation**

Initial terminal count is based on exactly three unique quote attempts, not quote count. Transition
once. Keep `quotes_ready` with `insufficient_verified_quotes` conflict when leverage is impossible.
For negotiation, compare with stored target/competitor context, finalize the improved quote, rank only
eligible quotes, narrate, and transition once.

- [ ] **Step 5: Complete intake materialization**

Validate collection into `JobSpecV1(intake_source=voice, confirmed=false, locked_version=None,
data_classification=role_play)`, compute missing fields canonically, create the JobRecord, complete the
session, and discard transient transcript values.

- [ ] **Step 6: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_webhooks.py services/api/tests/test_service.py services/api/tests/test_voice_tools.py -q
git add services/api/app/orchestration/voice_materializer.py services/api/app/orchestration/service.py services/api/app/orchestration/tools.py services/api/app/api/dependencies.py services/api/tests/test_webhooks.py services/api/tests/test_service.py services/api/tests/test_voice_tools.py
git commit -m "feat(orchestration): materialize live voice outcomes"
```

---

### Task 11: Proxy Recording Audio and Repair Missed Conversations

**Files:**
- Create: `services/api/app/integrations/elevenlabs/conversations.py`
- Create: `services/api/app/integrations/elevenlabs/recordings.py`
- Modify: `services/api/app/integrations/elevenlabs/base.py`
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/api/dependencies.py`
- Test: `services/api/tests/test_live_voice.py`
- Test: `services/api/tests/test_api.py`

**Interfaces:**
- Conversation client fetches details/audio server-side and translates errors safely.
- The streaming route verifies URLs produced by Task 3A and never contains the provider key.
- Repair accepts only `done`+analysis or provider `failed`.

- [ ] **Step 1: Write failing client/proxy tests**

Cover GET details/audio endpoints, required `xi-api-key`, `has_audio=false`, deleted/missing audio,
wrong content type, timeouts, non-object details, and provider status states. Assert exception text and
logs contain no credentials or URL signature.

- [ ] **Step 2: Write failing route-capability integration tests**

Use the Task 3A signer to build a real canonical URL, prove the route verifies it against the stored
call/job pair, and reject tampering or a signature from a rotated secret. Do not reimplement signing
inside the ElevenLabs integration.

- [ ] **Step 3: Implement streaming route**

Resolve only a canonical role-play call, verify signature, fetch provider audio, whitelist audio MIME
types, set no-store headers, stream without persisting bytes, and return safe 404/502 responses.

- [ ] **Step 4: Implement repair route/service**

Require explicit operator/demo authorization header, fetch by stored conversation ID, pass completed
analysis through the same materializer, or produce a failed outcome from provider `failed`. Reject
partial statuses. Keep it idempotent.

- [ ] **Step 5: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_live_voice.py services/api/tests/test_api.py -q
git add services/api/app/integrations/elevenlabs services/api/app/api services/api/tests/test_live_voice.py services/api/tests/test_api.py
git commit -m "feat(voice): stream recordings and repair calls"
```

---

### Task 12: Add OpenAI Credit/Usage Observability

**Files:**
- Create: `services/api/app/observability/usage.py`
- Create: `services/api/app/observability/__init__.py`
- Modify: `services/api/app/integrations/openai/live.py`
- Modify: `services/api/app/integrations/openai/document.py`
- Modify: `services/api/app/integrations/openai/recommendation.py`
- Modify: `services/api/app/api/models.py`
- Modify: `services/api/app/api/router.py`
- Modify: `services/api/app/api/dependencies.py`
- Test: `services/api/tests/test_openai_live.py`
- Test: `services/api/tests/test_api.py`

**Interfaces:**
- Safe usage records contain capability, model, input/output/total tokens, latency, success category,
  and provider request ID when supplied.
- No prompt, document, transcript, API key, or model response text is stored.

- [ ] **Step 1: Write failing usage extraction/redaction tests**

Use synthetic OpenAI responses with `usage`. Assert document extraction and narrative calls record the
correct capability/model/token totals once. Scan serialized records for input text and secret values.

- [ ] **Step 2: Implement an injected usage recorder**

Use a thread-safe bounded in-memory aggregate suitable for the one-instance demo. Recording failure
must never break the primary provider response. Keep Supabase usage persistence out of the critical
path.

- [ ] **Step 3: Add a safe integration-status endpoint**

Return enabled/healthy flags and aggregate usage by capability/model, not keys or environment values.
This provides demo evidence that document and recommendation OpenAI calls are active.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_openai_live.py services/api/tests/test_api.py -q
git add services/api/app/observability services/api/app/integrations/openai services/api/app/api services/api/tests/test_openai_live.py services/api/tests/test_api.py
git commit -m "feat(openai): expose safe usage telemetry"
```

---

### Task 13: Regenerate API Contracts and Update Typed Frontend Boundaries

**Files:**
- Modify: `packages/contracts/openapi.json` via generator
- Modify: generated API types under `apps/web`
- Modify: typed frontend call sites only as required for compilation
- Test: `services/api/tests/test_openapi.py`
- Test: frontend typecheck/Vitest

**Interfaces:**
- FastAPI OpenAPI remains canonical.
- No handwritten duplicate JobSpec/call/quote models are introduced.

- [ ] **Step 1: Add/adjust OpenAPI schema assertions**

Assert intake-session routes, pre-call and post-call webhook payloads, recording/repair routes, usage
status, optional non-quote recording URL, the closed call-outcome enum, and documented runtime
exclusivity validators. Do not require a discriminated-union schema unless Task 1 explicitly changes
the public contract to one.

- [ ] **Step 2: Export and generate**

```bash
.venv/bin/python scripts/export_openapi.py
npm --prefix apps/web run generate:api
```

- [ ] **Step 3: Fix typed call sites without frontend redesign**

Only update compile errors or shared API client methods. Do not implement the member-3 UI.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_openapi.py -q
npm --prefix apps/web run typecheck
npm --prefix apps/web test -- --run
git add packages/contracts/openapi.json apps/web services/api/tests/test_openapi.py
git commit -m "chore(api): publish live voice contracts"
```

---

### Task 14: Update Runbooks, Deployment Declarations, and Preflight

**Files:**
- Create: `scripts/live_voice_preflight.py`
- Create: `scripts/live_voice_smoke.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/integration-boundaries.md`
- Modify: `docs/backend-voice-runbook.md`
- Modify: `docs/backend-voice-pr-summary.md`
- Modify: `render.yaml`
- Modify: `.env.example`
- Test: `services/api/tests/test_documentation.py`
- Test: `services/api/tests/test_scripts.py`

**Interfaces:**
- Old “one call only/no canonical report” limitations are removed only after tests prove replacement.
- Preflight checks configuration, agent identity/config version, audio saving/retention, concurrency,
  daily limits, provider credits, Supabase connectivity, and public webhook reachability without
  printing secrets or phone numbers.

- [ ] **Step 1: Write failing documentation/preflight tests**

Assert no obsolete limitation remains, both agent roles and exact-three flow are documented, and
preflight output contains only booleans/counts/redacted identifiers. Use fake provider clients.

- [ ] **Step 2: Implement preflight with `--check-only`**

No call placement. Report safe pass/fail categories and refuse full-live readiness when any mandatory
guard fails. Call it a “three-call run,” never ElevenLabs Batch Calling.

Implement and test `live_voice_smoke.py` as a separate explicit operator command. It invokes the
provider for slot zero only, uses a supplied synthetic locked fixture context, prints only safe
provider/correlation status, and never creates or transitions a canonical batch/job. It refuses to
run without the same fail-closed live guards and an explicit confirmation flag.

- [ ] **Step 3: Update runbooks**

Document agent dashboard configuration, Data Collection import/copy, pre-call/post-call URLs,
transcription retry behavior, Audio Saving/nonzero short retention, three consenting numbers, Render
vars, Supabase migration, one-call supervised provider smoke, repair path, and rollback to mock.

- [ ] **Step 4: Verify and commit**

```bash
.venv/bin/pytest services/api/tests/test_documentation.py services/api/tests/test_scripts.py -q
git add scripts/live_voice_preflight.py scripts/live_voice_smoke.py README.md docs render.yaml .env.example services/api/tests/test_documentation.py services/api/tests/test_scripts.py
git commit -m "docs(voice): publish two-agent live runbook"
```

---

### Task 15: Run Full Automated Gates and Completion Audit

**Files:**
- Modify only files required by test failures that are within this plan.
- Record verification evidence in the final handoff; do not create fake pass artifacts.

- [ ] **Step 1: Run focused voice suite**

```bash
.venv/bin/pytest services/api/tests/test_contracts.py services/api/tests/test_live_voice.py services/api/tests/test_webhooks.py services/api/tests/test_voice_tools.py services/api/tests/test_service.py services/api/tests/test_supabase_repository.py -q
```

- [ ] **Step 2: Run the canonical repository gate**

```bash
.venv/bin/python scripts/check.py
```

Expected: Ruff, full pytest, OpenAPI export, frontend generation, TypeScript, Vitest, and Vite build
all pass with no generated diff.

- [ ] **Step 3: Run evals**

```bash
.venv/bin/python -m evals.run
```

Expected: 14/14 or better, including identical locked facts, evidence gating, honesty, and measurable
negotiation.

- [ ] **Step 4: Audit every design acceptance requirement**

Inspect contracts, agent asset count, config fail-closed behavior, three payloads, fake provider
end-to-end result, migration/RPC coverage, OpenAPI/frontend generation, telemetry redaction, recording
signature tests, and dirty-worktree state. Do not claim live success from fakes.

- [ ] **Step 5: Commit any final scoped corrections**

```bash
git status --short
git log --oneline --decorate -15
```

---

### Task 16: Configure Providers and Run the Supervised Live Demo

**External systems:**
- ElevenLabs Agents dashboard/API
- Imported Twilio number
- Render environment/deployment
- Supabase SQL editor/database
- Three consenting teammate phones

**Safety:** Do not paste or print secret/phone values in terminal output, chat, commits, screenshots,
or logs. Use browser secret fields/Render controls. Keep all spoken customer/vendor facts fictional.

- [ ] **Step 1: Apply the Supabase migration**

Apply `202607190003_live_voice_materialization.sql` to the enabled project and verify the RPCs through
safe repository smoke checks.

- [ ] **Step 2: Configure exactly two ElevenLabs agents**

Create/update `VeraMove Intake` and `VeraMove Outbound Negotiator` from committed assets. Configure
the exact Data Collection schemas, dynamic variables, `AGENT_CONFIG_VERSION`, disclosure first
messages, Audio Saving, and short nonzero retention. Assign the imported Twilio number inbound to
Intake; outbound requests explicitly select the Outbound agent.

- [ ] **Step 3: Configure signed provider webhooks**

Set the Render pre-call and post-call HTTPS URLs in ElevenLabs, add secrets through header/HMAC
controls, enable transcription retries, and leave audio webhook delivery disabled.

- [ ] **Step 4: Add Render secrets and deploy**

Add the two agent IDs, three destination numbers, phone-number ID, pre/post-call secrets, recording
signing secret, public origin, agent config version, and enable flags through secret UI. Keep values
out of source/logs. Deploy the tested commit and run health/preflight.

- [ ] **Step 5: Run progressive supervised tests**

1. One fictional intake call creates an unconfirmed role-play JobSpec.
2. Confirm and lock it through the API/UI.
3. Use the operator-only single-slot command for one outbound quote and verify canonical webhook,
   evidence, and playback; discard that smoke job.
4. Create a fresh job and run all three consenting role-play calls.
5. Verify exactly three identical snapshot hashes, three terminal outcomes, at least two eligible
   quotes, and `quotes_ready`.
6. Run negotiation, verify a measurable improvement, and fetch the completed report.
7. Play every cited recording link and inspect safe OpenAI/Tavily/Supabase indicators.

- [ ] **Step 6: Roll back safely on failure**

Disable `LIVE_CALLS_ENABLED`, preserve canonical debugging metadata without phones/transcripts, use
conversation repair when appropriate, and do not redial an accepted attempt. Re-enable only after the
specific failing gate is corrected.

- [ ] **Step 7: Final completion evidence**

Record safe job/call IDs, HTTP states, outcome counts, snapshot-hash equality, verified quote count,
negotiation delta, report evidence count, and gate/eval results. Only then mark the goal complete.

## Parallel Execution Map

After Task 0 and Task 1 land, use dependency-aware lanes with explicit merge barriers:

```text
Phase 1 parallel: Task 2 | Task 3 | Task 7
Phase 2: Task 3 -> Task 3A -> Task 8
Phase 2: Task 3 -> Task 4 -> Task 5
Phase 2: Task 3 -> Task 6
Phase 3: Tasks 4 + 6 -> Task 9
Integration barrier: Tasks 3A + 5 + 6 + 7 + 8 + 9 -> Task 10
Root finish: Task 11, Task 12, then Tasks 13–16
```

The root agent owns merge points in `service.py`, `dependencies.py`, `router.py`, repository
protocols, and generated contracts. Subagents must not edit overlapping files concurrently. Before a
lane starts, assign explicit file ownership; after each lane commit, inspect its diff and run focused
tests before starting the dependent integration.
