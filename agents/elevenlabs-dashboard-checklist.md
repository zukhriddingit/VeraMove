# ElevenLabs two-agent dashboard checklist

Use this checklist to manually synchronize repository configuration marker `2026-07-21.2` with
ElevenLabs. The YAML files are reviewed source manifests, not provider payloads. Do not commit API
keys, webhook secrets, workspace secret IDs, agent IDs, branch/version IDs, phone-number IDs,
destination numbers, or participant data.

## Before changing the dashboard

- [ ] Keep `LIVE_CALLS_ENABLED=false` until the redacted preflight passes.
- [ ] Confirm credits and a daily call limit of at least three. Concurrency one is sufficient for
      sequential dispatch; concurrency three allows parallel dispatch.
- [ ] For the role-play fallback, confirm exactly three unique, currently consenting teammate
      destinations are stored only in Render's `LIVE_TEST_TO_NUMBERS` secret value. Official-site
      recipients instead use the application authorization flow and never this environment value.
- [ ] Use only fictional move and vendor facts.
- [ ] Audio webhook: disabled. VeraMove streams retained audio on demand and does not accept pushed
      base64 audio.

## Provider version and tools rule

- [ ] Save each reviewed agent with version description `VeraMove 2026-07-21.2`.
- [ ] After saving, record the opaque `version_id` and `branch_id` only in the secure release log;
      never paste them into repository files or chat.
- [ ] Treat `2026-07-21.2` as VeraMove's review marker, not an ElevenLabs `version_id`.
- [ ] Attach no ElevenLabs tools. `agents/tools.yaml` documents VeraMove backend boundaries only;
      leave provider `tool_ids` empty until reviewed, real provider tool IDs exist.

## Agent 1 — VeraMove Intake

- [ ] Display name: `VeraMove Intake`.
- [ ] Copy `agents/intake/prompt.md` as the system prompt.
- [ ] Use the exact first message from `agents/intake/agent.yaml`.
- [ ] Define all seven required string dynamic variables from `agents/intake/agent.yaml`, including
      `intake_data_mode`, `resume_mode`, `partial_job_spec_json`, and `missing_fields_json`; the
      prompt must visibly contain every matching `{{variable}}` placeholder.
- [ ] In Agent Security, enable
      `enable_conversation_initiation_client_data_from_webhook` for Intake only.
- [ ] Keep client prompt override disabled. The pre-call response may supply dynamic variables but
      must not replace the reviewed system prompt.
- [ ] Enable Audio Saving and set `retention_days` to an explicit value from 1 through 7.
- [ ] Set the success evaluation to the reviewed value in `agents/intake/agent.yaml`.

### Intake Data Collection

Generate the exact API object without modifying files:

```bash
.venv/bin/python scripts/generate_agent_assets.py \
  --print-elevenlabs-data-collection intake
```

Paste the printed object under `platform_settings.data_collection`, or create the same 24 fields in
the Analysis tab. Every value contains only `type` and `description`; the object key is the field
identifier. Verify `recording_consent`, `summary_confirmed`, the complete access/inventory/service
set, and `insurance_preference` against `agents/intake/data-collection.json`.

## Agent 2 — VeraMove Outbound Negotiator

- [ ] Display name: `VeraMove Outbound Negotiator`.
- [ ] Copy `agents/negotiator/prompt.md`, followed by
      `agents/negotiator/generated-fee-probes.md`, as the system prompt.
- [ ] Use the exact first message from `agents/negotiator/agent.yaml`.
- [ ] Define all 16 string dynamic variables from `agents/negotiator/agent.yaml`; give the four
      negotiation-only variables their documented empty-string defaults. The prompt must visibly
      contain every matching `{{variable}}` placeholder, including `call_context`,
      `vendor_call_plan_json`, `website_claims_json`, and `verification_questions_json`.
- [ ] Keep `enable_conversation_initiation_client_data_from_webhook=false` for Outbound. VeraMove
      supplies verified variables directly with each outbound call request.
- [ ] Enable Audio Saving and use the same explicit 1–7 day retention as Intake.
- [ ] Set the success evaluation to the reviewed value in `agents/negotiator/agent.yaml`.

### Outbound Data Collection

Generate the exact API object without modifying files:

```bash
.venv/bin/python scripts/generate_agent_assets.py \
  --print-elevenlabs-data-collection outbound
```

Paste the printed object under `platform_settings.data_collection`, or create the same 15 fields in
the Analysis tab. Verify `recipient_opt_out`, the four allowed outcome types, quote totals/terms,
fee evidence, and concessions against `agents/negotiator/data-collection.json`.

## Official-business release gate

- [ ] Keep `REAL_VENDOR_CALLS_ENABLED=false` while synchronizing and checking both agents.
- [ ] Confirm each selected recipient separately opted in to an AI call and recording; a public
      website number by itself is not consent.
- [ ] Confirm official-business calls receive a nonempty `vendor_call_plan_json` and identify
      VeraMove as an AI assistant before discussing move facts.
- [ ] Confirm a refusal or stop request sets `recipient_opt_out=true`, ends immediately, and creates
      a hash-only suppression record.
- [ ] Enable `REAL_VENDOR_CALLS_ENABLED=true` only after the redacted preflight and the application
      reports exactly three current authorizations inside their permitted local call windows.

## Authenticated workspace pre-call webhook

1. Create a workspace secret through `POST /v1/convai/secrets` using this request shape. Enter the
   value through a secure operator surface and never save the completed request:

   ```json
   {
     "type": "new",
     "name": "VeraMove pre-call",
     "value": "VALUE_FROM_RENDER_ELEVENLABS_PRECALL_SECRET"
   }
   ```

2. Put the same random value in Render as `ELEVENLABS_PRECALL_SECRET`. Keep the returned
   `secret_id` only in the provider configuration.
3. Update `PATCH /v1/convai/settings` so the workspace initiation configuration has this exact
   locator shape:

   ```json
   {
     "conversation_initiation_client_data_webhook": {
       "url": "https://YOUR_RENDER_HOST/api/webhooks/elevenlabs/pre-call",
       "request_headers": {
         "X-VeraMove-Precall-Secret": {
           "secret_id": "WORKSPACE_SECRET_ID"
         }
       }
     }
   }
   ```

4. Confirm only Intake has the per-agent webhook enablement switch on. Outbound must remain off.

## HMAC post-call webhook, events, and retries

1. Create one HMAC workspace webhook through `POST /v1/workspace/webhooks` for
   `https://YOUR_RENDER_HOST/api/webhooks/elevenlabs`. Put the one-time returned
   `webhook_secret` in Render as `ELEVENLABS_WEBHOOK_SECRET`; do not store it anywhere else.
2. Update that webhook through `PATCH /v1/workspace/webhooks/WEBHOOK_ID` with all required fields:

   ```json
   {
     "is_disabled": false,
     "name": "VeraMove post-call",
     "retry_enabled": true
   }
   ```

   Retries currently apply to post-call transcription delivery. The VeraMove receiver is
   idempotent, so a retry must never create a duplicate canonical outcome.
3. Attach the webhook through `PATCH /v1/convai/settings` using this exact product configuration:

   ```json
   {
     "webhooks": {
       "post_call_webhook_id": "WEBHOOK_ID",
       "events": ["transcript", "call_initiation_failure"],
       "transcript_format": "json",
       "send_audio": false
     }
   }
   ```

   `transcript` produces the `post_call_transcription` delivery. The initiation-failure event is
   also required so unreachable, declined, or unanswered outbound attempts can terminate safely.
4. Verify the workspace webhook list shows the attached HMAC webhook enabled and not auto-disabled.
   The current list response does not expose `retry_enabled`, so confirm retries manually in the
   webhook settings after every webhook recreation.

## One imported Twilio number, two directions

- [ ] Update the imported phone number with `agent_id` set to VeraMove Intake. This assignment
      controls inbound calls and must remain on Intake.
- [ ] Set Render `ELEVENLABS_PHONE_NUMBER_ID` to that imported phone-number ID. VeraMove reuses the
      same ID when initiating all outbound calls while explicitly selecting the Outbound agent; do
      not reassign the number to Outbound.
- [ ] Call the imported number once and confirm it reaches Intake.
- [ ] Run the separately authorized one-call smoke and confirm the same number is the outbound
      caller ID while the Outbound agent speaks.

## Recording and retention warning

- [ ] Confirm `record_voice=true` and an explicit `retention_days` from 1 through 7 on both agents.
- [ ] Keep workspace `send_audio=false`; it is independent of Audio Saving.
- [ ] Treat Twilio recording as a separate data store. If an outbound request uses
      `call_recording_enabled=true`, ElevenLabs agent retention does not prove that Twilio's copy is
      deleted. Verify Twilio recording retention/deletion separately or disable Twilio recording
      after deciding which evidence source the demo requires.

## Final release checks

- [ ] Run `.venv/bin/python scripts/generate_agent_assets.py --check`.
- [ ] Run `.venv/bin/python scripts/live_voice_preflight.py --check-only` after every agent,
      webhook, secret, phone assignment, or deployment change.
- [ ] Confirm the preflight reports only booleans, counts, and one-way hashes.
- [ ] Complete one supervised synthetic Intake call, then one separately authorized outbound smoke.
      Before either an exactly-three role-play run or official-business run, review the three
      current recipient permissions and keep the unrelated path disabled.
