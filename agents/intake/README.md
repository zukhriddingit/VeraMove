# VeraMove Intake agent

Owner: Prathmesh (GitHub handle pending; see `AGENTS.md`).

This directory is the reviewed source package for the **VeraMove Intake** ElevenLabs agent. The
agent interviews a customer using fictional role-play facts and produces an unconfirmed voice
`JobSpecV1`. It never confirms the draft, locks a version, calls vendors, or performs a transaction.

## Files

- `agent.yaml` is the repository configuration manifest and records version, first message,
  dynamic variables, success evaluation, and linked assets.
- `prompt.md` is the reviewed system prompt.
- `data-collection.json` is generated from the approved 24-field collection definition.

The manifest is documentation and a drift boundary; it does not deploy itself. Configure or update
the dashboard manually (or through an explicitly reviewed API tool), following
`../elevenlabs-dashboard-checklist.md`.

Regenerate and verify the collection assets from the repository root:

```bash
.venv/bin/python scripts/generate_agent_assets.py
.venv/bin/python scripts/generate_agent_assets.py --check
```

Never place credentials, agent IDs, phone values, customer data, or provider payloads in these files.
