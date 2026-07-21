# Real Vendor Discovery and Website Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable job-scoped workflow that discovers real movers with Tavily, persists an exactly-three shortlist, extracts selected websites, stores source-backed unverified claims, and generates targeted verification questions without calling real businesses.

**Architecture:** A focused `VendorResearchService` coordinates the existing job lookup, a Tavily discovery gateway, a new Tavily Extract client, a strict OpenAI website-claim extractor, deterministic question generation, and a dedicated repository. FastAPI exposes job-scoped endpoints; the Calls page consumes only the generated OpenAPI client. Live voice remains isolated on the consenting fictional role-play roster.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, httpx, PostgreSQL/Supabase JSONB, OpenAI Responses API, Tavily Search and Extract APIs, React 19, TanStack Query, TypeScript 5.8, Vitest, pytest, Ruff.

## Global Constraints

- FastAPI-generated OpenAPI is the canonical public contract.
- `APP_MODE=mock` remains credential-free and performs no network or telephone activity.
- Live job-scoped research fails closed when Tavily is disabled or misconfigured; it never silently returns synthetic candidates.
- Research accepts only server-persisted HTTPS URLs returned by Tavily; the browser cannot submit URLs or search text.
- Send only derived city/state summaries to Tavily, never a street address.
- Select exactly three distinct persisted candidates before analysis.
- Website claims always remain `unverified_website_claim` and never enter quotes, transcript evidence, recommendations, call outcomes, or negotiation leverage.
- Do not discover, persist, or dial real-company phone numbers.
- Keep `FixtureRolePlayVendorRoster` and the current live destination slots unchanged.
- Persist at most 10 candidates, 3 selected URLs, 40,000 extracted characters per vendor, 20 claims per vendor, 500 characters per excerpt, 8 qualifiers per claim, and 40 verification questions per vendor.
- Preserve one centralized frontend client and generated OpenAPI types; do not add handwritten duplicate domain models or browser-side provider calls.
- Never commit credentials, populated `.env` files, raw webpages, arbitrary model output, customer PII, phone numbers, transcripts, recordings, or real moving records.

---

## File Structure

### New backend files

- `services/api/app/contracts/vendor_research.py` — strict public research contracts and validators.
- `services/api/app/integrations/tavily/extract.py` — bounded Tavily `/extract` client and parsed page envelope.
- `services/api/app/integrations/openai/vendor_research.py` — prompt, strict website-claim extraction, and deterministic mock extractor.
- `services/api/app/orchestration/vendor_research_questions.py` — pure missing-category and verification-question generation.
- `services/api/app/orchestration/vendor_research.py` — job-scoped discovery, shortlist, analysis, idempotency, and failure orchestration.
- `services/api/tests/test_vendor_research_contracts.py` — contract invariants.
- `services/api/tests/test_vendor_research_questions.py` — deterministic question rules.
- `services/api/tests/test_vendor_research_service.py` — workflow and evidence-isolation tests.
- `services/api/tests/test_tavily_extract.py` — Tavily Extract request/response tests.
- `services/api/tests/test_openai_vendor_research.py` — strict OpenAI request and normalization tests.
- `supabase/migrations/202607210006_vendor_research.sql` — durable service-role-only research table.

### New frontend files

- `apps/web/src/components/veramove/VendorResearchSection.tsx` — existing-design workflow UI.
- `apps/web/src/components/veramove/vendorResearchModel.ts` — pure exactly-three selection and display helpers.
- `apps/web/src/components/veramove/vendorResearchModel.test.ts` — pure Vitest coverage.

### Existing files modified

- `services/api/app/contracts/__init__.py`
- `services/api/app/integrations/tavily/base.py`
- `services/api/app/integrations/tavily/cached.py`
- `services/api/app/integrations/openai/base.py`
- `services/api/app/integrations/openai/live.py`
- `services/api/app/repositories/base.py`
- `services/api/app/repositories/memory.py`
- `services/api/app/repositories/supabase.py`
- `services/api/app/repositories/supabase_client.py`
- `services/api/app/api/dependencies.py`
- `services/api/app/api/router.py`
- `services/api/tests/test_supabase_repository.py`
- `services/api/tests/test_live_integrations_wiring.py`
- `services/api/tests/test_openapi.py`
- `apps/web/src/api/client.ts`
- `apps/web/src/lib/api/endpoints.ts`
- `apps/web/src/lib/api/hooks.ts`
- `apps/web/src/routes/calls.$jobId.tsx`
- `packages/contracts/openapi.json` — generated.
- `apps/web/src/api/schema.d.ts` — generated.
- `README.md`
- `data/demo/README.md`

---

### Task 1: Add strict research contracts and deterministic question generation

**Files:**
- Create: `services/api/app/contracts/vendor_research.py`
- Modify: `services/api/app/contracts/__init__.py`
- Create: `services/api/app/orchestration/vendor_research_questions.py`
- Test: `services/api/tests/test_vendor_research_contracts.py`
- Test: `services/api/tests/test_vendor_research_questions.py`

**Interfaces:**
- Produces: `WebsiteClaimKind`, `WebsiteResearchClaimV1`, `VendorVerificationQuestionV1`, `VendorResearchDossierV1`, `JobVendorResearchV1`, `VendorShortlistRequest`, and `build_verification_plan(job_spec, claims, required_fee_categories)`.
- Consumes: existing `Vendor`, `VendorSearchQuery`, `FeeCategory`, and `JobSpecV1` contracts.

- [ ] **Step 1: Write failing contract tests**

```python
def test_shortlist_is_empty_or_exactly_three_distinct_candidates(candidate_vendors, now):
    payload = research_payload(candidate_vendors, now)
    with pytest.raises(ValidationError, match="exactly three"):
        JobVendorResearchV1.model_validate({**payload, "selected_vendor_ids": [candidate_vendors[0].vendor_id]})


def test_claim_requires_unverified_classification(candidate_vendor, now):
    with pytest.raises(ValidationError):
        WebsiteResearchClaimV1(
            kind=WebsiteClaimKind.HOURLY_RATE,
            summary="Advertised from 149 USD per hour.",
            advertised_amount=Decimal("149"),
            currency="USD",
            unit="hour",
            qualifiers=["starting at"],
            source_url=candidate_vendor.provenance[0].location,
            source_excerpt="Moving services starting at $149/hour.",
            retrieved_at=now,
            classification="verified",
        )
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_contracts.py -q`  
Expected: collection fails because `services.api.app.contracts.vendor_research` does not exist.

- [ ] **Step 3: Implement the contracts with exact bounds and cross-field validators**

```python
class WebsiteResearchClaimV1(ContractModel):
    claim_id: UUID = Field(default_factory=uuid4)
    kind: WebsiteClaimKind
    summary: str = Field(min_length=1, max_length=500)
    advertised_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    unit: str | None = Field(default=None, max_length=80)
    qualifiers: list[str] = Field(default_factory=list, max_length=8)
    source_url: HttpUrl
    source_excerpt: str = Field(min_length=1, max_length=500)
    retrieved_at: datetime
    classification: Literal["unverified_website_claim"] = "unverified_website_claim"

    @field_validator("qualifiers")
    @classmethod
    def bound_qualifiers(cls, values: list[str]) -> list[str]:
        if any(len(value) > 120 for value in values):
            raise ValueError("claim qualifiers must be at most 120 characters")
        return values


class JobVendorResearchV1(ContractModel):
    job_id: UUID
    job_spec_version: Literal["1.0"]
    query: VendorSearchQuery
    candidates: list[Vendor] = Field(max_length=10)
    selected_vendor_ids: list[UUID] = Field(default_factory=list, max_length=3)
    dossiers: list[VendorResearchDossierV1] = Field(default_factory=list, max_length=3)
    source: Literal["tavily", "synthetic_mock"]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_selection(self) -> JobVendorResearchV1:
        selected = self.selected_vendor_ids
        if selected and (len(selected) != 3 or len(set(selected)) != 3):
            raise ValueError("selected_vendor_ids must contain exactly three distinct IDs")
        candidate_ids = {item.vendor_id for item in self.candidates}
        if not set(selected).issubset(candidate_ids):
            raise ValueError("selected vendors must come from persisted candidates")
        if any(item.vendor.vendor_id not in set(selected) for item in self.dossiers):
            raise ValueError("dossiers must belong to selected vendors")
        return self
```

- [ ] **Step 4: Write failing deterministic question tests**

```python
def test_planner_verifies_claim_and_every_missing_required_fee(job_spec, website_claim, required_fees):
    questions, missing = build_verification_plan(job_spec, [website_claim], required_fees)
    assert FeeCategory.BASE_SERVICE not in missing
    assert FeeCategory.STAIRS in missing
    assert any("$149" in item.question and item.reason == "published_claim" for item in questions)
    assert any(item.category == FeeCategory.STAIRS for item in questions)
    assert len(questions) <= 40
```

- [ ] **Step 5: Implement the pure planner**

Implement `build_verification_plan` so it maps fee-like claim kinds to `FeeCategory`, adds one
claim-confirmation question per safe claim, adds a deterministic question for every missing
configured fee, adds qualifier probes for `starting at`/missing unit/missing mover count, includes
locked access/service facts where relevant, deduplicates stable question text, and stops at 40.
Use UUID5 over vendor-independent question content so repeated calls are stable.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_contracts.py services/api/tests/test_vendor_research_questions.py -q`  
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/contracts services/api/app/orchestration/vendor_research_questions.py services/api/tests/test_vendor_research_contracts.py services/api/tests/test_vendor_research_questions.py
git commit -m "feat: define vendor research contracts"
```

---

### Task 2: Add bounded Tavily Extract and real-candidate normalization

**Files:**
- Modify: `services/api/app/integrations/tavily/base.py`
- Create: `services/api/app/integrations/tavily/extract.py`
- Modify: `services/api/app/integrations/tavily/cached.py`
- Test: `services/api/tests/test_tavily_extract.py`
- Modify tests: `services/api/tests/test_tavily_live.py`

**Interfaces:**
- Produces: `ExtractedWebPage(url: HttpUrl, content: str, truncated: bool)` and `TavilyExtractClient.extract(urls: tuple[HttpUrl, HttpUrl, HttpUrl]) -> dict[str, ExtractedWebPage | None]`.
- Produces: HTTPS-only, deduplicated Tavily candidates classified `real_redacted` when `role_play=False`.

- [ ] **Step 1: Write failing request/partial-response tests**

```python
def test_extract_posts_three_https_urls_with_bounded_options(recording_transport):
    client = TavilyHttpExtractClient("synthetic-key", "https://api.tavily.example", recording_transport)
    pages = client.extract((HttpUrl("https://a.example"), HttpUrl("https://b.example"), HttpUrl("https://c.example")))
    url, headers, payload = recording_transport.requests[0]
    assert url == "https://api.tavily.example/extract"
    assert payload == {
        "urls": ["https://a.example/", "https://b.example/", "https://c.example/"],
        "extract_depth": "basic",
        "include_images": False,
        "format": "markdown",
        "timeout": 20.0,
    }
    assert set(pages) == {"https://a.example/", "https://b.example/", "https://c.example/"}


def test_extract_preserves_success_when_one_url_fails(recording_transport):
    recording_transport.response = {"results": [{"url": "https://a.example/", "raw_content": "Rate $149"}], "failed_results": [{"url": "https://b.example/", "error": "blocked"}]}
    pages = make_client(recording_transport).extract(three_urls())
    assert pages["https://a.example/"] is not None
    assert pages["https://b.example/"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_tavily_extract.py -q`  
Expected: import fails for `TavilyHttpExtractClient`.

- [ ] **Step 3: Implement the injected Tavily Extract client**

Use the existing `TavilyJsonTransport`. Validate exactly three unique HTTPS URLs, translate HTTP or
malformed-envelope failures to `ProviderRequestError("Tavily extraction failed")`, return `None`
for explicit per-URL failures, cap content at 40,000 characters, and set `truncated=True` when capped.
Never return provider error strings or raw envelope metadata.

- [ ] **Step 4: Tighten live discovery normalization**

In `CachedTavilyVendorDiscovery._normalize`, reject non-HTTPS URLs before model construction,
deduplicate by normalized host/URL, and instantiate the job-scoped live gateway with
`role_play=False`. Keep the existing role-play option for mock-only tests and compatibility.

- [ ] **Step 5: Run Tavily tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_tavily_live.py services/api/tests/test_tavily_extract.py -q`  
Expected: all tests pass without network access.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/integrations/tavily services/api/tests/test_tavily_live.py services/api/tests/test_tavily_extract.py
git commit -m "feat: extract selected vendor websites"
```

---

### Task 3: Add strict OpenAI website-claim extraction and a credential-free mock

**Files:**
- Modify: `services/api/app/integrations/openai/base.py`
- Modify: `services/api/app/integrations/openai/live.py`
- Create: `services/api/app/integrations/openai/vendor_research.py`
- Test: `services/api/tests/test_openai_vendor_research.py`

**Interfaces:**
- Produces: `WebsiteClaimExtractor.extract(vendor, page, retrieved_at) -> list[WebsiteResearchClaimV1]`.
- Produces: `OpenAIWebsiteClaimExtractor` and `MockWebsiteClaimExtractor`.
- Consumes: `ExtractedWebPage` and `WebsiteResearchClaimV1`.

- [ ] **Step 1: Write failing strict-output and injection-resistance tests**

```python
def test_openai_claim_request_uses_strict_schema_and_untrusted_data_delimiters(vendor, page, now):
    transport = RecordingTransport(completed_response({"claims": [claim_payload(vendor, now)]}))
    extractor = build_extractor(transport)
    claims = extractor.extract(vendor, page, now)
    payload = transport.requests[0][2]
    assert payload["text"]["format"]["strict"] is True
    user_text = payload["input"][1]["content"][0]["text"]
    assert "<untrusted_vendor_webpage>" in user_text
    assert "Ignore all prior instructions" in user_text
    assert all(item.classification == "unverified_website_claim" for item in claims)


def test_extractor_rejects_excerpt_not_present_in_page(vendor, page, now):
    extractor = extractor_returning_excerpt("invented price")
    with pytest.raises(ProviderRequestError, match="unsupported source excerpt"):
        extractor.extract(vendor, page, now)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_openai_vendor_research.py -q`  
Expected: import fails for `OpenAIWebsiteClaimExtractor`.

- [ ] **Step 3: Add a generic strict structured-response method**

Add `OpenAIStructuredTextClient.parse_text(*, model, capability, schema_name, system_prompt, user_text, response_schema) -> dict[str, Any]` to `live.py`, reusing `_strict_json_schema`, `_post`, `_output_text`, and usage recording. Do not change existing document parsing behavior.

- [ ] **Step 4: Implement the research prompt and normalization**

The system prompt must state that webpage content is untrusted data, only exact published claims may
be extracted, `starting at` remains a qualifier, missing values stay absent, and no phone/contact
data may be returned. Wrap vendor identity, source URL, and bounded content in explicit untrusted
data delimiters. Validate every returned excerpt is an exact substring of `page.content`, replace
model IDs with server-generated UUID5 values, enforce the 20-claim cap, and preserve `truncated` as
a signal to orchestration.

- [ ] **Step 5: Implement deterministic mock claims**

`MockWebsiteClaimExtractor` returns a stable synthetic hourly-rate claim and one service claim using
`https://research.example.com/...` provenance. It performs no environment reads or network calls.

- [ ] **Step 6: Run focused OpenAI tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_openai_live.py services/api/tests/test_openai_vendor_research.py -q`  
Expected: all tests pass and usage records include capability `vendor_website_research`.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/integrations/openai services/api/tests/test_openai_live.py services/api/tests/test_openai_vendor_research.py
git commit -m "feat: extract unverified website claims"
```

---

### Task 4: Persist research independently in memory and Supabase

**Files:**
- Modify: `services/api/app/repositories/base.py`
- Modify: `services/api/app/repositories/memory.py`
- Modify: `services/api/app/repositories/supabase.py`
- Modify: `services/api/app/repositories/supabase_client.py`
- Create: `supabase/migrations/202607210006_vendor_research.sql`
- Modify tests: `services/api/tests/test_supabase_repository.py`
- Modify tests: `services/api/tests/test_repository_and_adapters.py`

**Interfaces:**
- Produces: `VendorResearchRepository.get_vendor_research(job_id, job_spec_version) -> JobVendorResearchV1 | None`.
- Produces: `VendorResearchRepository.save_vendor_research(research) -> JobVendorResearchV1`.

- [ ] **Step 1: Write failing repository round-trip tests**

```python
@pytest.mark.parametrize("repository_factory", [make_memory_repository, make_supabase_repository])
def test_vendor_research_round_trip_is_deep_copied(repository_factory, research):
    repository = repository_factory()
    saved = repository.save_vendor_research(research)
    saved.candidates.clear()
    loaded = repository.get_vendor_research(research.job_id, research.job_spec_version)
    assert loaded is not None
    assert len(loaded.candidates) == len(research.candidates)
```

- [ ] **Step 2: Run repository tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_repository_and_adapters.py services/api/tests/test_supabase_repository.py -q`  
Expected: missing repository methods.

- [ ] **Step 3: Add the repository protocol and in-memory implementation**

Store serialized deep copies under `(job_id, job_spec_version)` while holding the existing lock.
Clear this dictionary in the repository's test reset method.

- [ ] **Step 4: Add the Supabase migration**

```sql
create table if not exists vendor_research (
    id uuid primary key,
    job_id uuid not null references jobs(id) on delete cascade,
    job_spec_version text not null,
    data_classification text not null default 'real_redacted'
        check (data_classification in ('synthetic', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (job_id, job_spec_version)
);
alter table vendor_research enable row level security;
revoke all on vendor_research from anon, authenticated;
grant select, insert, update, delete on vendor_research to service_role;
create index if not exists vendor_research_job_version_idx
    on vendor_research(job_id, job_spec_version);
```

- [ ] **Step 5: Implement Supabase serialization**

Use deterministic UUID5 over `job_id:job_spec_version` as the row ID, `upsert(..., on_conflict="id")`,
and strict `JobVendorResearchV1.model_validate(row["payload"])` on read. Add `vendor_research` to the
table allowlist and fake-client tables. Convert transport failures to the repository's existing safe
error type.

- [ ] **Step 6: Run repository and migration tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_repository_and_adapters.py services/api/tests/test_supabase_repository.py services/api/tests/test_project_assets.py -q`  
Expected: all tests pass and the migration is detected in sequence.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/repositories services/api/tests/test_repository_and_adapters.py services/api/tests/test_supabase_repository.py supabase/migrations/202607210006_vendor_research.sql
git commit -m "feat: persist vendor research"
```

---

### Task 5: Implement the job-scoped vendor research service

**Files:**
- Create: `services/api/app/orchestration/vendor_research.py`
- Test: `services/api/tests/test_vendor_research_service.py`

**Interfaces:**
- Produces: `VendorResearchService.get`, `.discover`, `.set_shortlist`, `.clear_shortlist`, and `.analyze`.
- Consumes: `JobRepository`, `VendorResearchRepository`, `VendorDiscoveryGateway`, `TavilyExtractClient`, `WebsiteClaimExtractor`, required fee categories, and a clock.

- [ ] **Step 1: Write failing workflow tests**

Cover all of these named cases with injected fakes:

```python
def test_discovery_uses_locked_city_state_and_persists_real_candidates(service, confirmed_job, discovery):
    result = service.discover(confirmed_job.job_spec.job_id)
    assert discovery.queries == [VendorSearchQuery(city="Newton", state="MA", service_type="moving from Newton, MA to Boston, MA", radius_miles=25)]
    assert result.source == "tavily"
    assert all(v.data_classification is DataClassification.REAL_REDACTED for v in result.candidates)


def test_shortlist_rejects_ids_not_in_persisted_candidates(service, research):
    with pytest.raises(DomainConflict, match="persisted discovery candidates"):
        service.set_shortlist(research.job_id, [uuid4(), uuid4(), uuid4()])


def test_analysis_keeps_real_research_out_of_job_quotes_and_calls(service, job_repository, selected_research):
    analyzed = service.analyze(selected_research.job_id)
    job = job_repository.get(selected_research.job_id)
    assert len(analyzed.dossiers) == 3
    assert job.calls == []
    assert job.quotes == []
    assert job.recommendation is None
```

Also test unconfirmed jobs, unsafe location summaries, idempotent discovery, refresh conflicts,
exactly-three enforcement, clear-shortlist behavior, one failed URL, one invalid model result,
complete-dossier reuse, partial/failed scoped retry, `refresh=true`, and mock source behavior.

- [ ] **Step 2: Run service tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_service.py -q`  
Expected: import fails for `VendorResearchService`.

- [ ] **Step 3: Implement safe location derivation and discovery**

Accept only summaries ending in `city, state`, reject street-number patterns and missing two-letter
state codes, build a `VendorSearchQuery` with a 25-mile radius, call the injected discovery gateway,
retain at most 10 unique HTTPS-provenance candidates, force live candidates to `real_redacted`, and
persist even when fewer than three remain. Return an existing state unless `refresh=True`; raise
`DomainConflict` when refresh is requested with a saved shortlist.

- [ ] **Step 4: Implement shortlist mutations**

Validate exactly three unique UUIDs against the persisted candidate set. Preserve candidate order,
save selected IDs, create three `pending` dossiers, and clear stale dossiers when the selection
changes. `clear_shortlist` sets selected IDs and dossiers to empty while preserving discovery.

- [ ] **Step 5: Implement bounded analysis and idempotency**

Extract the three stored URLs in one request. For each vendor, reuse a `complete` dossier unless
`refresh=True`; retry pending/partial/failed dossiers. A missing page produces `failed`; successful
claim extraction plus truncated source produces `partial`; successful extraction otherwise produces
`complete`, including zero published prices. Generate questions using the pure planner and persist
after every vendor so partial progress survives a later failure.

- [ ] **Step 6: Run service tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_service.py -q`  
Expected: all workflow and evidence-isolation tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/orchestration/vendor_research.py services/api/tests/test_vendor_research_service.py
git commit -m "feat: orchestrate vendor research"
```

---

### Task 6: Wire FastAPI routes, providers, mock mode, and canonical OpenAPI

**Files:**
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/router.py`
- Modify tests: `services/api/tests/test_live_integrations_wiring.py`
- Modify tests: `services/api/tests/test_openapi.py`
- Modify tests or create: `services/api/tests/test_vendor_research_api.py`
- Generate: `packages/contracts/openapi.json`
- Generate: `apps/web/src/api/schema.d.ts`

**Interfaces:**
- Produces the four job-scoped route behaviors plus shortlist deletion from the approved design.
- Produces generated `components["schemas"]["JobVendorResearchV1"]` frontend type.

- [ ] **Step 1: Write failing API tests**

```python
def test_job_vendor_research_api_flow(client, confirmed_job_id, candidate_ids):
    discovered = client.post(f"/api/jobs/{confirmed_job_id}/vendor-research/discover")
    assert discovered.status_code == 200
    shortlisted = client.put(
        f"/api/jobs/{confirmed_job_id}/vendor-research/shortlist",
        json={"vendor_ids": [str(value) for value in candidate_ids[:3]]},
    )
    assert shortlisted.status_code == 200
    analyzed = client.post(f"/api/jobs/{confirmed_job_id}/vendor-research/analyze")
    assert analyzed.status_code == 200
    assert len(analyzed.json()["dossiers"]) == 3
    assert client.get(f"/api/jobs/{confirmed_job_id}/vendor-research").json() == analyzed.json()
```

Test 404 before discovery, 409 before confirmation, 409 for invalid selection, refresh query
semantics, DELETE shortlist, and safe provider errors.

- [ ] **Step 2: Run API tests and verify RED**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_api.py services/api/tests/test_openapi.py -q`  
Expected: new paths return 404 and OpenAPI path assertions fail.

- [ ] **Step 3: Wire production and mock providers**

Add `get_vendor_research_service`. In mock mode inject `MockVendorDiscoveryGateway`, a deterministic
mock Extract client, and `MockWebsiteClaimExtractor`. In live mode require configured Tavily for the
research service, instantiate `CachedTavilyVendorDiscovery(..., role_play=False)`,
`TavilyHttpExtractClient`, and either `OpenAIWebsiteClaimExtractor` or a disabled extractor that
produces safe failed dossiers. Reuse the application repository for the new repository protocol.

- [ ] **Step 4: Add the typed routes**

```python
@router.get("/api/jobs/{job_id}/vendor-research", response_model=JobVendorResearchV1)
def get_vendor_research(job_id: UUID, service: VendorResearchServiceDep) -> JobVendorResearchV1:
    return service.get(job_id)

@router.post("/api/jobs/{job_id}/vendor-research/discover", response_model=JobVendorResearchV1)
def discover_job_vendors(job_id: UUID, service: VendorResearchServiceDep, refresh: bool = False) -> JobVendorResearchV1:
    return service.discover(job_id, refresh=refresh)

@router.put("/api/jobs/{job_id}/vendor-research/shortlist", response_model=JobVendorResearchV1)
def set_vendor_shortlist(job_id: UUID, payload: VendorShortlistRequest, service: VendorResearchServiceDep) -> JobVendorResearchV1:
    return service.set_shortlist(job_id, payload.vendor_ids)

@router.delete("/api/jobs/{job_id}/vendor-research/shortlist", response_model=JobVendorResearchV1)
def clear_vendor_shortlist(job_id: UUID, service: VendorResearchServiceDep) -> JobVendorResearchV1:
    return service.clear_shortlist(job_id)

@router.post("/api/jobs/{job_id}/vendor-research/analyze", response_model=JobVendorResearchV1)
def analyze_vendor_websites(job_id: UUID, service: VendorResearchServiceDep, refresh: bool = False) -> JobVendorResearchV1:
    return service.analyze(job_id, refresh=refresh)
```

- [ ] **Step 5: Run API/wiring tests and verify GREEN**

Run: `.venv/bin/pytest services/api/tests/test_vendor_research_api.py services/api/tests/test_live_integrations_wiring.py services/api/tests/test_openapi.py -q`  
Expected: all tests pass.

- [ ] **Step 6: Regenerate canonical artifacts**

Run: `python scripts/export_openapi.py`  
Expected: `packages/contracts/openapi.json` includes all five routes and research schemas.

Run: `npm --prefix apps/web run generate:api`  
Expected: `apps/web/src/api/schema.d.ts` is regenerated without manual edits.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/api services/api/tests/test_vendor_research_api.py services/api/tests/test_live_integrations_wiring.py services/api/tests/test_openapi.py packages/contracts/openapi.json apps/web/src/api/schema.d.ts
git commit -m "feat: expose job vendor research API"
```

---

### Task 7: Build the generated-type frontend workflow

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/lib/api/endpoints.ts`
- Modify: `apps/web/src/lib/api/hooks.ts`
- Create: `apps/web/src/components/veramove/vendorResearchModel.ts`
- Create: `apps/web/src/components/veramove/vendorResearchModel.test.ts`
- Create: `apps/web/src/components/veramove/VendorResearchSection.tsx`
- Modify: `apps/web/src/routes/calls.$jobId.tsx`

**Interfaces:**
- Produces centralized client methods `getVendorResearch`, `discoverJobVendors`, `setVendorShortlist`, `clearVendorShortlist`, and `analyzeVendorWebsites`.
- Produces TanStack hooks keyed by `qk.vendorResearch(jobId)`.
- Consumes only generated `JobVendorResearchV1` and `VendorShortlistRequest` types.

- [ ] **Step 1: Write failing pure frontend model tests**

```typescript
it("selects at most three distinct candidates", () => {
  expect(toggleVendor([], "a")).toEqual(["a"]);
  expect(toggleVendor(["a", "b", "c"], "d")).toEqual(["a", "b", "c"]);
  expect(toggleVendor(["a", "b", "c"], "b")).toEqual(["a", "c"]);
});

it("enables research only for exactly three IDs", () => {
  expect(canResearch(["a", "b"])).toBe(false);
  expect(canResearch(["a", "b", "c"])).toBe(true);
});
```

- [ ] **Step 2: Run Vitest and verify RED**

Run: `npm --prefix apps/web test -- vendorResearchModel.test.ts`  
Expected: module import fails.

- [ ] **Step 3: Implement the pure selection/display helpers**

Export `toggleVendor`, `canResearch`, `sourceUrl(vendor)`, `statusCopy(status)`, and
`formatResearchTimestamp`. Do not define duplicate domain interfaces; parameter types come from
`components["schemas"]`.

- [ ] **Step 4: Add centralized API methods and hooks**

Construct paths with `encodeURIComponent(jobId)`, pass `refresh=true` only when explicit, send only
`{vendor_ids: string[]}` for shortlist, normalize all FastAPI errors through existing `apiFetch`, and
invalidate only `qk.vendorResearch(jobId)` after mutations. `GET` treats 404 as `null` so the not-
started state is normal.

- [ ] **Step 5: Implement `VendorResearchSection`**

Use the existing surface, button, status-pill, typography, and spacing primitives. Render:

- not-started explanation and `Find real movers`;
- pending discovery state;
- candidate cards with real-company label, source link, exactly-three checkbox behavior, and count;
- `Save and research selected movers`, which awaits shortlist persistence before analysis;
- one dossier card per selected vendor with `Unverified website information`, claims, qualifiers,
  excerpts, missing fee categories, verification questions, source, timestamp, and partial/failed
  retry;
- explicit copy that these real businesses were researched but not called and the voice calls are
  consenting fictional role plays;
- clear/refresh controls that state when provider credits will be spent again.

The component never calls `fetch`, Tavily, OpenAI, ElevenLabs, or Twilio directly.

- [ ] **Step 6: Replace the old Calls-page preview**

Delete `TavilyDiscoverySection` from `calls.$jobId.tsx` and mount
`<VendorResearchSection jobId={jobId} />` in the same location. Do not change call polling,
negotiation navigation, or role-play call cards.

- [ ] **Step 7: Run frontend tests, typecheck, and build**

Run: `npm --prefix apps/web test`  
Expected: all Vitest tests pass.

Run: `npm --prefix apps/web run typecheck`  
Expected: zero TypeScript errors.

Run: `npm --prefix apps/web run build`  
Expected: Vite/Nitro production build succeeds.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/api/client.ts apps/web/src/lib/api/endpoints.ts apps/web/src/lib/api/hooks.ts apps/web/src/components/veramove apps/web/src/routes/calls.\$jobId.tsx
git commit -m "feat(web): add real vendor research workflow"
```

---

### Task 8: Document operations and run the complete local verification gate

**Files:**
- Modify: `README.md`
- Modify: `data/demo/README.md`
- Modify if required: `.env.example` — no new secret or flag is expected.

**Interfaces:**
- Produces exact migration, local mock, live activation, privacy, and smoke-test instructions.

- [ ] **Step 1: Update documentation**

Document migration `202607210006_vendor_research.sql`, the Search → exactly-three → Extract flow,
Tavily/OpenAI credit behavior, mock fixtures, the fact that no real company is called, and the
separation between website claims and verified call evidence. Update the API table with all five
job-scoped routes. Keep `APP_MODE=mock` as the default.

- [ ] **Step 2: Run generated-asset consistency checks**

Run: `python scripts/export_openapi.py --check` if supported; otherwise run
`python scripts/export_openapi.py` followed by `git diff --exit-code packages/contracts/openapi.json`.  
Expected: generated OpenAPI is current.

Run: `npm --prefix apps/web run generate:api` followed by
`git diff --exit-code apps/web/src/api/schema.d.ts`.  
Expected: generated TypeScript is current.

- [ ] **Step 3: Run the complete repository gate**

Run: `python scripts/check.py`  
Expected: Ruff, pytest, OpenAPI export, frontend type generation, TypeScript, Vitest, and production
build all pass.

- [ ] **Step 4: Audit the no-secrets/no-PII boundary**

Run:

```bash
git diff --check
git grep -nE 'tvly-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{20,}|\+[1-9][0-9]{9,14}' -- ':!package-lock.json'
```

Expected: no new secret or real phone-number match appears in changed files.

- [ ] **Step 5: Commit**

```bash
git add README.md data/demo/README.md .env.example
git commit -m "docs: explain real vendor research"
```

---

### Task 9: Deploy, migrate, and prove the public workflow

**Files/external state:**
- Push: `codex/real-vendor-research`
- Apply: `supabase/migrations/202607210006_vendor_research.sql`
- Deploy backend on Render after migration.
- Mirror the reviewed `apps/web` changes to Lovable project `6d8ed1ea-bbda-4540-bb3f-8e866e3b7a77` and publish.

**Interfaces:**
- Produces public job-scoped real research at `https://deal-mover-ai.lovable.app` backed by the Render API.

- [ ] **Step 1: Push the verified branch and open/review the integration diff**

Run: `git push -u origin codex/real-vendor-research`  
Expected: remote branch points at the locally verified HEAD.

- [ ] **Step 2: Apply the Supabase migration before backend deployment**

Run the exact contents of `202607210006_vendor_research.sql` in the linked Supabase SQL editor.
Verify the table exists, RLS is enabled, `anon` and `authenticated` have no privileges, and
`service_role` has CRUD privileges.

- [ ] **Step 3: Deploy and verify the backend**

Deploy the verified commit to Render. Confirm:

```bash
curl -fsS https://veramove-api-demo-zukhriddingit.onrender.com/api/health
curl -fsS https://veramove-api-demo-zukhriddingit.onrender.com/api/integrations/status
```

Expected: health is OK; Tavily and OpenAI report `enabled=true, configured=true` without exposing
secrets.

- [ ] **Step 4: Run a live synthetic research smoke test**

Create or reuse an obviously fictional confirmed Newton, MA → Boston, MA JobSpec. Call discovery,
select three returned candidate IDs, then analyze. Verify:

- `source=tavily`;
- candidates are `real_redacted` and have HTTPS Tavily provenance;
- exactly three IDs persist after a new GET;
- every claim is `unverified_website_claim` with an exact source excerpt and timestamp;
- every dossier has targeted questions and all missing configured fee categories;
- the job's calls, quotes, recommendation, and role-play roster are unchanged;
- a repeated analyze call does not spend a full refresh.

- [ ] **Step 5: Publish and visually verify the Lovable frontend**

Mirror only the reviewed frontend files, run Lovable's TypeScript/tests/build checks, publish, and
open a fresh production browser session. Verify the Calls page can discover, select exactly three,
restore the selection after reload, display unverified dossier cards/source links/questions, and
never present a call button for a real business.

- [ ] **Step 6: Merge only after deployment evidence is green**

Review the complete branch diff for unrelated changes, merge to `main`, update
`deploy/veramove-demo` to the same verified commit, and confirm both remote branch heads match.

---

## Completion Audit

Before marking the feature complete, record evidence for every item:

- Real Tavily discovery uses the locked route and persists candidates.
- Exactly three selected real movers survive refresh/redeploy.
- Tavily Extract runs only on those stored HTTPS URLs.
- OpenAI produces bounded, source-supported, permanently unverified claims.
- Deterministic questions target published, ambiguous, and missing information.
- Full webpage content, phone numbers, provider secrets, and PII are not persisted.
- Real research never changes calls, quotes, evidence, recommendations, negotiation, or the role-play roster.
- Mock mode completes without credentials or network calls.
- Supabase migration and service-role-only access are active.
- Canonical OpenAPI and generated frontend types match.
- Backend tests, frontend tests, typecheck, and production build pass.
- The public Lovable deployment completes the research workflow against the deployed Render API.

Only after all evidence is present is the implementation complete.
