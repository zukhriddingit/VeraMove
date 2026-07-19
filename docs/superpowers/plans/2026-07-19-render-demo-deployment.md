# Render Demo Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy VeraMove's integrated FastAPI backend to a public Render HTTPS service that accepts the incoming frontend origin and signed ElevenLabs post-call webhooks without committing secrets.

**Architecture:** Add strict environment-backed CORS origins while preserving the two local defaults, then describe a single-process Render Python web service in `render.yaml`. Render owns live credentials, TLS, and the public URL; the existing in-memory repository remains intentionally demo-grade and restart-ephemeral.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, pytest, Render Blueprint, ElevenLabs HMAC webhooks.

## Global Constraints

- Keep `APP_MODE=mock` and `LIVE_CALLS_ENABLED=false` as repository defaults.
- Never commit API keys, webhook secrets, phone numbers, populated `.env` files, or real call payloads.
- Allow only explicit HTTP(S) frontend origins; do not use wildcard CORS.
- Run exactly one Uvicorn worker because persistence is process-local memory.
- Do not change canonical Pydantic contracts or OpenAPI route shapes.
- Keep live transcript-to-quote materialization and Supabase persistence out of this deployment.

---

## File Structure

- `services/api/app/core/config.py`: parse and validate explicit CORS origins.
- `services/api/app/main.py`: pass the settings-backed origins to FastAPI's CORS middleware.
- `services/api/tests/test_live_voice.py`: cover safe CORS defaults, explicit origins, and invalid values.
- `services/api/tests/test_api.py`: prove a configured public origin receives the correct preflight header.
- `.python-version`: select the Python 3.13 line on Render.
- `render.yaml`: declare the single Render web service and safe environment defaults.
- `.env.example`: document the CORS variable without a deployment-specific value.
- `README.md`: document public deployment, secret entry, and restart-ephemeral state.

### Task 1: Environment-Backed CORS

**Files:**
- Modify: `services/api/app/core/config.py`
- Modify: `services/api/app/main.py`
- Test: `services/api/tests/test_live_voice.py`
- Test: `services/api/tests/test_api.py`

**Interfaces:**
- Produces: `Settings.cors_allow_origins: tuple[str, ...]`
- Consumes: optional comma-separated `CORS_ALLOW_ORIGINS`

- [ ] **Step 1: Write failing settings tests**

Add these tests to `services/api/tests/test_live_voice.py`:

```python
def test_settings_cors_origins_default_and_explicit_override(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    assert Settings.from_env().cors_allow_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )

    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS",
        " https://veramove-demo.example,https://preview.veramove-demo.example/ ",
    )
    assert Settings.from_env().cors_allow_origins == (
        "https://veramove-demo.example",
        "https://preview.veramove-demo.example",
    )


@pytest.mark.parametrize(
    "value",
    ["*", "https://veramove-demo.example/path", "veramove-demo.example"],
)
def test_settings_reject_invalid_cors_origins(monkeypatch, value):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", value)
    with pytest.raises(ProviderConfigurationError, match="CORS_ALLOW_ORIGINS"):
        Settings.from_env()
```

- [ ] **Step 2: Write the failing CORS preflight test**

Add to `services/api/tests/test_api.py`:

```python
def test_configured_public_origin_passes_cors_preflight(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://veramove-demo.example")
    configured_app = create_app()

    with TestClient(configured_app) as test_client:
        response = test_client.options(
            "/health",
            headers={
                "Origin": "https://veramove-demo.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://veramove-demo.example"
    )
```

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest -q \
  services/api/tests/test_live_voice.py::test_settings_cors_origins_default_and_explicit_override \
  services/api/tests/test_live_voice.py::test_settings_reject_invalid_cors_origins \
  services/api/tests/test_api.py::test_configured_public_origin_passes_cors_preflight
```

Expected: failures because `Settings.cors_allow_origins` does not exist and middleware still uses local constants.

- [ ] **Step 4: Implement strict origin parsing**

In `services/api/app/core/config.py`, import `urlsplit` from `urllib.parse` and add:

```python
DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def _cors_origins_env() -> tuple[str, ...]:
    value = _optional_env("CORS_ALLOW_ORIGINS")
    if value is None:
        return DEFAULT_CORS_ALLOW_ORIGINS
    origins = tuple(
        dict.fromkeys(
            item.strip().rstrip("/")
            for item in value.split(",")
            if item.strip()
        )
    )
    if not origins or "*" in origins:
        raise ProviderConfigurationError(
            "CORS_ALLOW_ORIGINS must contain explicit HTTP(S) origins"
        )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderConfigurationError(
                "CORS_ALLOW_ORIGINS must contain explicit HTTP(S) origins"
            )
    return origins
```

Add this field to `Settings`:

```python
cors_allow_origins: tuple[str, ...] = DEFAULT_CORS_ALLOW_ORIGINS
```

Pass `cors_allow_origins=_cors_origins_env()` from `Settings.from_env()`.

- [ ] **Step 5: Wire the middleware**

Replace the hard-coded `allow_origins` in `services/api/app/main.py` with:

```python
allow_origins=list(settings.cors_allow_origins),
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  services/api/tests/test_live_voice.py \
  services/api/tests/test_api.py \
  services/api/tests/test_webhooks.py
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the CORS change**

```bash
git add services/api/app/core/config.py services/api/app/main.py \
  services/api/tests/test_live_voice.py services/api/tests/test_api.py
git commit -m "feat(api): configure deployment CORS origins"
```

### Task 2: Render Blueprint and Operator Documentation

**Files:**
- Create: `.python-version`
- Create: `render.yaml`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: Render's `PORT` and dashboard-managed environment variables.
- Produces: one service named `veramove-api-demo-zukhriddingit` with `/health` readiness checks.

- [ ] **Step 1: Add the Python version and Blueprint**

Create `.python-version` containing:

```text
3.13
```

Create `render.yaml` containing:

```yaml
services:
  - type: web
    name: veramove-api-demo-zukhriddingit
    runtime: python
    plan: free
    buildCommand: pip install -r services/api/requirements.txt
    startCommand: uvicorn services.api.app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: APP_MODE
        value: mock
      - key: LIVE_CALLS_ENABLED
        value: "false"
      - key: ELEVENLABS_API_KEY
        sync: false
      - key: ELEVENLABS_QUOTE_AGENT_ID
        sync: false
      - key: ELEVENLABS_NEGOTIATOR_AGENT_ID
        sync: false
      - key: ELEVENLABS_PHONE_NUMBER_ID
        sync: false
      - key: ELEVENLABS_WEBHOOK_SECRET
        sync: false
      - key: LIVE_TEST_TO_NUMBER
        sync: false
      - key: CORS_ALLOW_ORIGINS
        sync: false
```

- [ ] **Step 2: Document local and deployed variables**

Add to `.env.example` after `VITE_API_BASE_URL`:

```dotenv
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

Add a `CORS_ALLOW_ORIGINS` row to the README environment table and a `Render demo deployment`
section that states the exact build/start commands, dashboard-only live variables, public webhook
route, one-worker requirement, and restart-ephemeral in-memory limitation.

- [ ] **Step 3: Validate configuration files and documentation tests**

Run:

```bash
.venv/bin/python -c 'import pathlib, yaml; data=yaml.safe_load(pathlib.Path("render.yaml").read_text()); assert data["services"][0]["healthCheckPath"] == "/health"'
.venv/bin/python -m pytest -q services/api/tests/test_documentation.py services/api/tests/test_project_assets.py
git diff --check
```

Expected: all commands exit zero.

- [ ] **Step 4: Commit deployment configuration**

```bash
git add .python-version render.yaml .env.example README.md
git commit -m "chore(deploy): add Render demo service"
```

### Task 3: Regression, Push, and Public Deployment

**Files:**
- Verify only; no additional source file is expected.

**Interfaces:**
- Consumes: GitHub branch `deploy/veramove-demo` and the operator's Render/ElevenLabs sessions.
- Produces: public API origin `https://veramove-api-demo-zukhriddingit.onrender.com` if the requested name is available.

- [ ] **Step 1: Run the repository release gate**

Run:

```bash
.venv/bin/python scripts/check.py
```

Expected: Ruff, pytest, OpenAPI export, frontend generation, TypeScript, Vitest, and Vite build all pass.

- [ ] **Step 2: Confirm no secrets or personal data are staged**

Run:

```bash
git status --short
git diff --check
git grep -n -E '(sk-[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{20,}|AC[a-f0-9]{32})' -- . ':!docs/superpowers/plans/2026-07-19-render-demo-deployment.md'
```

Expected: no secret-like matches and no uncommitted source changes.

- [ ] **Step 3: Push the deployment branch**

```bash
git push -u origin deploy/veramove-demo
```

Expected: GitHub accepts the branch and reports it tracking `origin/deploy/veramove-demo`.

- [ ] **Step 4: Create the Render Blueprint through the dashboard**

Open `https://dashboard.render.com/blueprints`, create a Blueprint from
`zukhriddingit/VeraMove`, select branch `deploy/veramove-demo`, keep the root `render.yaml`, and enter
the requested values in Render's secret controls. Do not paste any secret into chat, source files, or
terminal history. Create the service and wait for the `/health` check to pass.

- [ ] **Step 5: Smoke-test the public backend in mock mode**

Run:

```bash
curl -fsS https://veramove-api-demo-zukhriddingit.onrender.com/health
curl -fsS -o /dev/null -w '%{http_code}\n' \
  https://veramove-api-demo-zukhriddingit.onrender.com/docs
```

Expected: health reports `mode: mock`; docs returns `200`.

- [ ] **Step 6: Enable the reviewed live configuration**

In Render's Environment page, set `APP_MODE=live`, `LIVE_CALLS_ENABLED=true`, and the existing
ElevenLabs agent, phone-number, webhook, and opted-in destination values. Save and deploy. Confirm
`GET /health` now reports `mode: live` before initiating any call.

- [ ] **Step 7: Configure and test the signed webhook**

In ElevenLabs Developers > Webhooks, create a post-call transcription webhook for:

```text
https://veramove-api-demo-zukhriddingit.onrender.com/api/webhooks/elevenlabs
```

Copy the generated shared secret directly into Render's `ELEVENLABS_WEBHOOK_SECRET`, redeploy, then
place exactly one controlled synthetic test call. Confirm the webhook receives HTTP 200 and
`GET /api/jobs/{job_id}/events` contains one safe `post_call_transcription` event for the matched
conversation.

- [ ] **Step 8: Hand the backend URL to the frontend owner**

Provide the public API URL as `VITE_API_BASE_URL`, receive the exact frontend HTTPS origin, set it as
Render's `CORS_ALLOW_ORIGINS`, and verify the browser preflight includes that exact origin.
