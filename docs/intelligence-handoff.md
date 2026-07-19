# Intelligence provider handoff

Backend orchestration consumes `IntelligenceProvider` from
`services/api/app/orchestration/providers.py` without importing OpenAI, Tavily, or persistence
clients directly.

The interface exposes:

```python
extract_document(document_text)
negotiate(job_spec, quotes, verified_competitor)
```

The repository, not a model, returns no negotiation leverage unless the competing quote:

- belongs to the same job and a different vendor;
- uses the locked `JobSpecV1` version;
- is verified, evidence-backed, and not manually fabricated;
- has an explicit `comparable_total`.

The document boundary is `DocumentIntakeGateway`. `OpenAIDocumentParser` accepts text, PDF, PNG, or
JPEG bytes through an injected strict structured-output client. The current document-intake API
supplies UTF-8 text; with `OPENAI_ENABLED=true`, the Responses adapter extracts and revalidates a
`DocumentParseResult`. Its `job_spec` is the same `JobSpecV1` used by voice intake and cannot be
confirmed or locked by the model. Negotiation planning remains deterministic.

The Tavily boundary exposes `source_call_list(VendorSearchQuery)` for city, state, service type, and
radius. Mock mode returns three cached synthetic vendors. The optional cached normalizer stores no
phone number or unnecessary personal information. With `TAVILY_ENABLED=true`, runtime discovery
uses a bounded live search and reports `source=tavily`; failures do not fall back to fixtures.

Recommendation narration is also optional. The OpenAI narrator receives the already-constructed
rankings and findings, and only its summary text is accepted. Canonical winner IDs, totals,
findings, evidence IDs, transcript evidence, and recording URLs remain unchanged.

Representative frontend responses are in `data/demo/job_specs.jsonl`, `quotes.jsonl`, and
`recommendations.jsonl`. The dataset explanation and evidence timestamps for the submission owner
are in `data/demo/README.md`.
