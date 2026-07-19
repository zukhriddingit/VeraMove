# ElevenLabs Provider Sync Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make VeraMove's checked-in ElevenLabs assets and read-only live preflight match the reviewed two-agent provider setup while keeping credentials, provider resource IDs, and live mutations out of source control.

**Architecture:** Human-reviewable role manifests and prompts remain the source of truth. The asset generator produces stable dashboard artifacts plus a pure conversion to ElevenLabs' keyed Data Collection API object. The live preflight only reads provider resources and collapses them to safe booleans/counts before reporting; it never configures an agent, webhook, phone number, or secret.

**Tech Stack:** Python 3.11+, YAML/JSON/Markdown assets, `httpx`, `pytest`, Ruff.

## Global Constraints

- Do not call a live provider or mutate Render, ElevenLabs, Twilio, or Supabase.
- Do not add secrets, phone numbers, provider IDs, provider URLs, transcripts, or recordings.
- Do not edit orchestration, repository, contract, or frontend code.
- Preserve unrelated working-tree edits and do not stage or commit this plan's changes.

---

### Task 1: Make role assets provider-accurate

**Files:**
- Modify: `agents/intake/agent.yaml`
- Modify: `agents/negotiator/agent.yaml`
- Modify: `agents/intake/prompt.md`
- Modify: `agents/negotiator/prompt.md`
- Test: `services/api/tests/test_project_assets.py`

- [x] Replace conceptual tool-name deployment claims with an empty `provider_tool_ids` list and a clearly separate reference to the backend boundary document.
- [x] Add `{{variable_name}}` runtime-context placeholders for every declared variable without instructing either agent to speak identifiers.
- [x] Keep the negotiator's quote and negotiation behavior driven by verified pre-call values, with empty negotiation-only values ignored during quote mode.
- [x] Add tests for exact placeholder coverage, no provider tools, and the repository marker/provider-ID distinction.

### Task 2: Generate exact Data Collection API objects

**Files:**
- Modify: `scripts/generate_agent_assets.py`
- Test: `services/api/tests/test_project_assets.py`
- Test: `services/api/tests/test_scripts.py`

- [x] Add a pure validation/transform function that converts reviewed list-shaped fields into the ElevenLabs object keyed by field identifier.
- [x] Reject duplicate identifiers, empty descriptions, and unsupported provider field types.
- [x] Add a print-only CLI mode for the Intake or Outbound provider payload while leaving generated files unchanged.
- [x] Test the exact payload shape and generator determinism.

### Task 3: Make the manual provider checklist unambiguous

**Files:**
- Modify: `agents/elevenlabs-dashboard-checklist.md`
- Modify: `docs/backend-voice-runbook.md`
- Test: `services/api/tests/test_project_assets.py`

- [x] Document a workspace secret locator for the pre-call header and Intake-only conversation-initiation enablement.
- [x] Document a shared HMAC post-call webhook with retries and both `transcript` and `call_initiation_failure` events.
- [x] Distinguish inbound phone assignment to Intake from reuse of the same phone-number ID for outbound initiations.
- [x] Require a version description, capture of opaque `version_id`/`branch_id`, one-to-seven-day agent retention, and separate review of Twilio recording retention.
- [x] Keep provider tools omitted until reviewed provider tool IDs exist.

### Task 4: Extend the read-only live preflight

**Files:**
- Modify: `scripts/live_voice_preflight.py`
- Test: `services/api/tests/test_scripts.py`

- [x] Read both agents, their current versions, workspace settings/webhooks, the configured phone number, and subscription capacity.
- [x] Verify version descriptions, prompt placeholders, omitted provider tools, Intake-only pre-call enablement, secret-locator configuration, post-call events/attachment, and inbound phone assignment. Retry remains a required manual check because ElevenLabs' documented list response does not expose it.
- [x] Report only booleans, counts, and one-way identifier hashes; never surface raw payloads or provider locators.
- [x] Fail closed on any configuration drift or provider read error.

### Task 5: Verify focused scope

**Files:**
- Test: `agents/**`
- Test: `scripts/generate_agent_assets.py`
- Test: `scripts/live_voice_preflight.py`
- Test: `services/api/tests/test_project_assets.py`
- Test: `services/api/tests/test_scripts.py`

- [x] Run `python scripts/generate_agent_assets.py --check`.
- [x] Run focused pytest for project assets and scripts.
- [x] Run Ruff on all changed Python files.
- [x] Inspect the final diff for provider writes, secret-like values, real PII, and out-of-scope edits.
