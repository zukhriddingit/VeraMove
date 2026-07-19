# VeraMove Two-Agent Live Voice Design

**Date:** 2026-07-19  
**Status:** Direction approved; written-spec review pending  
**Scope:** Professional intake and outbound voice agents, exactly-three controlled role-play calls,
signed post-call canonicalization, recording evidence, and live-demo observability.

## Goal

Turn the existing controlled ElevenLabs smoke test into the complete VeraMove voice demonstration:

1. one customer-facing Intake Agent produces an unconfirmed `JobSpecV1`;
2. customer confirmation locks that exact JobSpec version;
3. one Outbound Negotiator calls exactly three consenting role-play vendors with identical facts;
4. signed post-call results become canonical calls, quotes, transcript evidence, and recording links;
5. the same outbound agent performs one evidence-gated negotiation; and
6. VeraMove returns a ranked, evidence-backed recommendation.

The design must preserve credential-free `APP_MODE=mock`, fail-closed live activation, no committed
secrets or real PII, and FastAPI-generated OpenAPI as the public contract.

## Demo Truth Boundary

The three destination numbers belong to consenting teammates. They represent fictional or explicitly
role-play vendors. A live role-play call proves the telephony, extraction, verification, persistence,
negotiation, and reporting workflow; it is not evidence about a real moving company.

The customer side of the supervised demo also uses a fictional name, reserved/example addresses,
synthetic inventory, and no real moving record. The resulting intake session and JobSpec use
`data_classification=role_play`. Accidental provider phone metadata is dropped, and a participant is
instructed not to speak a real address or phone number.

Every call starts with immediate AI and recording disclosure. The agent stops or records a supported
non-quote outcome if the participant declines, asks to stop, or does not consent. The JobSpec,
vendors, quotes, and evidence use `data_classification=role_play`; call classification derives from
those canonical records. Phone numbers never enter domain contracts, fixtures, logs, API responses,
persisted transcripts, or committed configuration.

## Current Gap

The repository already contains conceptual intake and negotiator assets, a live ElevenLabs outbound
adapter, HMAC verification, pending `CallAttempt` persistence, and canonical quote/evidence contracts.
The remaining gap is architectural rather than a provider limitation:

- the deployed dashboard has one generic test agent instead of the two VeraMove roles;
- live configuration requires separate quote and negotiator IDs and one destination number;
- the live provider intentionally allows only one initial call;
- inbound intake has no runtime correlation path;
- the webhook keeps only status fields and discards structured analysis and transcript evidence;
- asynchronous live completions cannot advance the job to `quotes_ready` or `completed`; and
- no VeraMove route securely proxies ElevenLabs conversation audio.

## Approaches Considered

### Structured Data Collection plus signed canonicalizer — selected

Configure primitive ElevenLabs Data Collection fields, receive them in the signed
`post_call_transcription` webhook, validate them deterministically, and use timestamped transcript
turns as evidence. This minimizes latency and OpenAI cost while keeping VeraMove contracts in control.

Data Collection is LLM-generated and therefore never trusted by itself. A collected value is a
proposed fact until Pydantic validation, arithmetic checks, call ownership checks, locked-version
checks, and transcript-evidence checks succeed.

### Raw transcript through OpenAI

Send every transcript to OpenAI for a second extraction pass. This is flexible but adds cost,
latency, another probabilistic interpretation layer, and more transcript exposure. It remains a
future fallback for incomplete provider analysis, not the primary demo path.

### Real-time agent tools

Let the voice agent call VeraMove tools during the conversation. This can provide immediate state,
but creates partial-write and authentication failure modes while the call is still active. It is not
required to prove the hackathon workflow and is deferred.

## Agent Architecture

Exactly two ElevenLabs agents exist in the final configuration.

### VeraMove Intake Agent

The Intake Agent handles customer conversation. It:

- immediately identifies itself as an AI assistant and discloses recording and provider processing;
- requests consent before collecting substantive information;
- asks only questions defined by `configs/moving.yaml`;
- collects every required JobSpec field and follows up only on missing or ambiguous values;
- preserves unknowns instead of inferring inventory, access, services, coverage, or dates;
- reads the complete structured move summary back to the customer;
- records whether the customer agrees the summary is accurate;
- produces only an unconfirmed `JobSpecV1` with `intake_source=voice`; and
- never confirms the job, locks a version, calls vendors, books, pays, signs, or negotiates.

The imported Twilio number may assign this agent as its default inbound handler. For inbound calls,
ElevenLabs' conversation-initiation webhook calls a VeraMove pre-call endpoint. That endpoint verifies
a dedicated header secret, validates `agent_id` and `call_sid`, idempotently creates a separate
`IntakeSession`, and returns `job_id`, `intake_session_id`, and `agent_config_version` as dynamic
variables. The Intake Agent defines only those three custom dynamic variables, so the response
contains every required variable. The endpoint has a short bounded timeout and does not store
`caller_id` or `called_number`.

`IntakeSession` is internal provider-correlation state, not an incomplete `JobRecord`. It contains an
opaque session ID, reserved job ID, hashed/idempotent provider call key, expected agent ID, repository
agent-config version, safe status, conversation ID when known, and timestamps. The post-call handler
atomically creates the normal `JobRecord(state=intake_complete)` after it validates `JobSpecV1`.
Repeated pre-call requests for the same provider call return the same session and job IDs.

`POST /api/intake/sessions` creates the equivalent web session and returns its IDs. A mandatory
`GET /api/intake/sessions/{session_id}` response exposes safe status and the resulting job ID/JobSpec,
and `GET /api/intake/conversations/{conversation_id}` resolves the same session for supervised inbound
demo operation. The agent never speaks a UUID. Frontend rendering is outside this design, but the
typed backend retrieval contract is not optional.

### VeraMove Outbound Negotiator

One Outbound Negotiator performs both phases under a required dynamic `call_mode`:

- `quote`: request a complete itemized quote using the immutable locked JobSpec;
- `negotiation`: request a measurable price or term improvement using only a verified competing
  quote supplied by VeraMove.

For both modes the agent:

- immediately gives AI and recording disclosure and honors stop/opt-out requests;
- states it is assisting with a synthetic role-play moving request;
- uses the supplied facts without adding, omitting, or changing move details;
- asks about all configured fee categories, total, deposit, binding status, and availability;
- never invents a price, competitor, policy, concession, transcript, or recording;
- never claims authority to book, accept, pay, or sign; and
- ends with exactly one supported outcome: `itemized_quote`, `callback_commitment`,
  `documented_decline`, or `failed`.

In negotiation mode, the prompt exposes only the verified competitor quote ID, eligible leverage
total, evidence references, and deterministic improvement objective. The agent cannot select or alter
the competitor. A claimed negotiation win is accepted only if canonical validation proves a lower
price or an explicitly measurable improved term.

## Structured Analysis Schemas

ElevenLabs Data Collection supports primitive string, boolean, integer, and number values. The
adapter accepts the provider's map or list result representation, extracts each entry's `value`, and
treats missing, null, empty, incorrectly typed, or duplicate identifiers as incomplete. Unknown
identifiers are ignored rather than persisted.

### Intake collection

The intake agent stays within the ordinary 25-item limit:

| Identifier | Type | Canonical destination |
| --- | --- | --- |
| `recording_consent` | boolean | intake safety gate |
| `summary_confirmed` | boolean | intake completeness metadata, not JobSpec lock |
| `move_date` | string | `JobSpecV1.move_date` ISO date |
| `date_flexible` | boolean | `JobSpecV1.date_flexible` |
| `origin_address_summary` | string | origin summary |
| `origin_dwelling_type` | string | origin dwelling enum |
| `origin_floors` | integer | origin access |
| `origin_stairs` | integer | origin access |
| `origin_elevator_access` | boolean | origin access |
| `origin_parking_distance_feet` | integer | origin access |
| `destination_address_summary` | string | destination summary |
| `destination_dwelling_type` | string | destination dwelling enum |
| `destination_floors` | integer | destination access |
| `destination_stairs` | integer | destination access |
| `destination_elevator_access` | boolean | destination access |
| `destination_parking_distance_feet` | integer | destination access |
| `bedroom_count` | integer | bedroom count |
| `inventory_json` | string | validated `InventoryItem[]` JSON |
| `special_items_json` | string | validated string-list JSON |
| `packing` | boolean | services |
| `disassembly` | boolean | services |
| `storage` | boolean | services |
| `storage_days` | integer | services, conditional |
| `insurance_preference` | string | coverage preference |

The webhook constructs a fresh or correlated `JobSpecV1`, computes the authoritative missing-field
list, and stores it unconfirmed. `summary_confirmed` means the caller approved the readback; it never
sets `confirmed=true` or `locked_version`.

### Outbound collection

The outbound agent collects:

- `recording_consent` as boolean;
- `outcome_type` as the exact supported enum string;
- `callback_at` as an ISO datetime string when applicable;
- `outcome_reason` as a bounded string for decline/failure;
- `headline_total`, `deposit`, `original_total`, and `negotiated_total` as numbers;
- `binding_type` and `availability_status` as exact enum strings;
- `availability` as a bounded string;
- `fee_items_json` as a validated list of category, description, amount/status, rate, units,
  disclosure, and mandatory values;
- `addressed_fee_categories_json` as a validated enum list; and
- `concessions_json` as a validated string-list JSON.

This uses 14 primitive Data Collection items and stays below the ordinary provider limit. The JSON
strings are untrusted transport envelopes, not nested provider contracts; VeraMove applies size
limits, strict JSON parsing, Pydantic validation, configured fee-enum checks, arithmetic checks, and
transcript support. Fee categories are defined centrally from `configs/moving.yaml`; the agent YAML
and backend adapter cannot maintain a second divergent list. Unknown amounts remain unknown rather
than zero. Deposit is not double-counted when it also appears as a fee line. Quote totals and fee
arithmetic are normalized by the existing intelligence layer.

## Runtime Data Flow

### 1. Voice intake

1. The customer calls the imported Twilio number or starts the configured intake conversation.
2. The pre-call/session boundary assigns a VeraMove `job_id` without persisting phone metadata.
3. The Intake Agent discloses AI/recording use, obtains consent, gathers facts, and reads them back.
4. ElevenLabs completes its post-call analysis.
5. VeraMove authenticates the raw webhook bytes before parsing.
6. VeraMove verifies the intake agent ID, conversation ID, `job_id`, and agent version.
7. Allowlisted collected values become an unconfirmed voice `JobSpecV1`.
8. Raw transcript and arbitrary analysis fields are discarded after bounded provenance/evidence work.

### 2. Confirmation and lock

The existing confirmation API remains the sole authority. It rejects missing required fields, sets
`confirmed_at`, and locks `locked_version="1.0"`. Neither agent nor provider analysis can perform
this transition.

### 3. Exactly three initial calls

1. A dedicated `RolePlayVendorRoster` returns three distinct fictional vendor records from synthetic
   fixtures. The call workflow never consumes the active Tavily discovery gateway. Tavily discoveries
   may be shown separately as research provenance but are never presented as the companies called.
2. It deep-copies the same confirmed JobSpec into three `CallAttempt` snapshots.
3. It assigns stable internal destination slots `0`, `1`, and `2`.
4. The live provider resolves each slot against exactly three unique secret E.164 destinations.
5. Every request uses the same outbound agent ID and `call_mode=quote`.
6. Every request includes `job_id`, `call_id`, vendor identity, locked version, and identical
   `job_spec_json` dynamic values.
7. Attempts are independently persisted; a synchronous provider rejection or a signed asynchronous
   `call_initiation_failure` becomes a canonical `failed` outcome for that slot and does not prevent
   the other two attempts. Voicemail or automated pickup is not treated as initiation failure because
   the provider considers the call connected.

The phone value is never copied into `Vendor`, `CallAttempt`, `JobEvent`, Supabase payload JSON, or
logs. A retry reuses the stored slot, and negotiation reuses the original target vendor's slot.

### 4. Signed post-call canonicalization

For `post_call_transcription`:

1. verify the HMAC and timestamp over the exact raw body;
2. accept only configured intake/outbound agent IDs and supported completed states;
3. correlate by stored conversation ID and nested dynamic `call_id`/`job_id` values;
4. cross-check call mode, vendor, job, locked version, and agent version against the attempt;
5. claim a two-phase webhook receipt lease in `processing` state;
6. parse only allowlisted Data Collection values;
7. locate timestamped transcript turns supporting each material amount, term, and outcome;
8. construct `TranscriptQuoteFacts`, then use the injected hardened `QuoteVerificationGateway` and
   `VoiceTools` write gate;
9. invoke one atomic finalize operation that writes the attempt, `CallRecord`, optional `QuoteV1`,
   evidence, aggregate transition, safe event, and `processed` receipt under the lease token; and
10. discard the full transcript, phone metadata, arbitrary analysis, summaries, and rationales.

An `itemized_quote` with structurally valid fields but insufficient evidence becomes a terminal
`PARTIALLY_VERIFIED` quote. It cannot become leverage or enter the ranking. Other collected values
without transcript support may form only their supported non-quote outcome. Duplicate delivery after
`processed` changes nothing.

The receipt claim is a compare-and-set operation: insert `processing` with a unique lease token and
expiry; reject a second unexpired claimant; allow a new lease only for an expired/failed receipt; and
require the current lease token during finalization. Deterministic invalid payloads mark the receipt
`failed` with a bounded safe code and return a non-retryable response. Transient storage/provider
failures mark it retryable and return `503`; automatic redelivery occurs only when workspace retries
are enabled, so the explicit conversation-repair path remains the guaranteed operator recovery.
Return `2xx` only after durable processing or durable duplicate acknowledgement. Malformed
authenticated payloads fail before receipt creation, and unauthenticated payloads fail before JSON
parsing.

`call_initiation_failure` has a separate signed branch. It validates `data.agent_id`,
`conversation_id`, and `failure_reason`, correlates the stored attempt, creates one canonical failed
outcome, and discards provider-specific metadata containing phone values. Busy, no-answer, and unknown
initiation failures are terminal. This branch never creates a quote or transcript evidence.

When the third initial attempt reaches a terminal canonical outcome, orchestration transitions the job
from `calling` to `quotes_ready`. Exactly three initial attempts are required even when one outcome is
callback, decline, or failure. Negotiation requires at least two eligible verified, nonfabricated,
same-version quotes from different vendors. If fewer than two exist after the three terminal attempts,
the job remains `quotes_ready` with an explicit `insufficient_verified_quotes` conflict and no
negotiation/report. VeraMove never silently redials or fabricates a replacement; the supervised demo
must start a fresh synthetic job after correcting the role-play scenario.

### 5. Negotiation and report

VeraMove selects the target and an eligible different-vendor quote with the same locked version. The
outbound agent receives `call_mode=negotiation`, reuses the target's destination slot, and receives
only verified leverage. Its webhook goes through the same canonicalizer. VeraMove rejects a result
unless price decreases or a configured measurable term improves, then builds and persists the final
recommendation using only eligible verified, nonfabricated, same-version quotes with per-material-
claim transcript support and transitions the job to `completed`.

### 6. Recording evidence and repair

ElevenLabs exposes conversation details and audio by `conversation_id`, but not a stable public audio
URL. For this synthetic-only hackathon deployment, VeraMove exposes a directly playable opaque
capability URL keyed by canonical `call_id` and an HMAC signature. The signature is generated from
the call/job identity with `RECORDING_SIGNING_SECRET`; it is not the ElevenLabs key. Rotating that
secret revokes every demo recording URL. A future real-data deployment must replace this capability
boundary with user/session authorization. The proxy:

- constant-time verifies the signed role-play capability;
- resolves only a stored provider conversation ID;
- checks provider `has_audio`;
- fetches audio server-side with the ElevenLabs key;
- streams a defensive audio content type without caching or persisting bytes; and
- returns safe not-found/unavailable errors after provider deletion or retention expiry.

Canonical `recording_url` values are built from validated `PUBLIC_API_BASE_URL` and point to this
VeraMove route. A server-side conversation-details client can also repair a missing webhook. A `done`
conversation with non-null analysis uses the normal canonicalizer; a provider `failed` conversation
can create only a canonical failed outcome. Partial `initiated`, `in-progress`, or `processing`
conversations never materialize evidence.

## Configuration

New preferred secret names:

- `ELEVENLABS_INTAKE_AGENT_ID`
- `ELEVENLABS_OUTBOUND_AGENT_ID`
- `ELEVENLABS_PHONE_NUMBER_ID`
- `ELEVENLABS_WEBHOOK_SECRET`
- `ELEVENLABS_PRECALL_SECRET`
- `LIVE_TEST_TO_NUMBERS` containing exactly three unique E.164 numbers
- `PUBLIC_API_BASE_URL` as a validated HTTPS origin
- `RECORDING_SIGNING_SECRET`
- `AGENT_CONFIG_VERSION` matching the committed/generated agent assets

For one transition release, the old quote and negotiator variables may alias the outbound ID only when
both resolve to the same value. Different legacy IDs fail closed because they would represent more
than one outbound role. The legacy `LIVE_TEST_TO_NUMBER` and one-call route behavior are removed;
there is one unambiguous production workflow and it requires exactly three destinations. A supervised
single-call smoke uses an operator-only script/provider command with explicit slot zero and cannot
advance canonical batch state.

`APP_MODE=mock` and `LIVE_CALLS_ENABLED=false` remain defaults. Live configuration is usable only
when `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, `SUPABASE_ENABLED=true`, both agent IDs, the imported
phone-number ID, both webhook secrets, recording settings, public origin, and exactly three valid
destinations are present. Local live-shaped tests may use the transactionally locked in-memory
equivalent, but the deployed three-call workflow requires durable Supabase. Optional OpenAI and
Tavily flags remain independent and never implicitly enable voice.

Before the three-call run, an operator preflight verifies the active outbound agent, agent config
version, audio saving, nonzero retention, workspace/agent concurrency, daily call limits, and provider
credits. If concurrency cannot support three simultaneous calls, VeraMove dispatches the three
individual requests sequentially without changing their facts or identities. This design does not use
ElevenLabs Batch Calling.

## API and Contract Changes

The canonical domain types remain `JobSpecV1`, `CallOutcome`, `CallRecord`, `QuoteV1`,
`TranscriptEvidence`, and `RecommendationV1`. New provider-shaped models remain internal. Existing
contract validation is tightened so:

- each `CallOutcome` forbids details belonging to another outcome type;
- `CallRecord` enforces terminal-status, completion-time, and outcome consistency;
- a non-quote call without saved audio may have no recording URL;
- a verified quote still requires transcript evidence and a real recording URL;
- quote, call, and evidence recording references must resolve to the same canonical call; and
- negotiation improvement compares the new result with the target quote and accepts only a lower
  comparable price, lower deposit, stronger binding commitment, or newly added configured concession.

Expected public API additions are:

- an authenticated ElevenLabs conversation-initiation webhook for inbound intake;
- typed intake-session creation, status, and conversation-resolution routes; and
- a signed role-play recording-audio capability route keyed by canonical call ID.

The existing post-call webhook response remains an idempotent acknowledgement. Public schema changes
are required: `CallRecord.recording_url` becomes optional for non-quote calls without audio and the new
routes add typed request/response models. Therefore the repository contract-change process is
mandatory: Pydantic and API tests, OpenAPI export, frontend type generation, typed call-site updates,
and full repository check.

`CallAttempt` gains a non-PII destination slot, immutable JobSpec version, call kind, expected agent
ID, repository agent-config version, `call_mode`, locked-snapshot hash, and negotiation context: target
quote ID, competitor quote ID, eligible leverage total, and evidence IDs. The observed provider
`version_id` is saved as audit metadata after completion; in-flight calls compare against the expected
agent/config stored at initiation rather than mutable current settings. These fields make retry,
negotiation routing, and asynchronous transitions deterministic and auditable.

The migration adds first-class `kind`, `job_spec_version`, and destination-slot columns to
`call_attempts`, then creates a unique key on `(job_id, vendor_id, kind, job_spec_version)`. No public
model gains a phone field. Call classification is derived from its role-play Vendor/JobSpec; it is not
added as a redundant `CallRecord` field.

An explicit `QuoteVerificationGateway` is injected into orchestration and implemented by the existing
`QuoteVerifier` after hardening. It requires transcript support for each material known fee, total,
binding claim, availability claim, and negotiated term. Ranking filters to eligible verified,
nonfabricated, same-version quotes instead of accepting every persisted quote.

## Persistence

Supabase persists safe intake-session correlation, destination slot, conversation/provider IDs,
canonical calls, quotes, evidence, recommendations, and replay reservations. It does not persist:

- caller or destination phone numbers;
- raw provider webhook bodies;
- full transcripts or analysis envelopes;
- Data Collection rationales;
- audio bytes; or
- OpenAI prompts, responses, or credentials.

Repository mutations remain idempotent. The same post-call event cannot create a second call, quote,
or recommendation, and incomplete transactions can be replayed through the canonicalizer. A bounded
`VoiceMaterializationRepository`/RPC client protocol exposes:

- `claim_voice_webhook_receipt` for compare-and-set lease acquisition;
- `finalize_voice_webhook` for one transaction containing safe canonical writes, aggregate revision,
  state transition, and receipt completion; and
- `fail_voice_webhook_receipt` for bounded failure state and retryability.

The application parses the transient provider envelope outside the database, then sends only typed
safe canonical values plus the lease token to `finalize_voice_webhook`. The Supabase client gains a
restricted `rpc(name, payload)` boundary that allowlists these functions; the in-memory repository
implements equivalent locking and compare-and-set semantics. Optimistic aggregate revision or
normalized-table rebuild prevents three concurrent webhooks from overwriting each other's
`jobs.payload` state.

## OpenAI, Tavily, Supabase, and Observability

OpenAI continues to power document-to-JobSpec extraction and evidence-grounded recommendation
narration. It is not required to reinterpret every voice transcript. The live adapters already passed
their smoke tests. Safe observability adds model name, provider request ID, token usage, latency, and
success/failure category; it never records document text, prompts, transcripts, secrets, or PII.

Tavily continues to provide source-backed vendor discovery and provenance. The three live role-play
calls use fictional vendor identities and are never attached to discovered real companies. Supabase
remains the durable repository. ElevenLabs owns voice execution and post-call analysis; VeraMove owns
canonical truth.

## Error Behavior

- One failed call initiation does not cancel the other two initial slots.
- Busy, no-answer, provider failure, callback, and decline map to supported terminal outcomes.
- Callback timestamps must be timezone-aware and strictly later than call completion.
- Missing or ambiguous collected values never become zero, false, or invented facts.
- A completed provider status without valid canonical evidence does not produce a verified quote.
- Out-of-order and repeated webhooks are safe.
- Provider-agent ID, job, call, vendor, version, or mode mismatches fail closed.
- Webhook responses remain fast enough to avoid provider disablement; optional repair work can run
  through an explicit retry endpoint or bounded background operation.
- Live provider errors never fall back silently to mock data.
- An initiation request may be retried only when no provider conversation/reference was accepted.
  Once a provider reference exists, retry means webhook/conversation repair, never a second dial that
  would violate the exactly-three invariant.

## Testing

### Agent assets

- exactly two professional agent configurations exist;
- both prompts contain AI/recording disclosure, role boundaries, stop behavior, and no-booking rules;
- outbound prompt has strict quote and negotiation branches;
- configured analysis identifiers stay within provider limits and mirror backend allowlists;
- a generator reads `configs/moving.yaml` and emits the outbound prompt fee fragment plus both
  committed Data Collection schema artifacts; a drift test fails if generated assets differ;
- no provider secret or real phone appears in agent assets.

### Configuration and adapter

- exactly three unique E.164 destinations are required for full live mode;
- the provider sends three distinct destinations and one shared outbound agent ID;
- the three quote requests contain equivalent locked JobSpec JSON;
- quote and negotiation carry the correct `call_mode`;
- negotiation reuses the target vendor's slot and uses comparable-total fallback correctly;
- old identical agent-ID aliases work during migration; divergent IDs fail closed;
- deployed full live mode fails closed without Supabase, public-base, signing, audio, and limit
  preflight settings;
- mock mode remains credential-free and sends no network requests.

### Webhooks and canonicalization

- HMAC verification occurs before JSON parsing;
- nested dynamic variables correlate calls and are cross-checked;
- map and list Data Collection result shapes are accepted safely;
- missing/null/wrong-type values remain incomplete;
- unknown fields, phones, full transcript, analysis, and rationales are not persisted or logged;
- material quote facts require timestamped evidence;
- all four outcomes validate and mixed outcome details are rejected;
- replay creates one canonical result, while a failed materialization remains safely retryable;
- lease expiry and compare-and-set prevent two concurrent claimants from materializing one event;
- `call_initiation_failure` produces a failed outcome without persisting provider phone metadata;
- three terminal initial outcomes advance the job to `quotes_ready`;
- three concurrent out-of-order completions cannot lose a call, quote, or state transition;
- negotiation improvement creates the report; no-op or pre-existing terms do not;
- a voice intake result creates only an unconfirmed `JobSpecV1`.

### Recording and repair

- audio is fetched only for a stored call/conversation pair;
- the provider API key never reaches responses or logs;
- missing, deleted, and wrong-content audio fail safely;
- both agents have audio saving and nonzero retention configured;
- conversation repair accepts `done` analysis or provider `failed` status and is idempotent.

### Repository gates

- focused backend and frontend contract tests pass;
- `python scripts/export_openapi.py` and frontend type generation are committed together;
- `python scripts/check.py` passes;
- `python -m evals.run` remains 14/14 or better;
- the mock create/confirm/calls/negotiate/report loop remains green;
- a supervised live synthetic call passes before the three-call run; and
- the final supervised demo proves the complete acceptance sequence below.

## Demo Acceptance Sequence

1. A customer completes a professional Intake Agent conversation.
2. VeraMove shows an unconfirmed voice `JobSpecV1` with missing fields handled honestly.
3. Explicit confirmation locks version `1.0`.
4. Exactly three consenting phones ring as three role-play vendors.
5. All attempts received identical locked facts and one shared outbound-agent configuration.
6. All three calls end in canonical supported outcomes.
7. At least two evidence-backed quotes are available.
8. VeraMove selects verified leverage and performs one negotiation call.
9. Price or a configured term improves measurably.
10. The ranked report cites evidence excerpts, timestamps, and playable VeraMove recording URLs.
11. OpenAI usage metadata, Tavily provenance, and Supabase persistence are demonstrable without
    exposing sensitive content or credentials.

## Rollout

1. Implement and test provider-neutral models and canonicalization in mock/fake transports.
2. Expand the two agent assets and document their Data Collection configuration.
3. Add configuration, exactly-three destination slots, and asynchronous state transitions.
4. Add intake pre-call correlation, recording proxy, and conversation repair.
5. Apply the Supabase migration and regenerate OpenAPI/types.
6. Run all repository gates and evals.
7. Create or configure the two ElevenLabs agents from the reviewed assets.
8. Configure signed pre-call and post-call webhooks, transcription retries, Audio Saving on both
   agents, and short nonzero retention.
9. Add secrets in Render without exposing their values.
10. Run one supervised intake, one supervised outbound quote, then the full three-call and
    negotiation demonstration.

## Ownership and Review

The implementation crosses Toheeb's orchestration/ElevenLabs/agents boundary and Zukhriuddin's
contracts/OpenAI/Supabase boundary. Changes must remain narrowly scoped, be reviewed by both owners,
and request frontend-owner review for any generated API/type changes. No unrelated subsystem rewrite
is authorized.

## Non-Goals

- Calling or impersonating real moving companies during the hackathon demo.
- Persisting real customer PII, raw transcripts, or audio files.
- Letting an agent confirm a JobSpec or book a move.
- Using OpenAI to overwrite provider-supported facts without evidence.
- Building the frontend in this workstream.
- Replacing Tavily, OpenAI, Supabase, Twilio, or ElevenLabs.

## Provider References

- [Post-call webhooks](https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks)
- [Data Collection](https://elevenlabs.io/docs/eleven-agents/customization/agent-analysis/data-collection)
- [Dynamic variables](https://elevenlabs.io/docs/eleven-agents/customization/personalization/dynamic-variables)
- [Twilio inbound personalization](https://elevenlabs.io/docs/eleven-agents/customization/personalization/twilio-personalization)
- [Conversation details](https://elevenlabs.io/docs/eleven-agents/api-reference/conversations/get)
- [Conversation audio](https://elevenlabs.io/docs/eleven-agents/api-reference/conversations/get-audio)
- [Disclosure requirement](https://elevenlabs.io/docs/eleven-agents/legal/disclosure-requirement)
