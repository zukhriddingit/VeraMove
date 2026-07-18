# Demo UX

The frontend is a deliberately small workflow scaffold. It demonstrates route ownership and typed
API usage rather than final visual design.

- `/` shows VeraMove, the pitch, demo status, API health, and workflow links.
- `/intake` creates the synthetic two-bedroom job.
- `/confirm/:jobId` displays key fields and locks the JobSpec.
- `/calls/:jobId` creates three mock calls, shows quote summaries, and starts negotiation.
- `/report/:jobId` ranks vendors and displays evidence counts and rationale.

Every data route begins with a loading state and renders a readable alert when the API fails. A user
can complete the sequence without credentials after starting `python scripts/dev.py`.
