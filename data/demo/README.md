# VeraMove public demo dataset

Every file in this directory contains fictional records labeled `synthetic`, `role_play`, or
`real_redacted`. The committed demo defaults to `synthetic`. It contains no real people, phone
numbers, home addresses, vendor contacts, recordings, credentials, or private transcripts.
`recordings.example.com` links are evidence-shaped placeholders, not actual calls.

## Generation and demo coverage

The records were generated from three policy cards in `configs/moving.yaml`: a transparent vendor,
a low-headline vendor that reveals charges only after probing, and a premium vendor that improves
an offer only when shown a verified quote. The primary demo uses the locked job in
`job_specs.jsonl`, the three records in `quotes.jsonl`, all evidence records, and the ranked
recommendation. `call_outcomes.jsonl` also covers callback, decline, and failure branches.

## Files

- `job_specs.jsonl`: versioned, confirmed `JobSpecV1` records.
- `vendor_policies.json`: policy rules used for role-play; these are not scripted conversations.
- `quotes.jsonl`: provisional fields, verified fields, normalized totals, and provenance-safe flags.
- `transcript_evidence.jsonl`: short synthetic excerpts with timestamps and example recording URLs.
- `call_outcomes.jsonl`: the four closed outcome types.
- `recommendations.jsonl`: evidence-backed rankings that distinguish cheapest from best value.
- `eval_results.csv`: reproducible expected results from `python -m evals.run`.

Legacy JSON fixtures remain because the mock orchestration loader consumes them.

## Anonymization and publication

All locations are obvious placeholders, vendor names are fictional, and no direct contact fields
are stored. A future `real_redacted` record must remove names, phone numbers, street addresses,
private participant details, and recording content before review. Real data must never be relabeled
as synthetic.

## Evaluations

Run `python -m evals.run`. The suite validates strict contracts, normalization arithmetic,
unknown-versus-zero handling, transcript evidence, deterministic red flags, fake-bid rejection,
and ranking consistency. Unit tests use injected mock providers and never call OpenAI or Tavily.

This dataset is provided under the repository MIT license.
