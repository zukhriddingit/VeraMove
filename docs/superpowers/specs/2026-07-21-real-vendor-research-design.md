# Real Vendor Discovery and Website Research Design

**Date:** 2026-07-21  
**Status:** Approved for implementation  
**Scope:** Backend contracts, Tavily/OpenAI integrations, persistence, FastAPI routes, and the
existing Calls-page vendor-research section

## Goal

Turn VeraMove's currently separate Tavily demonstration into a durable, job-specific real-vendor
research workflow. After a move specification is confirmed, the user can discover real movers near
the locked route, select exactly three, and receive source-backed website research plus a targeted
call-verification plan.

The selected businesses are research candidates only. VeraMove does not discover or store their
phone numbers and does not call them in this implementation. Existing live calls continue to use
the three consenting fictional role-play destinations. This separation prevents role-play quotes
or behaviors from being attributed to real businesses.

## Existing State

- `TAVILY_ENABLED=true` already selects `CachedTavilyVendorDiscovery` in the deployed backend.
- `GET /api/vendors/discover` returns real Tavily-provenance candidates when origin or destination
  is supplied.
- The frontend currently calls that endpoint without either location, so the Calls-page discovery
  panel can show `Discovery unavailable right now` even though Tavily is configured.
- Tavily currently returns only title and URL. It does not retrieve website details or persist a
  job-specific shortlist.
- Live voice intentionally uses `FixtureRolePlayVendorRoster`; it never consumes real Tavily
  identities.

## Approaches Considered

### Selected: search, select, then extract

Use Tavily Search to find candidates, persist the result, let the user select exactly three, and
then call Tavily Extract only for those three stored website URLs. Normalize bounded excerpts into
typed claims and generate deterministic verification questions.

This minimizes credits and retained content, gives the user control over the shortlist, and keeps
the source of every claim reviewable.

### Rejected: extract every search result

Request raw content for all search results in the initial search. This is simpler operationally but
uses more provider credits, retrieves unnecessary content, and performs research before the user
chooses which vendors matter.

### Rejected: rely on search snippets

Generate research claims directly from result titles and snippets. This is inexpensive but too weak
for prices, minimums, inclusions, and fee claims. Snippets remain useful for discovery ranking but
cannot support the research dossier.

## Product Behavior

### Discovery

1. Discovery is available only after `JobSpecV1` is confirmed and locked.
2. VeraMove derives city and state from the locked origin and destination summaries and combines
   them with dwelling and move-service context plus a configured radius. It sends only city/state
   summaries to Tavily, never a street address. If city/state cannot be derived safely, discovery
   fails before provider activity. The browser cannot provide arbitrary search text or source URLs.
3. Tavily Search returns bounded real-company candidates with source URLs and Tavily provenance.
4. The backend removes malformed URLs and duplicate vendor IDs and persists the candidate snapshot
   against the job ID and locked JobSpec version.
5. An existing successful discovery is returned idempotently. An explicit refresh replaces it only
   when no shortlist has been saved; once three vendors are selected, refresh requires clearing the
   shortlist first.
6. Tavily failure never silently returns synthetic candidates.

### Shortlist

1. The user must select exactly three candidates from the persisted discovery snapshot.
2. The backend accepts candidate IDs, not browser-provided Vendor objects or URLs.
3. All three IDs must be distinct and present in the current job/version candidate snapshot.
4. The selected vendor snapshots are persisted and survive page refreshes and backend redeploys.
5. Changing the shortlist clears any dossiers derived from the previous selection.
6. The user may explicitly clear the shortlist and dossiers before refreshing discovery. Clearing
   research does not mutate the JobSpec or any call, quote, evidence, or recommendation.

### Website research

1. The backend passes only the three stored selected HTTPS URLs to Tavily Extract.
2. One bounded basic-depth Extract request retrieves content for the three URLs. Images are
   disabled. Each successful page is capped before it crosses the intelligence boundary.
3. Each page is normalized independently so one inaccessible or malformed site does not discard
   the other two dossiers.
4. The existing backend-only OpenAI integration converts each bounded page into strict structured
   claims. It may extract advertised rates, minimums, mover counts, service inclusions, deposits,
   insurance language, availability language, and fee-related statements. It may not infer missing
   facts or turn `starting at` language into an exact quote.
5. Only typed claims, a short exact supporting excerpt, source URL, and retrieval timestamp are
   persisted. Full extracted pages and arbitrary model output are discarded.
6. Every website claim remains permanently classified as `unverified_website_claim`. A later phone
   call can create separate transcript evidence, but it never upgrades or mutates the website
   claim into quote evidence.

### Targeted verification plan

The backend, not the model, generates the final verification questions. It combines:

- each published claim, converted to a concise confirmation question;
- every required fee category in `configs/moving.yaml` not adequately addressed by the website;
- ambiguity probes for qualifiers such as `starting at`, missing units, missing mover count, or an
  unstated minimum;
- job-specific access and requested-service questions from the locked JobSpec.

Example:

- Website claim: `Moving services from $149/hour.`
- Generated question: `Your website advertises moving services from $149 per hour. Does that rate
  apply to this exact move, how many movers are included, and what minimum and additional fees
  apply?`

The plan makes a future call shorter and more specific, but every mandatory fee category must still
be confirmed. Website material is never sufficient for quote comparison or negotiation leverage.

## Contracts

Add strict versioned contracts under `services/api/app/contracts` and regenerate OpenAPI and
frontend types.

### `WebsiteResearchClaimV1`

- `claim_id: UUID`
- `kind: WebsiteClaimKind`
- `summary: str` — bounded normalized statement
- `advertised_amount: Decimal | None`
- `currency: str | None`
- `unit: str | None`
- `qualifiers: list[str]`
- `source_url: HttpUrl`
- `source_excerpt: str` — exact bounded webpage excerpt
- `retrieved_at: datetime`
- `classification: Literal["unverified_website_claim"]`

`WebsiteClaimKind` covers the configured fee categories plus `hourly_rate`, `minimum_hours`,
`mover_count`, `service`, `availability`, `binding`, and `other`.

### `VendorVerificationQuestionV1`

- `question_id: UUID`
- `category: FeeCategory | WebsiteClaimKind`
- `question: str`
- `reason: Literal["published_claim", "missing_information", "ambiguous_claim"]`
- `claim_ids: list[UUID]`

### `VendorResearchDossierV1`

- `vendor: Vendor`
- `status: Literal["pending", "complete", "partial", "failed"]`
- `claims: list[WebsiteResearchClaimV1]`
- `missing_fee_categories: list[FeeCategory]`
- `verification_questions: list[VendorVerificationQuestionV1]`
- `researched_at: datetime | None`
- `safe_failure_reason: str | None`

Status semantics are exact:

- `pending`: selected but not yet analyzed;
- `complete`: structured extraction succeeded, even when the website publishes no price;
- `partial`: at least one safe claim was retained but some extraction or normalization work failed;
- `failed`: no safe structured claim set could be produced for that vendor.

### `JobVendorResearchV1`

- `job_id: UUID`
- `job_spec_version: Literal["1.0"]`
- `query: VendorSearchQuery`
- `candidates: list[Vendor]`
- `selected_vendor_ids: list[UUID]` — either empty or exactly three distinct candidate IDs
- `dossiers: list[VendorResearchDossierV1]`
- `source: Literal["tavily", "synthetic_mock"]`
- `created_at: datetime`
- `updated_at: datetime`

All real candidates use `data_classification=real_redacted`. The records contain public business
identity and website provenance only, not a person's PII or direct telephone contact.

## API

Add job-scoped endpoints:

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/api/jobs/{job_id}/vendor-research` | Return persisted discovery, selection, and dossiers; `404` before discovery |
| `POST` | `/api/jobs/{job_id}/vendor-research/discover` | Search from the locked JobSpec and persist candidates; optional `refresh=false` query flag |
| `PUT` | `/api/jobs/{job_id}/vendor-research/shortlist` | Validate and persist exactly three candidate IDs |
| `DELETE` | `/api/jobs/{job_id}/vendor-research/shortlist` | Clear the shortlist and dossiers without changing discovery candidates |
| `POST` | `/api/jobs/{job_id}/vendor-research/analyze` | Extract and normalize the three selected websites; optional `refresh=false` query flag |

All mutations require a confirmed JobSpec. Analyze requires a valid three-vendor shortlist.
Requests are synchronous and bounded in the first implementation; the frontend shows provider
progress and disables duplicate submissions. Persisted idempotency makes browser retries safe.

Default analysis returns an unchanged terminal `complete` dossier without provider activity and
retries only `partial`, `failed`, or `pending` dossiers. `refresh=true` explicitly reanalyzes all
three selected websites and spends provider credits again.

The existing generic `GET /api/vendors/discover` remains for compatibility but is no longer used by
the Calls-page job workflow.

## Architecture

### Integration boundaries

- Extend the Tavily boundary with a separate `TavilyExtractClient` protocol. Discovery and
  extraction remain independently testable even though they use the same backend API key.
- The production client calls `POST /extract` using bearer authentication, `extract_depth=basic`,
  `include_images=false`, and a bounded timeout.
- Add a `WebsiteClaimExtractor` protocol at the OpenAI integration boundary. It accepts one
  already-bounded page and returns only validated claim candidates.
- Orchestration owns validation, persistence, missing-category calculation, and deterministic
  question generation. External SDKs are never called directly from orchestration.

### Persistence boundary

Add a focused `VendorResearchRepository` protocol with `get` and `save` operations keyed by job ID
and JobSpec version.

- The in-memory repository stores deep-copied `JobVendorResearchV1` values.
- Supabase adds a `vendor_research` table with `(job_id, job_spec_version)` uniqueness, JSONB
  payload, timestamps, service-role-only access, and cascade deletion from `jobs`.
- Research remains separate from the `jobs`, `calls`, `quotes`, and `transcript_evidence` payloads,
  preventing asynchronous call updates from overwriting research and preventing research claims
  from entering evidence collections.

### Orchestration boundary

Add a focused `VendorResearchService` used by the FastAPI dependency graph. It receives:

- job lookup;
- `VendorDiscoveryGateway`;
- `TavilyExtractClient`;
- `WebsiteClaimExtractor`;
- `VendorResearchRepository`;
- moving configuration and a clock.

It never initiates voice calls. `VeraMoveService` and `FixtureRolePlayVendorRoster` retain their
current call behavior.

### Credential-free mock behavior

`APP_MODE=mock` remains fully credential-free. The job-scoped research routes use deterministic
synthetic candidates, extracted-content fixtures, claims, and questions labeled
`source=synthetic_mock`; they never make network calls. In `APP_MODE=live`, job-scoped real research
requires Tavily to be enabled and configured. Live discovery never falls back to the mock research
provider. Live discovery and shortlist persistence remain usable when OpenAI is disabled, but
analysis then records safe failed dossiers rather than fabricating claims.

## Frontend

Replace the collapsed `Where a production call list comes from` preview on the Calls page with a
job-aware research section while preserving the existing visual design.

### States

- **Not started:** explain real research and show `Find real movers`.
- **Discovering:** show bounded progress and prevent duplicate requests.
- **Candidates:** show company name, service area, Tavily source link, exactly-three selection, and
  a selected counter.
- **Researching:** persist the shortlist first, then show per-vendor progress.
- **Complete/partial:** show one dossier card per selected vendor with a prominent `Unverified
  website information` label, claims, missing categories, questions, source link, and timestamp.
- **Failed:** preserve any saved state and offer a scoped retry.

The section always states that real businesses were researched but not called and that the three
voice calls shown elsewhere are consenting fictional role plays. Presentation components use the
central API client and generated OpenAPI types; they never call Tavily or OpenAI directly.

## Failure Behavior

- Missing/invalid locked location: return a domain conflict before provider activity.
- Tavily disabled or misconfigured: fail closed with a safe provider-configuration response.
- Tavily search failure: retain prior successful persisted state and expose a retryable safe error.
- Fewer than three valid unique candidates: persist the candidates for display but reject shortlist
  creation until exactly three are available.
- Extract failure for one URL: create a `failed` dossier for that vendor and continue the others.
- OpenAI disabled or failed for one page: retain the vendor and source URL, create a `failed` or
  `partial` dossier, and do not fabricate claims.
- Model output outside the strict schema: reject that vendor's claim set and preserve the safe
  failure state.
- Job/version mismatch: reject the request rather than reusing stale research.
- Repeated analyze requests: reuse complete dossiers and retry only non-complete dossiers; full
  provider re-spend requires `refresh=true`.

## Trust and Privacy Rules

- Never persist Tavily/OpenAI credentials, raw extracted pages, arbitrary model output, phone
  numbers, personal contact data, or customer PII.
- Do not fetch browser-provided URLs. Only extract URLs from the server-persisted discovery set.
- Send only derived city/state route summaries to Tavily, never a street address from JobSpec.
- Accept only valid HTTPS source URLs from Tavily results.
- Cap candidates, page content, excerpt length, claims per vendor, and questions per vendor.
- Escape or treat all webpage content as untrusted data; it cannot alter model/system instructions.
- Website claims cannot populate `QuoteV1`, `TranscriptEvidence`, `RecommendationV1`, negotiation
  inputs, or call outcomes.
- Real-business vendor names never replace fictional role-play identities in the current live-call
  workflow.

### Bounded limits

- Search radius: 25 miles.
- Persisted discovery candidates: at most 10.
- Selected/extracted URLs: exactly 3.
- Extract depth: `basic`; timeout: 20 seconds for the three-URL request.
- Content crossing into OpenAI: at most 40,000 characters per vendor.
- Persisted claims: at most 20 per vendor.
- Persisted source excerpt: at most 500 characters per claim.
- Qualifiers: at most 8 per claim and 120 characters each.
- Verification questions: at most 40 per vendor and 500 characters each.

Provider responses that exceed these limits are truncated before the next boundary or rejected when
safe truncation would change structured meaning.

## Testing

### Backend

- Contract validation for exactly-three selection, source/excerpt bounds, unverified
  classification, and terminal dossier consistency.
- Tavily Search and Extract request-shape, malformed-response, timeout, partial-result, and safe
  error tests using injected fake transports only.
- OpenAI structured-claim parsing tests, including prompt-injection text and unsupported claims.
- Deterministic verification-question tests against every required fee category in
  `configs/moving.yaml`.
- Orchestration tests for confirmed-job gating, idempotent discovery, candidate-ID validation,
  shortlist replacement, partial analysis, and version mismatch.
- In-memory and Supabase repository round-trip tests.
- Evidence-isolation tests proving website claims never appear in quotes, transcript evidence,
  negotiation leverage, or recommendations.
- OpenAPI contract tests for every new endpoint.

### Frontend

- Generated-type compilation with no handwritten duplicate domain models.
- Candidate loading with the current job ID and no location supplied by the browser.
- Exactly-three selection and disabled invalid submission.
- Persisted state restoration after remount.
- Claim, source, unverified label, partial failure, and retry rendering.
- Confirmation that research actions never start calls.

### Required gates

1. Run focused backend and frontend tests during implementation.
2. Run `python scripts/export_openapi.py`.
3. Run `npm --prefix apps/web run generate:api`.
4. Run `python scripts/check.py`.
5. With deployed Tavily and OpenAI enabled, perform one read-only/live research smoke test using a
   synthetic JobSpec and confirm real candidates, three persisted selections, source-backed claims,
   and targeted questions.

Automated tests never spend provider credits or place phone calls.

## Rollout

1. Apply the new Supabase migration before deploying code that writes vendor research.
2. Deploy the backend with existing `TAVILY_ENABLED` and `OPENAI_ENABLED` settings; no new secret is
   required.
3. Deploy the frontend after the backend contract is live.
4. Confirm the public integration-status endpoint still reports Tavily and OpenAI truthfully.
5. Run the live research smoke test with obvious fictional move/customer data.
6. Leave the existing voice roster and destination secrets unchanged.

## Non-Goals

- Discovering, persisting, or dialing real-company phone numbers.
- Automatically contacting a real business.
- Treating published website prices as quotes or verified evidence.
- Using research claims as negotiation leverage.
- Replacing the current consented role-play call roster.
- Scraping arbitrary user-provided URLs.
- Booking, payment, or customer authorization workflows.

## External References

- Tavily Search API: <https://docs.tavily.com/documentation/api-reference/endpoint/search>
- Tavily Extract API: <https://docs.tavily.com/documentation/api-reference/endpoint/extract>
- Tavily Extract best practices:
  <https://docs.tavily.com/documentation/best-practices/best-practices-extract>
