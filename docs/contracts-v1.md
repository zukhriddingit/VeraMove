# VeraMove v1 data contract lock

`services/api/app/contracts/models.py` is the editable authority. FastAPI-generated OpenAPI and the
generated frontend schema are committed consumers. Breaking changes require backend and frontend
owner review and a new version suffix.

## JobSpecV1

Voice, document, merged, and demo intake all use `JobSpecV1`. An unconfirmed spec may contain null
access facts or an empty inventory so document parsing can represent “not stated” honestly.
`missing_required_fields()` identifies those gaps. Confirmation requires every pricing-relevant
field, a timestamp, and `locked_version == version`. The in-memory repository rejects later changes
to a confirmed spec.

`source_context` contains only nullable `vera_user_id` and `vera_property_id`. It does not integrate
with VeraAI. `intake_source` is a separate enum.

## QuoteV1 and evidence

Agent-tool fields remain in `provisional_data`. Transcript verification corrects contradictions in
`verified_data`, attaches `TranscriptEvidence`, and records `VerificationStatus`. A verified quote
cannot be manually fabricated and must contain transcript evidence plus a clear total.

`FeeLineItem.amount_status` distinguishes:

- `known` with an explicit amount or a calculable rate/minimum;
- `unknown` with no assumed amount;
- `not_applicable` when the vendor explicitly establishes that a category does not apply.

Zero is a known numeric value. Unknown is never serialized as zero. `comparable_total` is populated
only when the known line items support a trustworthy all-in comparison.

## Deterministic findings and recommendation

`IntelligenceFinding` carries a stable code, severity, plain-language description, vendor/quote
references, fee category, and evidence IDs. Model narration cannot add, remove, or override these
findings.

`RecommendationV1` distinguishes `cheapest_vendor_id` from `best_value_vendor_id`, ranks every
supported quote, cites transcript evidence and recording URLs, reports uncertainty, and includes
hidden-fee findings. It intentionally exposes no opaque AI score.

## Provenance and labels

Versioned payloads can carry `ProvenanceReference` values for document, voice, agent-tool,
transcript, demo-fixture, or Tavily sources. Public records use exactly one data label:
`synthetic`, `role_play`, or `real_redacted`.
