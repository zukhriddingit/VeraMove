# Claim Ledger

**Rule: no claim below moves into a video, the Project Summary, or the README until its Technical Owner marks it Verified.** "Verified" means the owner has watched/read the actual supporting evidence in this build, not that it seems plausible.

Status key: `VERIFIED` · `PENDING` · `PARTIAL` (true with caveats — see wording limitations) · `CUT` (removed from all materials)

| Claim | Where it appears | Technical owner | Supporting code / dataset | Supporting recording / transcript | Verified | Wording limitations |
|---|---|---|---|---|---|---|
| Both intake paths produce the same `JobSpecV1` | Demo Video 0:15–0:40, Tech Video 0:30–1:10, README | Zukhriuddin | `packages/contracts`, `services/api/intake` | demo-02-intake.mp4 | PENDING | Confirm both paths hit the identical schema version, not just a similar-looking object |
| Every call uses the same locked JobSpec version | Demo Video 0:40–0:55, Project Summary | Zukhriuddin + Toheeb | job-spec version field in Supabase | demo-03-confirmation.mp4 | PENDING | Must show the version ID is unchanged across all three call payloads |
| Three distinct vendor negotiation styles were demonstrated | Demo Video 0:55–1:35, Tech Video, Team Video | Toheeb | `data/demo/vendor_policies.json` | demo-04/05/06 clips | PENDING | If any vendor is role-play, label it on screen — see known-limitations.md |
| A hidden fee was uncovered | Demo Video 0:55–1:35, Best Quote lines | Zukhriuddin | hidden-fee detection logic | demo-05-hidden-fee.mp4 | PENDING | State clearly whether the fee was surfaced by the agent's question or volunteered by the vendor |
| The competing quote used as leverage was verified, not invented | Demo Video 1:35–2:05, honesty-line requirement | Toheeb + Zukhriuddin | `get_verified_competing_quote` tool call log | demo-07-negotiation.mp4 | PENDING | This is the single highest-risk claim — do not soften or imply if not literally true |
| The negotiated price or terms measurably changed | Demo Video 1:35–2:05, pitch script, viral clip | Toheeb | call outcome record (before/after) | demo-07-negotiation.mp4 | PENDING | Report exact before/after numbers, not "significantly better" |
| Final recommendation cites evidence (transcript/recording links) | Demo Video 2:05–2:35, requirements-mapping.md | Zukhriuddin | `services/api/report` | demo-08-report.mp4 | PENDING | Confirm the UI actually links out to the underlying transcript, not just a static quote |
| VeraMove is standalone and not currently integrated into VeraAI | Project Summary, README, Tech Video 4:15–4:40 | Arsalan (policy line) / Toheeb (technical fact) | `source_context` stub field, not wired to anything | tech-member-4-context.mp4 | PENDING | Must stay true even if a demo mentions VeraAI by name |
| AI disclosure happens on every call | Demo/Tech Video, conversation-requirements checklist | Toheeb | disclosure line in agent system prompt | any call clip | PENDING | Confirm this fired on all three calls, not just the one shown |
| At least one call survived real friction (hold music / callback) | Demo Video, conversation-requirements checklist | Toheeb | callback-commitment tool log | call clip with friction | PENDING | If this was not captured on the calls that made the final cut, don't imply it was |
| Every call ended in one of: itemized quote / callback commitment / documented decline | Tech Video, requirements-mapping.md | Toheeb | call outcome field in Supabase | all three call clips | PENDING | — |
| Quotes below 30% of median are flagged as red flags | Demo Video 2:05–2:35, README | Zukhriuddin | red-flag threshold logic | demo-08-report.mp4 | PENDING | — |

### Process
1. Owner reviews their rows and flips status to VERIFIED, PARTIAL, or CUT.
2. Arsalan re-checks wording in every script/doc against the final status before recording or publishing.
3. Any claim still PENDING at Gate 5 (code freeze) gets cut from the story, not left in on a hope.
