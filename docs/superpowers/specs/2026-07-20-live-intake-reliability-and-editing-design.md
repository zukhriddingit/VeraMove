# Live intake reliability and editable confirmation design

## Outcome

A fresh live ElevenLabs interview must finish without operator repair, open the real confirmation
page, allow every visible review editor to change the unconfirmed canonical `JobSpecV1`, and lock
that edited spec before vendor calls. Demo mode and credential-free mock mode must keep working.

## Confirmed failures

- ElevenLabs returns the same 24 data-collection results in both map and list representations. The
  webhook parser counts 48 entries and rejects the payload even though there are only 24 unique
  identifiers.
- ElevenLabs can encode inventory as `{ "item": ..., "quantity": ... }`, while `InventoryItem`
  requires `name`, `quantity`, and `room`.
- Natural extraction can return a dwelling phrase such as `two-bedroom apartment`, while the
  canonical contract accepts a bounded enum such as `apartment`.
- The imported confirmation UI edits only a local `JobView`. Live mode deliberately skips the
  update mutation because the API has no unconfirmed-job update operation.
- Missing-field state is copied from the initial response and is not consistently cleared when a
  user supplies a value. Some fields are treated as required even though no corresponding editor
  exists.
- Formatting a date-only value through `new Date("YYYY-MM-DD")` shifts it one day earlier in US
  time zones.

## Approaches considered

### 1. Update only the ElevenLabs prompt

This is useful defense in depth but not sufficient. Provider extraction remains probabilistic,
existing completed conversations retain the old shape, and ElevenLabs may continue returning both
official data-collection representations.

### 2. Normalize at the provider boundary and add a canonical draft-update API (recommended)

Keep `JobSpecV1` strict. Normalize only known ElevenLabs variations before materialization, improve
the agent extraction instructions, and add one typed API operation that replaces an unconfirmed
JobSpec before confirmation. The frontend continues to use generated OpenAPI types and one client.

### 3. Loosen canonical contracts or keep frontend-only edits

This would hide provider errors inside the domain model or show edits that vendor calls never
receive. It violates the single-contract and locked-spec requirements and is rejected.

## Backend design

### Provider normalization

- Count unique data-collection identifiers across map and list representations. Identical
  duplicates are accepted; conflicting duplicate values remain rejected.
- Preserve the existing maximum of 40 unique identifiers.
- During intake materialization only, accept `item` as a legacy alias for `name`, remove the alias,
  and default an omitted room to `Unspecified`. Canonical inventory payloads remain unchanged.
- Normalize an allowlisted dwelling phrase only when it contains one unambiguous known dwelling
  token (`apartment`, `condo`/`condominium`, `townhouse`/`townhome`, `house`, or `storage unit`).
  Unknown or ambiguous non-null values remain errors.

### Draft update operation

Add `PUT /api/jobs/{job_id}` with a generated `JobSpecV1` request and `JobRecord` response.

The service accepts the replacement only when:

- the job exists and is in `intake_complete`;
- the current and replacement specs are unconfirmed;
- no call has started;
- `job_id`, version, intake source, source context, and data classification are unchanged.

The repository preserves `created_at`, updates `updated_at`, and saves the replacement atomically.
Confirmation remains a separate operation and locks the saved version before any call.

## Frontend design

- The live API client exposes the generated `PUT /api/jobs/{job_id}` operation.
- The adapter fetches the current canonical record, applies the editable `JobView` fields without
  discarding unexposed canonical values, and sends a full generated `JobSpecV1` replacement.
- Clicking an editor changes the review draft and marks the precise corresponding review key as
  edited. Cancel must restore that editor's prior value; Save changes keeps the draft value.
- Missing-field state is recomputed from visible, editable requirements. Home type and access fields
  clear immediately after valid edits. Hidden values such as destination parking distance cannot
  block confirmation.
- On confirmation, both demo and live modes persist the draft first. Confirmation is attempted only
  after persistence succeeds; errors leave the spec unlocked and visible.
- Date-only values are formatted from their numeric year/month/day parts rather than parsed as UTC.

## Agent configuration

- Update the intake data-collection descriptions to require canonical dwelling enum values.
- Define `inventory_json` explicitly as a JSON list containing `name`, `quantity`, and `room`, with
  `room` set to `Unspecified` when the caller does not provide one.
- Make the prompt ask for origin and destination dwelling/access facts that the confirmation UI
  expects, while still allowing an explicit unknown instead of inventing a value.
- Increment `agent_config_version`; the repository assets remain the reviewed source of truth and
  the ElevenLabs dashboard is synchronized after the code deploy.

## Error handling and safety

- Do not log provider bodies, transcripts, API keys, HMAC secrets, phone numbers, or addresses.
- Invalid or conflicting provider facts fail closed with the existing typed errors.
- Updating a locked or active job returns `409` and never changes canonical state.
- A failed update never proceeds to confirmation or calling.
- `APP_MODE=mock` remains credential-free and Supabase-independent.

## Verification

- Regression payload tests cover both ElevenLabs collection representations, conflicting
  duplicates, legacy inventory keys, missing rooms, dwelling phrases, and the 40-unique-field cap.
- API tests cover successful unconfirmed replacement plus job-ID, immutable-field, confirmed-state,
  and calling-state rejection.
- Frontend tests cover live edit persistence, missing-field clearing, Cancel/Save behavior, and
  date-only formatting in `America/New_York`.
- Run `python scripts/check.py`, then deploy and complete a brand-new browser voice interview from
  intake through confirmation without manual webhook replay.

