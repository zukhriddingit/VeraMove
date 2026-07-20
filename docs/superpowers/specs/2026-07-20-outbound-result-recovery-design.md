# Outbound Result Recovery Design

## Objective

Make every completed ElevenLabs outbound attempt materialize into one canonical VeraMove call
outcome so the Calls screen shows the answered quote and missed-call results without requiring a
redial. Preserve VeraMove's evidence, consent, correlation, and locked-JobSpec guarantees.

## Confirmed Failure

ElevenLabs delivered all three post-call results for the live job, but the API returned HTTP 409 for
each webhook. Two non-quote outcomes contained harmless quote-field defaults, and one answered quote
contained a fee item that did not exactly match `FeeLineItem`. Because materialization failed before
persistence, the job remained in `calling` with an empty canonical `calls` array.

## Chosen Approach

Normalize only the untrusted ElevenLabs data-collection payload at the outbound materializer
boundary. Do not weaken Pydantic contracts, change the outcome enum, or synthesize frontend results.

- For `itemized_quote`, accept only quote details and continue to reject conflicting callback or
  failure details.
- For `callback_commitment`, `documented_decline`, and `failed`, ignore provider-populated quote
  defaults because they cannot affect the selected canonical outcome. Continue to reject a
  conflicting callback/reason field.
- Normalize fee objects into `FeeLineItem` inputs using bounded, deterministic rules. Preserve
  supplied monetary values, represent absent amounts as `unknown`, and map an unrecognized category
  to `other` without inventing a fee amount.
- Reject structurally unsafe JSON, negative or non-finite money, excessive list sizes, invalid
  callback timestamps, missing supported reasons, correlation mismatches, and unsupported outcomes.
- Keep quote evidence verification unchanged. A quote is only verified when its transcript supports
  its fee and total claims, and recording audio is only exposed after consent.

## Data Flow

1. The authenticated ElevenLabs webhook or operator repair snapshot enters the existing voice
   materializer.
2. Correlation checks bind the provider event to the expected call, job, vendor, locked JobSpec hash,
   agent configuration, and call mode.
3. Provider-boundary normalization selects the declared outcome and sanitizes only fields relevant
   to that outcome.
4. Existing canonical models and quote verification validate the normalized result.
5. The repository persists one replay-stable call record. When all three attempts have terminal
   outcomes, the job advances and the existing frontend polling renders the call cards.

## Existing-Call Recovery

After deploying the materializer fix, use the existing operator-authorized repair path to replay the
three stored ElevenLabs conversations. Repair must use the saved attempt correlation and provider
conversation identifiers; it must not place new phone calls. Idempotency prevents duplicate call
records if a webhook or repair is replayed.

## Testing and Acceptance

- Regression tests cover non-quote results containing quote-field defaults.
- Regression tests cover safely normalizable fee payloads and rejection of unsafe monetary values.
- Existing mixed-outcome, consent, correlation, evidence, and mock-mode tests remain green.
- `python scripts/check.py` passes in full.
- The live job returns exactly three canonical calls after repair.
- The Calls screen shows the answered quote outcome and the missed/no-answer outcome(s), then allows
  the workflow to continue without redialing.

## Scope Boundaries

No frontend redesign, canonical contract relaxation, provider secret exposure, real PII, or change to
the rule that exactly three vendors receive the identical locked `JobSpecV1` is included.
