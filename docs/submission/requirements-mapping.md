# Requirements-to-Evidence Mapping

Every row must resolve to real, checkable evidence before submission — no cell should say "yes" without a path, timestamp, or file behind it.

| Requirement | Demo timestamp | Tech-video timestamp | Code path | Dataset fixture | Transcript/recording evidence | Owner |
|---|---|---|---|---|---|---|
| Voice intake | 0:15 | 0:30–1:10 | `agents/intake` | `data/demo/job_specs.jsonl` | `demo-02-intake.mp4` | Zukhriuddin / Northeastern teammate |
| Document intake | 0:15 | 0:30–1:10 | `services/api/intake` | `data/demo/job_specs.jsonl` | `demo-02-intake.mp4` | Zukhriuddin |
| Same confirmed JobSpec across paths | 0:40 | 0:30–1:10 | `packages/contracts` | `data/demo/job_specs.jsonl` | `demo-03-confirmation.mp4` | Zukhriuddin |
| Three distinct call styles | 0:55–1:35 | 1:10–2:10 | `data/demo/vendor_policies.json` | `data/demo/vendor_policies.json` | `demo-04/05/06*.mp4` | Toheeb |
| Itemized, comparable quotes | 0:55–1:35, 2:05 | 2:10–2:55 | `services/api/report` | `data/demo/quotes.jsonl` | `demo-08-report.mp4` | Zukhriuddin |
| AI disclosure | 0:55 (first call) | 1:10–2:10 | agent system prompt / `agents/negotiator` | — | any call clip | Toheeb |
| Friction handling / callback commitment | 0:55–1:35 | 1:10–2:10 | `request_callback` tool | `data/demo/call_outcomes.jsonl` | call clip with friction | Toheeb |
| Honesty constraint (no invented quotes/inventory) | 1:35–2:05 | 1:10–2:10 | `get_verified_competing_quote` tool | — | `demo-07-negotiation.mp4` | Toheeb |
| Structured call ending | 0:55–1:35 | 1:10–2:10 | call outcome field | `data/demo/call_outcomes.jsonl` | all call clips | Toheeb |
| Measurable negotiation | 1:35–2:05 | 1:10–2:10 | `agents/negotiator` | `data/demo/call_outcomes.jsonl` | `demo-07-negotiation.mp4` | Toheeb |
| Evidence-backed recommendation | 2:05–2:35 | 2:10–2:55 | `services/api/report` | `data/demo/transcript_evidence.jsonl` | `demo-08-report.mp4` | Zukhriuddin |

Cross-check against `claim-ledger.md` — a requirement can't be marked complete here if its underlying claim is still PENDING there.
