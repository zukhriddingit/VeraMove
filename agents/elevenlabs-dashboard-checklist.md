# ElevenLabs two-agent dashboard checklist

Use this checklist to manually synchronize repository agent configuration version
`2026-07-19.1`. The YAML files are reviewed source manifests; they do not automatically update the
ElevenLabs dashboard. Never copy credentials, destination values, provider IDs, or participant data
into this document.

## Workspace prerequisites

- [ ] Confirm provider credits are available.
- [ ] Confirm the workspace concurrency and daily call limit allow the supervised three-call run.
- [ ] Keep live calling disabled in VeraMove until both agents pass preflight.
- [ ] Use only consenting teammates and fictional customer/vendor facts.
- [ ] Configure a short, nonzero retention period that covers the demo and deletion check.
- [ ] Audio webhook: disabled. VeraMove streams audio on demand instead of accepting pushed bytes.
- [ ] Post-call transcription webhook retries: enabled.

## Agent 1 — VeraMove Intake

- [ ] Display name: `VeraMove Intake`.
- [ ] Prompt/config version: `2026-07-19.1`.
- [ ] Copy `agents/intake/prompt.md` as the system prompt.
- [ ] First message: “Hello, I'm VeraMove's AI intake assistant. This call may be recorded and
      processed by ElevenLabs so I can prepare a moving-request summary. Do you consent to
      continue?”
- [ ] Dynamic variables (all required strings): `job_id`, `intake_session_id`,
      `agent_config_version`.
- [ ] Conversation initiation webhook: enabled for the imported inbound number and pointed at the
      deployed VeraMove authenticated pre-call endpoint.
- [ ] Prompt override in the conversation initiation response: disabled.
- [ ] Audio Saving: enabled.
- [ ] Retention: short and nonzero.
- [ ] Success evaluation: consent obtained; every required field is known or explicitly unknown; an
      accurate complete readback was approved; the agent did not confirm or lock the job.

### Intake Data Collection

Create these 24 identifiers using the exact primitive types from
`agents/intake/data-collection.json`:

| Identifier | Type |
| --- | --- |
| `recording_consent` | boolean |
| `summary_confirmed` | boolean |
| `move_date` | string |
| `date_flexible` | boolean |
| `origin_address_summary` | string |
| `origin_dwelling_type` | string |
| `origin_floors` | integer |
| `origin_stairs` | integer |
| `origin_elevator_access` | boolean |
| `origin_parking_distance_feet` | integer |
| `destination_address_summary` | string |
| `destination_dwelling_type` | string |
| `destination_floors` | integer |
| `destination_stairs` | integer |
| `destination_elevator_access` | boolean |
| `destination_parking_distance_feet` | integer |
| `bedroom_count` | integer |
| `inventory_json` | string |
| `special_items_json` | string |
| `packing` | boolean |
| `disassembly` | boolean |
| `storage` | boolean |
| `storage_days` | integer |
| `insurance_preference` | string |

## Agent 2 — VeraMove Outbound Negotiator

- [ ] Display name: `VeraMove Outbound Negotiator`.
- [ ] Prompt/config version: `2026-07-19.1`.
- [ ] Copy `agents/negotiator/prompt.md`, followed by
      `agents/negotiator/generated-fee-probes.md`, as the system prompt.
- [ ] First message: “Hello, I'm VeraMove's AI assistant calling about a synthetic moving-services
      role-play. This call may be recorded and processed by ElevenLabs. Do you consent to continue?”
- [ ] Dynamic variables (required strings in both modes): `job_id`, `call_id`, `vendor_id`,
      `vendor_name`, `job_spec_version`, `job_spec_json`, `call_mode`, `agent_config_version`.
- [ ] Dynamic variables (required strings only for `call_mode=negotiation`):
      `verified_competitor_quote_id`, `verified_competitor_total`,
      `verified_competitor_evidence_json`, `negotiation_objective`.
- [ ] Allowed `call_mode` values: `quote`, `negotiation`.
- [ ] Conversation initiation webhook: disabled for outbound calls; VeraMove supplies verified
      dynamic variables when initiating each call.
- [ ] Audio Saving: enabled.
- [ ] Retention: the same short, nonzero period used for Intake.
- [ ] Success evaluation: consent obtained; locked facts preserved; every mandatory fee category
      addressed; exactly one supported outcome captured; negotiation uses only verified leverage and
      records a measurable improvement.

### Outbound Data Collection

Create these 14 identifiers using the exact primitive types from
`agents/negotiator/data-collection.json`:

| Identifier | Type |
| --- | --- |
| `recording_consent` | boolean |
| `outcome_type` | string |
| `callback_at` | string |
| `outcome_reason` | string |
| `headline_total` | number |
| `deposit` | number |
| `original_total` | number |
| `negotiated_total` | number |
| `binding_type` | string |
| `availability_status` | string |
| `availability` | string |
| `fee_items_json` | string |
| `addressed_fee_categories_json` | string |
| `concessions_json` | string |

## Shared webhook and release checks

- [ ] Configure only `post_call_transcription` delivery to the deployed
      `/api/webhooks/elevenlabs` HTTPS endpoint.
- [ ] Configure the provider signing secret through dashboard and deployment secret controls; do
      not place it in prompt text or dynamic variables.
- [ ] Enable post-call transcription retries and verify the endpoint returns success only after a
      durable acknowledgement.
- [ ] Confirm the observed dashboard prompt/config version matches `2026-07-19.1` before calling.
- [ ] Confirm Audio Saving is enabled and retention is nonzero on both agents.
- [ ] Confirm exactly two VeraMove agents exist for this workflow—one Intake and one shared Outbound
      Negotiator.
- [ ] Keep the audio webhook disabled; do not configure a separate audio delivery target.
- [ ] Complete one supervised synthetic intake and one operator-only outbound smoke before enabling
      the full three-call run.
