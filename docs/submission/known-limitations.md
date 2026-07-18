# Known Limitations

Stated plainly in the README, the Tech Video (4:15–4:40), and available if a judge asks live.

- **Vendors may be role-played.** Where a call was made to a consenting teammate or friend rather than a real moving company, this is labeled on screen and in the transcript metadata — not presented as a real vendor interaction.
- **Real-business calling is not production-ready.** Calling actual, non-consenting moving companies at scale would need additional compliance work (consent, call recording law by state, do-not-call rules) not built for this hackathon.
- **Legal/compliance work remains.** No review has been done for telephony consumer-protection law, recording consent across jurisdictions, or data retention requirements.
- **VeraAI integration is planned, not built.** The only forward-looking artifact is an unused `source_context` stub field. There is no live connection to VeraAI.
- **Current MVP is moving-only.** The "config not code" claim for other verticals (e.g. contractor bids) is a stated design intent, not a built or tested feature.
- **No payments or booking.** The product recommends; it does not transact.
- **Document-parsed job specs may need confirmation.** OpenAI extraction from uploaded photos/quotes can misread a detail; the user confirmation step exists specifically to catch this, and it should be described as a safeguard, not a guarantee of accuracy.
- **Incomplete quotes are marked as incomplete**, not silently excluded or averaged into a ranking as if complete.

Honesty here is a strength, not a weakness — state it clearly rather than letting a judge find a gap the team didn't mention.
