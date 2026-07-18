# Intelligence provider handoff

Member 1 can consume `IntelligenceProvider` from
`services/api/app/intelligence/base.py` without importing OpenAI, Tavily, or persistence SDKs.

The interface exposes:

```python
verify_quote(provisional_quote, transcript_facts, required_fee_categories)
get_verified_competing_quote(job_id, excluded_vendor_id)
recommend(job_spec, quotes)
```

`DefaultIntelligenceProvider` requires a `QuoteCatalog`. The orchestration owner can adapt the
repository with one read-only `list_quotes(job_id)` method. The provider returns no leverage unless
the competing quote:

- belongs to the same job and a different vendor;
- uses the locked `JobSpecV1` version;
- is verified, evidence-backed, and not manually fabricated;
- has an explicit `comparable_total`.

The document boundary is `DocumentIntakeGateway`. `OpenAIDocumentParser` accepts PDF, PNG, or JPEG
bytes through an injected strict structured-output client. It is intentionally not wired to an API
route or credentials on this branch because route ownership remains with Member 1. The returned
`DocumentParseResult.job_spec` is the same `JobSpecV1` used by voice intake.

The Tavily boundary exposes `source_call_list(VendorSearchQuery)` for city, state, service type, and
radius. Mock mode returns three cached synthetic vendors. The optional cached normalizer stores no
phone number or unnecessary personal information.

Representative frontend responses are in `data/demo/job_specs.jsonl`, `quotes.jsonl`, and
`recommendations.jsonl`. The dataset explanation and evidence timestamps for the submission owner
are in `data/demo/README.md`.
