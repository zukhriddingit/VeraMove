# Contributing to VeraMove

Run `python scripts/bootstrap.py` after cloning, create a member-scoped branch from `main`, and read
`AGENTS.md` before editing. Keep changes within temporary directory ownership and open a focused PR.

For contract changes, update Pydantic first, regenerate OpenAPI and TypeScript types, and include all
affected tests. For fixture changes, keep every record clearly synthetic and preserve the three
documented vendor behaviors.

Before requesting review:

```bash
python scripts/check.py
```

Include the reason for the change, test evidence, contract impact, and screenshots for visible UI
changes. Do not include secrets, real personal data, recordings, deployment steps, or production
integration credentials.
