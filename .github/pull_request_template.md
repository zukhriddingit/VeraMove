## Summary

Describe the focused change and the owned subsystem it affects.

## Contract impact

- [ ] No public contract change
- [ ] Pydantic, OpenAPI, and generated TypeScript types updated together

## Verification

- [ ] `python scripts/check.py` passes
- [ ] Mock workflow exercised when orchestration or contracts changed
- [ ] Visible UI changes include a screenshot

## Narrative impact

- [ ] N/A — this PR doesn't touch README.md, docs/submission/, or docs/demo-ux.md
- [ ] This PR changes judge-facing wording — flagged to @ars2711 for `docs/submission/claim-ledger.md` verification before it's used in a video or the Project Summary

## Safety

- [ ] No secrets, real PII, phone numbers, home addresses, recordings, or local databases
- [ ] All new demo data is clearly synthetic
- [ ] No real external API call or deployment step was added
