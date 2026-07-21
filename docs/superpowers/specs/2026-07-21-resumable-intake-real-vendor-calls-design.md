# Resumable Voice Intake and Consent-Gated Real Vendor Calls

**Date:** 2026-07-21  
**Status:** Approved for implementation  
**Branch:** `codex/resumable-intake-real-calls`

## Purpose

Complete the next live-workflow phase without weakening VeraMove's truth, consent, privacy, or
locking boundaries:

1. A voice interview that ends before the final summary must become an explicit, recoverable
   incomplete intake instead of polling into the misleading `Processing is delayed` state.
2. The user must be able to continue speaking from structured partial answers, finish the same
   draft manually, or start over.
3. The three selected real movers must be contactable only through official-site phone numbers
   that the user reviews and confirms, and only after documented recipient opt-in for an AI call
   and recording.
4. Every initial quote call must receive the selected vendor's bounded website-research plan so the
   agent confirms published statements once and asks from scratch only where required information
   is missing or ambiguous.

This design does not authorize an unsolicited production call during implementation or testing.
Development and production verification use only explicitly approved test destinations. Real
business dispatch remains fail-closed and requires a separate runtime feature flag plus an explicit
per-job confirmation.

## Existing invariants retained

- Voice, document, and manual completion produce the same versioned `JobSpecV1` contract.
- A `JobSpecV1` remains editable and unconfirmed until `POST /api/jobs/{job_id}/confirm` locks it.
- Exactly three initial quote attempts use the same locked version and SHA-256 snapshot.
- Website claims remain `unverified_website_claim`; they never count as quote, transcript, or
  negotiation evidence.
- Negotiation continues to require a verified competing quote from a different vendor for the same
  locked JobSpec version.
- Mock mode remains credential-free and performs no network calls.
- External SDKs stay in `services/api/app/integrations`; orchestration uses protocols.
- API keys, provider tokens, raw transcripts, recordings, real numbers, and full addresses never
  enter source control, fixtures, logs, event payloads, or call-attempt payloads.
- FastAPI OpenAPI remains the canonical browser contract.

## Non-goals

- Do not redesign the intake, confirmation, calls, negotiation, or report pages.
- Do not persist raw browser transcripts or replay them into a resumed agent.
- Do not infer phone numbers from search snippets, map listings, aggregators, social profiles, or
  third-party directories.
- Do not let the browser supply the destination used at dispatch time.
- Do not let website prices become verified quote evidence.
- Do not book, reserve, pay, sign, or accept a mover's offer.
- Do not place real-business calls as part of automated tests or deployment verification.
- Do not treat a public business phone number or the VeraMove user's checkbox as the recipient's
  affirmative opt-in to an AI-generated call.
- Do not replace the existing evidence-gated negotiation workflow.

## Approach decision

The selected approach is **structured resume plus consent-gated real calls**.

Rejected alternatives:

- Manual-only recovery is simpler but makes voice intake unnecessarily restartable rather than
  resumable.
- Replaying a raw transcript into a new agent increases data exposure, duplicates context, and lets
  probabilistic interpretation overwrite already captured facts.
- Trusting a browser-submitted number at call time permits destination substitution and bypasses the
  official-source review.
- Asking the generic fee script after website research preserves redundant calls and defeats the
  purpose of research-aware planning.

## Architecture

### 1. Intake terminal states

Extend `IntakeSessionStatus` to:

```text
pending -> in_progress -> completed
                       -> incomplete
                       -> failed
```

`incomplete` is a successful provider correlation with consent and at least one supported move fact,
but without an approved complete summary readback. It is terminal for that provider conversation,
yet it may be the source of exactly one recovery action.

The browser-only phase `finalizing` represents the bounded wait between disconnect and a terminal
server state. It is not persisted. The old `delayed` phase is removed.

### 2. Partial intake representation

Reuse `JobSpecV1` rather than introducing a handwritten partial domain model. The contract already
allows unknown required values and exposes `missing_required_fields()`.

An incomplete session stores:

- a strict, unconfirmed `JobSpecV1` with `intake_source=voice`;
- the derived missing-field list;
- no raw transcript;
- no recording URL;
- no browser transcript turns;
- a terminal reason such as `user_ended_before_summary`;
- an optional recovery action and recovery target identifier.

The partial spec is not a `JobRecord` until the user chooses **Finish manually**. This avoids
creating abandoned jobs for every interrupted conversation.

### 3. Resume lineage

`POST /api/intake/sessions/{session_id}/resume` creates one fresh intake session with a fresh
reserved job ID. It copies the source partial spec into an internal base snapshot and records
`resumed_from_session_id`. The source session atomically records `recovery_action=resume` and the
new session ID. Repeated identical requests return the same child session; a conflicting manual
finish returns HTTP 409.

The new browser credential contains these bounded dynamic variables:

- `job_id`
- `intake_session_id`
- `agent_config_version`
- `resume_mode` (`fresh` or `structured_partial`)
- `partial_job_spec_json`
- `missing_fields_json`

The intake prompt briefly confirms the carried-over facts, asks only the first unresolved question,
and eventually performs a complete readback. The backend merges newly collected values over the
immutable base snapshot; unknown or absent provider fields do not erase known values.

### 4. Manual completion

`POST /api/intake/sessions/{session_id}/finish-manually` atomically materializes the partial
`JobSpecV1` as the normal unconfirmed `JobRecord` with state `intake_complete`. The source session
records `recovery_action=manual` and the created job ID. The frontend navigates to the existing
confirmation route. Its current missing-field UI and `PUT /api/jobs/{job_id}` flow remain the only
manual editor.

### 5. Explicit intake data mode

The current browser interview is intentionally role-play-only, so it cannot ethically feed a real
vendor call. Intake-session creation therefore accepts an explicit mode:

- `supervised_role_play` remains the default and retains the current fictional-details copy.
- `real_redacted` collects only city/state route summaries and non-identifying move facts. It never
  asks for or stores a person's name, street address, apartment number, email address, or customer
  phone number.

The selected mode is immutable for the session, inherited by a resume session, supplied to the
Intake agent as `intake_data_mode`, and mapped to `JobSpecV1.data_classification`. An official-
business call rejects `role_play` and `synthetic` jobs. The frontend shows the choice before the
microphone starts and explains that real-redacted details may later be shared with the three
confirmed movers.

### 6. Provider-result repair

After a clean browser disconnect, the frontend polls for a short bounded interval. If the session
is still `in_progress`, it calls:

`POST /api/intake/sessions/{session_id}/recover`

The service resolves the already attached conversation ID, fetches the provider's completed
conversation through the existing server-side ElevenLabs conversation-detail client, and feeds the
verified normalized event through the same idempotent materializer as the webhook. The browser
never submits a conversation ID, analysis object, transcript, or collected-data map to this route.

Only one automatic recovery attempt runs per disconnect. If the provider still has no terminal
result, the UI shows **Result unavailable** with Retry and Start over. It never returns to an
unbounded spinner or the ambiguous delayed label.

### 7. Official business contact extraction

Add a dedicated contact-extraction boundary to the existing selected-site research flow. It runs
only for the exactly three selected candidate websites and only on the official candidate URL or
same-site pages reached from it.

Extraction is deterministic:

- parse `tel:` links;
- parse bounded visible phone text;
- normalize valid destinations to E.164;
- retain display formatting separately;
- retain a short exact source excerpt and source URL;
- reject unsupported country codes, malformed extensions, and numbers absent from official-site
  content;
- deduplicate by normalized number.

OpenAI does not invent, normalize, rank, or validate contact numbers. Tavily search snippets and
third-party sources are never accepted as contact evidence.

### 8. Contact review and authorization

New contract-owned models:

- `VendorContactCandidateV1`
- `VendorContactSelectionV1`
- `VendorCallAuthorizationV1`
- `VendorCallPlanV1`

Each authorization binds:

- job ID;
- locked JobSpec version and hash;
- selected candidate ID and vendor ID;
- official website host;
- normalized phone number;
- source URL and source excerpt hash;
- confirmation timestamp;
- recipient opt-in evidence type and timestamp;
- explicit permission for an AI-generated quote-request call;
- explicit permission for call recording and ElevenLabs processing;
- call context (`supervised_role_play` or `official_business`);
- generated call-plan version.

The exact destination is stored only in a service-role-only `vendor_call_authorizations` table.
Call attempts and event records reference the authorization ID and vendor ID but exclude the phone
number. The browser can review the public business number, but dispatch resolves it server-side from
the confirmed authorization.

The authorization API accepts only candidate IDs and contact IDs previously produced by server-side
official-site extraction. It never accepts an arbitrary destination number. A VeraMove user may
record that the recipient opted in and how that opt-in was obtained, but a public number, website
claim, or pre-checked box never counts as recipient consent.

### 9. Compliance dispatch gate

ElevenLabs' current outbound-calling guidance requires affirmative opt-in, consent records,
revocation handling, calling-time controls, and do-not-call handling. Official-business dispatch
therefore also requires:

- an affirmative recipient opt-in record for an AI voice call;
- an affirmative recipient opt-in record for recording and ElevenLabs processing;
- a non-expired consent timestamp and bounded evidence reference;
- the destination not appearing on VeraMove's internal suppression list;
- the call time to fall inside the configured permitted window for the destination's local time;
- no previous call outcome containing a supported opt-out or stop request.

The recipient is still asked to confirm consent immediately when the call connects and may revoke
it in any reasonable verbal form. Revocation adds the number hash to the suppression list and ends
the call. The application never enables `call_recording_enabled` for official-business mode without
the prior recording permission record. These controls follow the provider's published TCPA
guidance: <https://elevenlabs.io/docs/eleven-agents/legal/tcpa>.

### 10. Vendor-specific call plan

`VendorCallPlanV1` is produced deterministically from the dossier and locked JobSpec. It contains:

- a small set of relevant published claims to confirm once;
- one question for each applicable mandatory fee category not covered by a published claim;
- ambiguity probes for published prices missing units, mover counts, minimums, or conditions;
- required all-in total, deposit, availability, binding-status, and readback instructions;
- website source URLs for internal audit only;
- no phone number;
- no raw webpage content.

The spoken agenda is capped. It guarantees required comparable-quote coverage, then includes at
most a small number of non-fee service or licensing confirmations. Duplicate claims and low-value
marketing language are omitted. A published price is phrased as a confirmation:

> Your website lists [claim]. Does that apply to this move, and what conditions or additional fees
> apply?

A missing category is phrased as a direct request. Unknown remains unknown; it is never converted
to zero.

### 11. Outbound dispatch

`POST /api/jobs/{job_id}/calls` retains its public shape. In official-business mode it requires:

- a confirmed, locked `JobSpecV1` with `data_classification=real_redacted`;
- `REAL_VENDOR_CALLS_ENABLED=true`;
- exactly three selected research candidates;
- exactly three confirmed, distinct call authorizations for the current JobSpec hash;
- current affirmative recipient AI-call and recording opt-in records for all three destinations;
- no suppressed destination and a permitted local calling time;
- one call plan per authorization;
- a configured outbound ElevenLabs agent with the required dynamic variables.

The orchestration service first persists all three pending attempts and their authorization IDs,
then dispatches them sequentially. A synchronous provider failure materializes a canonical failed
attempt and never causes silent substitution or a call to another number. Repeating the start
request is idempotent.

Supervised role-play keeps the existing configured synthetic destination slots and never resolves
official-business contacts. Live mode cannot silently fall back from official-business to role-play
or vice versa.

### 12. ElevenLabs payload and prompt

Add bounded quote-mode dynamic variables:

- `call_context`
- `vendor_call_plan_json`
- `website_claims_json`
- `verification_questions_json`

Negotiation-mode variables remain unchanged. Quote mode uses the targeted plan instead of blindly
reading every question in `generated-fee-probes.md`; the static probe file remains the deterministic
fallback for mock/supervised-role-play calls without research.

Official-business first-message behavior:

1. Identify the caller as VeraMove's AI assistant contacting the selected mover for a quote.
2. State that the call may be recorded and processed by ElevenLabs.
3. Ask whether the recipient consents to continue.
4. Stop immediately on refusal or a request to stop.
5. Do not discuss move facts before consent.
6. Never book, accept, pay, sign, or claim authority to bind the customer.

The preflight script verifies all required dynamic variables before enabling official-business
dispatch. A stale dashboard agent therefore fails closed before any destination is dialed.

## API changes

### Intake

- `GET /api/intake/sessions/{session_id}`
  - Adds terminal `incomplete` support, partial spec, missing fields, recoverability, and recovery
    action metadata.
- `POST /api/intake/sessions/{session_id}/recover`
  - Idempotently repairs a missing post-call result from server-side provider data.
- `POST /api/intake/sessions/{session_id}/resume`
  - Creates or returns the one structured-resume child session.
- `POST /api/intake/sessions/{session_id}/finish-manually`
  - Creates or returns the one unconfirmed manual-completion job.
- `POST /api/intake/sessions/{session_id}/voice-token`
  - Adds the bounded resume context to dynamic variables.
- `POST /api/intake/sessions`
  - Accepts the explicit `supervised_role_play` or `real_redacted` intake mode.

### Vendor contacts

- `POST /api/jobs/{job_id}/vendor-research/contacts`
  - Extracts or refreshes official-site contact candidates for the selected three dossiers.
- `PUT /api/jobs/{job_id}/vendor-research/call-authorizations`
  - Confirms exactly three server-issued contact IDs, call context, and documented recipient opt-in
    metadata.
- `DELETE /api/jobs/{job_id}/vendor-research/call-authorizations`
  - Clears the current uncalled authorization set.
- `GET /api/jobs/{job_id}/vendor-research`
  - Adds contact-candidate, authorization-readiness, and call-plan summaries.

All public contract changes follow the repository's Pydantic -> OpenAPI -> TypeScript generation
process. Presentation components use the existing centralized API client and never call `fetch`
directly.

## Persistence changes

### `intake_sessions`

Add:

- `partial_job_spec jsonb`
- `missing_fields jsonb`
- `terminal_reason text`
- `recovery_action text`
- `recovery_target_id uuid`
- `resumed_from_session_id uuid`
- `base_job_spec jsonb`

Expand the status check to include `incomplete`. Database constraints enforce:

- completed sessions own one canonical job and completion timestamp;
- incomplete sessions own a strict partial spec but no job until manual completion;
- failed sessions own neither a partial spec nor a job;
- at most one recovery action per incomplete session;
- no transcript-, audio-, secret-, or phone-shaped keys in partial/base payloads.

### `vendor_call_authorizations`

Service-role-only table containing the exact business destination and official-source evidence.
Unique constraints prevent duplicate vendor or destination use within the same job/version/hash.
Rows are immutable after the first call attempt references them. Authorization changes before
dispatch clear and regenerate the corresponding call plans.

### Existing tables

- `call_attempts` gains only `vendor_call_authorization_id`; no destination number.
- `vendor_research` stores public contact candidates and call-plan summaries without secrets.
- a service-role-only suppression table stores normalized-number hashes and supported opt-out
  timestamps without exposing raw numbers in events.
- `event_log`, `jobs`, `quotes`, `calls`, and evidence rows continue rejecting phone-shaped or raw
  provider material.

All RLS remains enabled. Only `service_role` may read or mutate the exact authorization table.

## Frontend behavior

### Voice intake panel

Replace the old phase set with:

```text
ready
requesting_microphone
connecting
connected
finalizing
incomplete
completed
unavailable
failed
```

`incomplete` displays the known structured fields, missing-field count, and three actions:

- **Continue speaking**
- **Finish manually**
- **Start over**

`unavailable` displays Retry result and Start over. It never claims that processing is merely slow
after the repair path is exhausted.

Before starting a fresh interview, the panel explicitly selects **Demo role-play** or **My real
move (redacted)**. The second option explains the allowed city/state-level facts and that a locked
spec may be shared with three confirmed movers.

### Calls page

The research panel adds a contact-review step after website analysis:

- show official-site source and public business number;
- let the user choose among multiple same-site numbers;
- explain that website contact data is public but still requires confirmation;
- require exactly three checked confirmations;
- show the concise call plan for each vendor;
- require a non-prechecked record of how and when each recipient affirmatively opted in to an AI
  call and recording;
- show suppression or calling-window failures before dispatch;
- disable Start calls until the backend reports authorization readiness;
- require one final acknowledgement that the AI will call those three destinations and ask for
  quote information only.

Demo mode keeps the current role-play presentation and synthetic destination behavior.

## Error handling

- A user ending before readback is `incomplete`, not `failed`.
- Declined recording consent is a supported failed/ineligible intake outcome with a clear restart
  message.
- Provider/network failures never create a partial spec from unsupported data.
- Recovery is bounded and idempotent; a second repair cannot produce a second job.
- Resume and manual completion race through one compare-and-set recovery action.
- A role-play or synthetic JobSpec cannot authorize an official-business call.
- Invalid official-site contact content results in `contact_unavailable`; it does not use a
  third-party fallback.
- A vendor without a usable official number must be replaced before authorizing exactly three.
- Authorization for an older JobSpec hash becomes invalid after any pre-confirmation edit or version
  change.
- Provider call rejection records `failed` for that exact authorized vendor and does not substitute
  another destination.
- A stale ElevenLabs agent schema prevents dispatch before network side effects.
- Missing, expired, suppressed, or outside-window recipient consent prevents dispatch before
  network side effects.

## Security and privacy

- No provider API call is made directly from the browser.
- Browser-issued contact IDs are resolved against server-owned official-site extraction results.
- Phone numbers are never included in dynamic variables, JobSpec, events, call attempts, logs, test
  fixtures, or error messages.
- The destination enters only the server-to-ElevenLabs request.
- Partial intake stores structured facts only; raw transcript turns remain ephemeral in the current
  browser and provider retention boundary.
- Real-business calls accept only `real_redacted` city/state move facts. Full names and street
  addresses are not collected or sent.
- `REAL_VENDOR_CALLS_ENABLED=false` remains the default.
- Public contact discovery is not recipient opt-in. Official-business dispatch requires a current
  affirmative AI-call and recording permission record, suppression check, and local-time check.
- Mock mode remains independent of Supabase, Tavily, OpenAI, ElevenLabs, and Twilio credentials.

## Testing strategy

### Contracts and state machines

- Incomplete sessions require a strict partial spec and missing-field agreement.
- Completed, incomplete, and failed invariants are mutually exclusive.
- Resume and manual completion are each idempotent and mutually exclusive.
- Intake data mode is immutable and inherited by resumed sessions.
- Call authorizations bind exactly three distinct selected vendors and current JobSpec hash.
- Call plans reject phone numbers, raw webpage content, and unsupported claim classifications.

### Voice intake

- Full interview still materializes one unconfirmed complete JobSpec.
- Manual early end materializes `incomplete` instead of leaving `in_progress`.
- Continue speaking merges new values over the structured base snapshot and preserves known values.
- Finish manually creates the normal editable job with missing fields.
- Automatic repair reaches completed, incomplete, failed, or unavailable without an endless poll.
- Duplicate webhook and repair events remain exactly-once.
- No transcript appears in repository writes or API responses.

### Contact and dispatch

- Accept valid official-site `tel:` and visible-number candidates.
- Reject snippets, third-party URLs, invalid E.164 values, and absent source evidence.
- Require exactly three confirmed contact IDs.
- Reject stale, duplicate-vendor, duplicate-destination, and mismatched-host authorizations.
- Persist all three attempts before invoking the provider.
- Deliver each vendor's own bounded call plan to its own outbound payload.
- Confirm published pricing once and ask missing required categories.
- Ensure repeated dispatch is idempotent.
- Ensure provider failure never substitutes another destination.
- Reject role-play jobs, missing recipient opt-in, suppressed destinations, and outside-window
  dispatches before any provider request.
- Materialize a supported verbal opt-out into the suppression boundary.
- Ensure negotiation still ignores website claims as leverage.

### Frontend

- Render incomplete, unavailable, completed, and failed voice states accurately.
- Continue speaking and Finish manually navigate through typed API calls.
- Contact review requires exactly three and shows official source links.
- Start calls is disabled until backend authorization readiness is true.
- Demo mode remains independent from live contact authorization.
- Presentation components contain no direct `fetch` calls or duplicate domain models.

### Required repository checks

Run and pass:

```bash
python scripts/export_openapi.py
npm --prefix apps/web run generate:api
python scripts/check.py
```

The final check must include Ruff, pytest, OpenAPI freshness, TypeScript, Vitest, and the production
frontend build. Exercise the full credential-free mock create -> confirm -> calls -> negotiate ->
report loop.

## Deployment and production verification

1. Apply the additive Supabase migration before deploying code that writes the new shapes.
2. Deploy the Render API with `REAL_VENDOR_CALLS_ENABLED=false`.
3. Publish the generated Lovable frontend.
4. Verify interrupted browser intake reaches `incomplete` and both recovery actions work.
5. Update the ElevenLabs Intake agent with data-mode/resume variables and the Outbound agent with call-plan
   variables.
6. Run the preflight in check-only mode and confirm both agent schemas match.
7. Verify official contact extraction and exactly-three authorization with no dispatch.
8. Verify the outbound payload against only previously approved test destinations.
9. Enable `REAL_VENDOR_CALLS_ENABLED` only after the reviewed environment is ready and the user
   explicitly approves enabling real-business dispatch.
10. Do not place an unsolicited real-business call as part of verification.

## Acceptance criteria

The work is complete only when all of the following are proven:

- Ending an interview mid-question no longer produces `Processing is delayed`.
- The interrupted result becomes a terminal incomplete session with known and missing fields.
- Continue speaking resumes from structured partial facts without replaying a transcript.
- Finish manually opens the existing editable confirmation flow.
- Exactly three selected movers expose official-site contact choices and source evidence.
- Exactly three confirmed contact authorizations are required for official-business dispatch.
- Real-vendor intake uses explicit `real_redacted` mode and never sends role-play facts to a real
  mover.
- Every authorized real destination has current recipient opt-in for the AI call and recording,
  passes suppression checks, and is inside the permitted local calling window.
- Every initial call receives the correct vendor-specific research-aware plan.
- The agent confirms published information once and asks missing/ambiguous quote questions.
- Call attempts and evidence remain bound to one locked JobSpec version/hash.
- Website claims remain ineligible for quote or negotiation evidence.
- No phone or transcript leaks into prohibited persistence or generated artifacts.
- Mock mode and the existing demonstration remain fully functional.
- Full repository checks pass.
- The deployed API and public frontend exhibit the new behavior.
- No unapproved real-business call is placed during implementation or verification.
