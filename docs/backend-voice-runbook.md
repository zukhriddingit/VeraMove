# Backend voice smoke and release runbook

This is the operator runbook for VeraMove's two live ElevenLabs roles: **VeraMove Intake** and the
single **VeraMove Outbound Negotiator**. Mock mode remains the normal development and CI path. Live
voice supports a supervised role-play path and a separately gated official-business path. Neither
path grants permission by itself: every destination owner must explicitly authorize the AI call and
recording, and no real business is called during deployment verification.

## Deterministic mock smoke test

From the repository root, bootstrap dependencies and run every repository gate:

```bash
python scripts/bootstrap.py
python scripts/check.py
```

Start the API and web app in a first terminal:

```bash
APP_MODE=mock python scripts/dev.py
```

In a second terminal, run the HTTP workflow below in order. It needs only `curl` and the repository
virtual environment; it does not require credentials, Supabase, or network access beyond the local
API.

1. Create one job from synthetic document intake.

   ```bash
   export VM_API_BASE_URL=http://127.0.0.1:8000
   curl -fsS -X POST "$VM_API_BASE_URL/api/intake/document" \
     -H 'content-type: application/json' \
     --data '{"document_text":"Synthetic VeraMove smoke inventory for a two-bedroom demo move."}' \
     -o /tmp/veramove-intake.json
   export VM_JOB_ID="$(.venv/bin/python -c 'import json; print(json.load(open("/tmp/veramove-intake.json", encoding="utf-8"))["job_spec"]["job_id"])')"
   ```

2. Confirm and lock the generated `JobSpecV1`.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/confirm" \
     -o /tmp/veramove-confirm.json
   ```

3. Create exactly three deterministic initial vendor calls from the same locked facts.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/calls" \
     -o /tmp/veramove-calls.json
   ```

4. Negotiate using verified competing evidence.

   ```bash
   curl -fsS -X POST "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/negotiate" \
     -o /tmp/veramove-negotiate.json
   ```

5. Read the ranked, evidence-backed report.

   ```bash
   curl -fsS "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/report" \
     -o /tmp/veramove-report.json
   ```

6. Read the provider-neutral event stream.

   ```bash
   curl -fsS "$VM_API_BASE_URL/api/jobs/$VM_JOB_ID/events" \
     -o /tmp/veramove-events.json
   ```

Verify the smoke artifacts:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

def load(name):
    return json.loads(Path(f"/tmp/veramove-{name}.json").read_text(encoding="utf-8"))

confirmed = load("confirm")
called = load("calls")
completed = load("negotiate")
report = load("report")
events = load("events")

assert confirmed["job_spec"]["confirmed"] is True
assert len(called["calls"]) == 3
assert {call["outcome"]["quote"]["job_spec_version"] for call in called["calls"]} == {"1.0"}
assert completed["state"] == "completed"
assert len(completed["quotes"]) == 4
assert report["rankings"][0]["evidence_ids"]
assert all(item["recording_url"] for item in report["transcript_evidence"])
assert isinstance(events["events"], list)
print("Mock backend voice smoke passed.")
PY
```

Repeated confirmation and call-batch requests are safe: each returns the existing aggregate without
duplicating calls or quotes. Negotiation is also idempotent after completion. All demo jobs, vendors,
quotes, evidence, recordings, and document text in this procedure are synthetic.

## Durable provider rollout on Render

Keep `LIVE_CALLS_ENABLED=false` while provisioning. Enter keys only in Render environment controls,
never in source, a populated `.env`, chat, screenshots, shell history, or logs.

1. In Supabase SQL Editor, apply these migrations in order:

   1. `supabase/migrations/202607180001_initial_schema.sql`
   2. `supabase/migrations/202607190002_live_persistence_hardening.sql`
   3. `supabase/migrations/202607190003_live_voice_materialization.sql`
   4. `supabase/migrations/202607190004_atomic_voice_intake.sql`
   5. `supabase/migrations/202607190005_browser_voice_intake.sql`
   6. `supabase/migrations/202607210006_vendor_research.sql`
   7. `supabase/migrations/202607210007_resumable_intake_vendor_calls.sql`

   Set `SUPABASE_URL`, backend-only `SUPABASE_SECRET_KEY`, and `SUPABASE_ENABLED=true` in Render.
   A live three-call run is disabled without durable Supabase. Create an obviously synthetic record,
   redeploy once, and prove it survives. Never run repository-reset test fixtures against this
   project.
2. Optionally enable Tavily with `TAVILY_ENABLED=true`. It may return vendor discovery provenance,
   official-site contact candidates, and published pricing/fee leads. Those leads remain unverified
   and never count as quote evidence. A human still selects exactly three vendors and records each
   recipient's separate permission.
3. Optionally enable OpenAI with `OPENAI_ENABLED=true`. It may extract a document `JobSpecV1` and
   narrate an already-grounded recommendation. It may not overwrite voice evidence, select an
   unsupported winner, or confirm a job.
4. Set `PUBLIC_API_BASE_URL` to the Render HTTPS origin. Set all values documented in
   `.env.example`, including `ELEVENLABS_INTAKE_AGENT_ID`, `ELEVENLABS_OUTBOUND_AGENT_ID`,
   `ELEVENLABS_PHONE_NUMBER_ID`, signing secrets, `AGENT_CONFIG_VERSION`, and exactly three unique
   E.164 values in `LIVE_TEST_TO_NUMBERS`. Twilio credentials stay in the provider dashboard and are
   not sent by VeraMove.

For official-business calling, also create a new random `VENDOR_CONTACT_HASH_SECRET` of at least 32
bytes and keep `REAL_VENDOR_CALLS_ENABLED=false`. Do not reuse another signing secret. The backend
uses this value to bind reviewed contacts and store do-not-call suppressions without exposing raw
numbers. `VENDOR_CONSENT_MAX_AGE_DAYS` defaults to 30.

Leave `APP_MODE=mock` and `LIVE_CALLS_ENABLED=false` until every dashboard and preflight item below
passes.

## ElevenLabs dashboard configuration

Use the generated assets and [`agents/elevenlabs-dashboard-checklist.md`](../agents/elevenlabs-dashboard-checklist.md).
Do not improvise provider fields.

1. Configure exactly two agents, **VeraMove Intake** and **VeraMove Outbound Negotiator**. Copy the
   reviewed prompts, generated Data Collection definitions, first messages, dynamic variables, and
   success evaluations. The outbound agent handles both `call_mode=quote` and
   `call_mode=negotiation`.
2. Save both reviewed configurations with version description `VeraMove 2026-07-21.2`. Capture the
   provider's opaque `version_id` and `branch_id` in a secure release log, not in the repository.
   Attach no provider tools until reviewed ElevenLabs tool IDs exist.
3. Enable **Audio Saving** on both agents and set the same 1–7 day nonzero retention. VeraMove
   proxies audio on demand; keep workspace `send_audio=false`. If outbound requests enable Twilio
   recording, review Twilio retention/deletion separately because the ElevenLabs agent policy does
   not govern Twilio's copy.
4. Create an ElevenLabs workspace secret whose value matches Render's
   `ELEVENLABS_PRECALL_SECRET`. Configure the workspace conversation-initiation URL as
   `https://<service-host>/api/webhooks/elevenlabs/pre-call` and set
   `X-VeraMove-Precall-Secret` to a `{secret_id: ...}` locator. Enable conversation-initiation data
   from webhook for Intake only, and keep prompt override disabled.
5. Configure one enabled HMAC post-call webhook at
   `https://<service-host>/api/webhooks/elevenlabs`. Attach workspace events `transcript` and
   `call_initiation_failure`, JSON transcript format, and `send_audio=false`. Enable post-call transcription retries
   manually; the provider's webhook-list response does not currently expose retry state. The API
   acknowledges success only after a durable receipt/materialization decision.
6. Assign the imported Twilio phone number to Intake for inbound calls. Keep the same
   `ELEVENLABS_PHONE_NUMBER_ID` in Render for outbound call initiation with the shared Outbound
   agent; do not reassign the inbound number to Outbound.
7. Verify workspace credits, concurrency, and daily call limits. Configure explicit per-agent
   concurrency of at least one and a daily limit of at least three so preflight does not rely on an
   inherited/unobservable limit. Capacity of one is supported by sequential dispatch; capacity of
   three allows parallel dispatch. This is called a **three-call run**.
   This is not ElevenLabs Batch Calling.

## Redacted preflight

After deploying the intended commit, set `APP_MODE=live`, `SUPABASE_ENABLED=true`, and
`LIVE_CALLS_ENABLED=true`, then run from a secure operator shell:

```bash
.venv/bin/python scripts/live_voice_preflight.py --check-only
```

Preflight does not place a call. It checks complete fail-closed configuration, both agent identities
and current provider versions, prompt placeholders, Intake-only pre-call enablement, the workspace
secret locator, post-call events and enabled HMAC webhook, inbound phone assignment, Audio Saving,
short retention, provider credits, capacity, Supabase connectivity, and the public signed-webhook
guard. Output contains only booleans, counts, and one-way redacted identifiers. Because the documented
webhook-list API does not expose `retry_enabled`, the dashboard checklist remains the required retry
verification. A false category blocks the smoke and full run.

Confirm all three consenting destination owners are teammates, available now, and prepared to play
the three fictional vendors. Do not paste or print their numbers. Re-run preflight after any agent,
secret, deployment, or dashboard change.

For official-business readiness, keep `REAL_VENDOR_CALLS_ENABLED=false` during this check. Verify
the new Outbound prompt variables and `recipient_opt_out` data-collection field against
`agents/elevenlabs-dashboard-checklist.md`. Do not dial any public business as a configuration test.

## Manual-only one-call provider smoke

Do not run the live smoke test from CI. The smoke is a direct provider check for destination slot
zero; it does not create a job, canonical batch, quote, state transition, or report. Reconfirm slot
zero consent immediately before running:

```bash
.venv/bin/python scripts/live_voice_smoke.py --confirm-supervised-one-call
```

The command performs the same fail-closed preflight, supplies a locked synthetic fixture and
fictional vendor, invokes only slot zero, and prints only redacted correlation/provider status. If
the request response is ambiguous, do not retry until the provider dashboard proves no conversation
was accepted.

## Supervised intake, three-call run, negotiation, and report

Only after the one-call smoke succeeds:

1. Call the imported Twilio number and complete one fictional Intake conversation. Confirm AI and
   recording disclosure, explicit consent, complete readback, and that the agent does not lock the
   job.
   Alternatively, open the deployed frontend in Live Mode, start the browser voice interview,
   allow microphone access, and complete the same fictional intake through WebRTC. This requires
   authenticated client access on the reviewed Intake agent and uses a single-use server-issued
   conversation token; no provider key is exposed to the browser.
2. Verify the intake-session API shows one unconfirmed voice `JobSpecV1`. Correct any missing field
   through the supported workflow, then explicitly confirm it to lock version `1.0`.
3. Reconfirm all three role-play participants, then invoke the canonical calls route once. Verify
   exactly three attempts, stable slots 0–2, one shared outbound agent, and the same locked JobSpec
   hash/version. One failed initiation must not cancel the other two.
4. Let signed post-call transcription webhooks materialize three supported terminal outcomes. At
   least two itemized quotes must contain per-claim timestamp evidence and a playable VeraMove
   recording URL before negotiation is eligible.
5. Start negotiation once. Verify the target receives only backend-selected verified leverage and
   that the final quote improves price, deposit, binding status, or a configured concession.
6. Open the canonical report and verify the ranking cites evidence excerpts, timestamps, and
   recording proxy URLs. Demonstrate safe OpenAI usage counts, Tavily provenance, and persistence
   only if those optional integrations are enabled.

## Interrupted intake recovery

If a caller ends the browser interview before the final readback, wait for the signed terminal
provider event. The session must become **incomplete**, not remain indefinitely in processing. The
browser then offers three explicit choices:

1. **Continue speaking** creates a new provider conversation with the existing structured facts and
   asks only for missing fields.
2. **Finish manually** creates an editable, unconfirmed draft and opens the confirmation screen.
3. **Start over** reserves a separate blank session and does not mutate the interrupted one.

No option reuses a provider conversation ID, persists a transcript, or locks a JobSpec. If the
provider has not delivered a terminal event yet, the UI may show delayed processing and a manual
check action; it must not invent a partial draft.

## Official-business three-call release gate

The frontend displays official-site contacts but accepts no arbitrary phone input. Before the
canonical calls route can dispatch, an operator must select one server-issued contact for each of
the three shortlisted vendors and record all of the following without preselected checkboxes:

- recipient timezone and current opt-in time;
- how direct permission was obtained and a non-secret consent-record reference;
- affirmative consent to an AI-generated call;
- affirmative consent to recording and ElevenLabs processing;
- one final acknowledgement that exactly three calls will start with the locked JobSpec.

The backend re-resolves every contact, validates the same JobSpec version/hash, checks consent age,
local calling window, and hash-only suppression, persists all three attempts before the first
provider request, and fails closed if any member of the batch is invalid. Website claims influence
the targeted question plan but remain unverified until the recipient confirms them on the recorded
call. A stop request ends the call and creates a suppression record.

Only after migration, deployment, agent synchronization, check-only preflight, and a human review of
all three current authorizations may an operator set `REAL_VENDOR_CALLS_ENABLED=true`. Enabling the
flag does not dial; the separate frontend Start action does. Keep it `false` for normal development,
CI, deployment verification, and any demo that lacks real recipient consent.

## Webhook retry, recording, and repair

- Provider webhook retries are expected and safe. Do not redial after a provider reference exists;
  repeat delivery or use repair.
- If a completion webhook was missed, use the operator-authorized conversation **repair** route from
  the generated OpenAPI. It may reconcile only a stored conversation that is `done` with analysis or
  provider `failed`; partial conversations remain pending. Repair is idempotent.
- Recording URLs are signed VeraMove capabilities. They resolve only a canonical stored call and
  stream supported audio server-side. Expired/deleted provider audio returns a safe unavailable
  response. Never copy audio bytes, raw transcripts, provider URLs, or API keys into the repository.

## Rollback and secret cleanup

If any mandatory check fails, stop before dialing. In Render, set
`REAL_VENDOR_CALLS_ENABLED=false` first, then `LIVE_CALLS_ENABLED=false`; restore `APP_MODE=mock` and
redeploy if voice must be disabled completely. Optional OpenAI/Tavily/Supabase switches can be
disabled independently. Mock mode remains credential-free and must never silently fall through to
a live adapter.

Unset any shell-only values after the supervised session:

```bash
unset APP_MODE LIVE_CALLS_ENABLED ELEVENLABS_API_KEY ELEVENLABS_INTAKE_AGENT_ID
unset ELEVENLABS_OUTBOUND_AGENT_ID ELEVENLABS_PHONE_NUMBER_ID ELEVENLABS_WEBHOOK_SECRET
unset ELEVENLABS_PRECALL_SECRET LIVE_TEST_TO_NUMBERS PUBLIC_API_BASE_URL
unset RECORDING_SIGNING_SECRET VOICE_OPERATOR_SECRET AGENT_CONFIG_VERSION
unset REAL_VENDOR_CALLS_ENABLED VENDOR_CONTACT_HASH_SECRET VENDOR_CONSENT_MAX_AGE_DAYS
unset SUPABASE_ENABLED SUPABASE_URL SUPABASE_SECRET_KEY
```

## Code-freeze and release gates

No release tag before code freeze. A backend/voice handoff is ready only after:

1. `python scripts/check.py` passes Ruff, pytest, OpenAPI export, API type generation, frontend
   typecheck/tests, and the production build.
2. OpenAPI export and frontend generation leave committed artifacts unchanged.
3. The deterministic mock smoke, redacted check-only preflight with fakes, and agent-asset drift
   checks pass without any automated call.
4. The three owners review their boundaries; all recorded submission claims are verified.
5. A human explicitly authorizes the one-call smoke and, separately, the full live sequence.
6. The team resolves known limitations and declares code freeze. Merge, tag, release, and live calls
   remain separate external actions.
