# VeraMove Outbound Negotiator agent

Owner: Prathmesh (GitHub handle pending; see `AGENTS.md`).

This directory is the reviewed source package for the **VeraMove Outbound Negotiator** ElevenLabs
agent. One agent handles both initial quote and evidence-gated negotiation calls. VeraMove selects
the branch through the verified `call_mode` dynamic variable; this is not two separate agents.

## Files

- `agent.yaml` records the shared agent configuration, dynamic variables, mode requirements, first
  message, and success evaluation.
- `prompt.md` defines disclosure, role-play boundaries, quote and negotiation branches, and exact
  supported outcomes.
- `data-collection.json` is the generated 14-field post-call collection definition.
- `generated-fee-probes.md` is generated exclusively from
  `configs/moving.yaml:mandatory_fee_questions` and must be appended to the dashboard prompt.

The repository tools manifest documents VeraMove's trust and write boundaries. The selected demo
architecture resolves verified leverage before a call and canonicalizes results after the signed
post-call webhook; it does not depend on an unreviewed real-time provider tool.

These files do not auto-deploy. Follow `../elevenlabs-dashboard-checklist.md`, then record the active
provider agent ID only in the deployment secret manager.

Regenerate and verify the assets from the repository root:

```bash
.venv/bin/python scripts/generate_agent_assets.py
.venv/bin/python scripts/generate_agent_assets.py --check
```

Never commit credentials, provider IDs, destination values, customer facts, transcripts, or audio.
