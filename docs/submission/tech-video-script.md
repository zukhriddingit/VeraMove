# Tech Video Script & Recording Instructions

**Target length:** 4:00–5:00
**Host / final cut:** Arsalan
**Deadline for all raw segments:** *[insert — recommend Gate 5 minus 3 hours, so Arsalan has real edit time]*
**Preferred format for every segment:** 1080p minimum, landscape (16:9), MP4, clear single-speaker audio, screen-share + webcam-in-corner where applicable

---

## Segment order

| Time | Segment | Speaker | Filename |
|---|---|---|---|
| 0:00–0:30 | Architecture overview + VeraMove/VeraAI independence | Arsalan | `tech-member-4-context.mp4` (intro half) |
| 0:30–1:10 | Shared JobSpec, document parsing, version locking | Zukhriuddin | `tech-member-2-data.mp4` (part 1) |
| 1:10–2:10 | Voice system: ElevenLabs, dynamic variables, tools, webhooks, disclosure, verified leverage | Toheeb | `tech-member-1-voice.mp4` |
| 2:10–2:55 | Backend/data: Supabase, normalization, hidden-fee detection, ranking | Zukhriuddin | `tech-member-2-data.mp4` (part 2) |
| 2:55–3:35 | Frontend: Lovable structure, API integration, live call status, report | Northeastern teammate | `tech-member-3-frontend.mp4` |
| 3:35–4:15 | Evals & market simulation: moving.yaml, vendor policies, tests, dataset | Zukhriuddin | `tech-member-2-data.mp4` (part 3) |
| 4:15–4:40 | Limitations, role-play disclosure, future work | Arsalan | `tech-member-4-context.mp4` (outro half) |

---

## Per-speaker recording brief

### Arsalan — 0:00–0:30 and 4:15–4:40 (~55s total)
- **Must be visible:** architecture diagram (Lovable → Backend → Supabase/OpenAI → ElevenLabs/Twilio → vendor/counter-agent), then at the end a plain slide listing limitations.
- **Talking points:** what the system does end to end; explicitly state VeraMove is intentionally decoupled from early-stage VeraAI; close with role-play disclosure, "real-business calling is future work," "VeraAI integration is planned but not built," "this MVP demonstrates the full loop."
- **Resolution/orientation:** 1080p landscape, webcam over diagram or slide.

### Zukhriuddin — 0:30–1:10, 2:10–2:55, 3:35–4:15 (~2:05 total, can be one continuous take split by the editor)
- **Must be visible:** JobSpec schema (on screen), a live document-parsing run, the version-lock field, Supabase table view, the normalization/hidden-fee logic, `moving.yaml`, vendor policy files, eval output.
- **Talking points:** how document + voice intake collapse into one schema; how version locking works; how a transcript becomes structured JSON; how hidden fees are detected and how ranking/red-flag logic works; how the dataset and evals were built.
- **Resolution/orientation:** 1080p landscape, screen recording with voiceover.

### Toheeb — 1:10–2:10 (~60s)
- **Must be visible:** ElevenLabs agent config screen, a dynamic-variable payload, an outbound call firing, the webhook payload landing in the backend, the disclosure line in the system prompt, and — critically — proof the agent cannot access or state an unverified competing quote.
- **Talking points:** batch calling setup, tool calls (`save_quote`, `save_call_outcome`, `get_verified_competing_quote`, `request_callback`), webhook flow, the honesty guardrail.
- **Resolution/orientation:** 1080p landscape, screen recording with voiceover.

### Northeastern teammate — 2:55–3:35 (~40s)
- **Must be visible:** Lovable component tree or preview, the live call-status view, the report page, the transcript-evidence links.
- **Talking points:** how the frontend consumes the frozen API routes rather than duplicating logic; what a judge sees start to finish in the UI.
- **Resolution/orientation:** 1080p landscape, screen recording with voiceover.

---

### Editing rules
- The honesty-guardrail moment (Toheeb's segment) should be shown clearly enough that a judge could pause and read it — don't cut away too fast.
- Every "this is planned, not built" statement stays in the final cut. Do not trim it for pacing.
