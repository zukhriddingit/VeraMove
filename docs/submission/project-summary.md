# Project Summary

**Status: DRAFT — pending final technical verification by Member 1 (Toheeb) and Member 2 (Zukhriuddin) before portal submission.**

**Word count: 238** *(recount after any edit — must stay in the 150–300 range)*

---

VeraMove is an AI-powered moving-services negotiator that helps renters and homebuyers obtain transparent, comparable quotes without repeating the same information across multiple phone calls. The challenge brief cites a 5.6× price spread for the same 45-mile move, showing how opaque phone-based pricing can be. VeraMove is built as a standalone hackathon product and designed to become an optional VeraAI module as the broader housing platform matures.

A user begins with either an ElevenLabs voice interview or an uploaded moving quote or inventory document. Both intake paths produce the same structured job specification, including locations, move date, inventory, stairs, elevator access, packing needs, and other price-changing details. The user confirms this specification before any calls are placed.

VeraMove then uses an ElevenLabs calling agent to contact at least three vendors or simulated counterparties with different negotiation styles. Every vendor receives the identical confirmed specification. The agent requests an itemized, all-in quote, identifies hidden fees, records structured outcomes, and handles refusals, interruptions, and AI-disclosure questions honestly.

After collecting the initial quotes, VeraMove uses verified competing offers as leverage in a follow-up negotiation. It never invents a bid or misrepresents the customer's job. The final dashboard ranks the options by total price, quote completeness, binding status, concessions, and risk flags, while linking each conclusion to transcript and call evidence.

The prototype combines ElevenLabs, OpenAI, Lovable, Supabase, Tavily, and Codex to demonstrate a complete intake-to-negotiation workflow for a phone-priced, housing-adjacent market.

---

### Pre-submission checks (Member 4 / Arsalan)
- [ ] Word count re-confirmed in range (150–300)
- [ ] Every tool named was actually used — cross-check against `configs/moving.yaml` and the final tech stack
- [ ] No claim of current VeraAI integration
- [ ] No claim of production readiness
- [ ] Member 1 sign-off (backend/voice accuracy)
- [ ] Member 2 sign-off (data/OpenAI accuracy)
