-- Durable, no-PII correlation and exactly-once live voice materialization.

alter table jobs
    add column if not exists aggregate_revision bigint not null default 0;

alter table call_attempts
    add column if not exists kind text,
    add column if not exists job_spec_version text,
    add column if not exists destination_slot smallint,
    add column if not exists expected_agent_id text,
    add column if not exists agent_config_version text,
    add column if not exists call_mode text,
    add column if not exists job_spec_sha256 text,
    add column if not exists negotiation_context jsonb,
    add column if not exists provider_version_id text;

update call_attempts
set
    kind = coalesce(kind, payload ->> 'kind', 'quote'),
    job_spec_version = coalesce(
        job_spec_version,
        payload ->> 'job_spec_version',
        payload #>> '{job_spec_snapshot,version}',
        '1.0'
    ),
    destination_slot = coalesce(
        destination_slot,
        nullif(payload ->> 'destination_slot', '')::smallint,
        0
    ),
    expected_agent_id = coalesce(
        expected_agent_id,
        payload ->> 'expected_agent_id',
        'legacy-unconfigured-agent'
    ),
    agent_config_version = coalesce(
        agent_config_version,
        payload ->> 'agent_config_version',
        'legacy-unconfigured-version'
    ),
    call_mode = coalesce(call_mode, payload ->> 'call_mode', payload ->> 'kind', 'quote'),
    job_spec_sha256 = coalesce(
        job_spec_sha256,
        payload ->> 'job_spec_sha256',
        repeat('0', 64)
    ),
    negotiation_context = coalesce(
        negotiation_context,
        nullif(payload -> 'negotiation_context', 'null'::jsonb),
        '{}'::jsonb
    );

alter table call_attempts
    alter column kind set not null,
    alter column job_spec_version set not null,
    alter column destination_slot set not null,
    alter column expected_agent_id set not null,
    alter column agent_config_version set not null,
    alter column call_mode set not null,
    alter column job_spec_sha256 set not null,
    alter column negotiation_context set not null;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'call_attempts_live_audit_check'
    ) then
        alter table call_attempts
            add constraint call_attempts_live_audit_check check (
                kind in ('quote', 'negotiation')
                and call_mode = kind
                and destination_slot between 0 and 2
                and job_spec_sha256 ~ '^[a-f0-9]{64}$'
                and char_length(expected_agent_id) between 1 and 200
                and char_length(agent_config_version) between 1 and 80
                and (
                    (kind = 'quote' and negotiation_context = '{}'::jsonb)
                    or
                    (kind = 'negotiation' and negotiation_context <> '{}'::jsonb)
                )
            );
    end if;
end
$$;

create unique index if not exists call_attempts_one_workflow_slot_idx
    on call_attempts (job_id, vendor_id, kind, job_spec_version);

create table if not exists intake_sessions (
    id uuid primary key,
    reserved_job_id uuid not null unique,
    provider_call_key_hash text unique,
    conversation_id text unique,
    expected_agent_id text not null,
    agent_config_version text not null,
    status text not null check (
        status in ('pending', 'in_progress', 'completed', 'failed')
    ),
    failure_code text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    check (provider_call_key_hash is null or provider_call_key_hash ~ '^[a-f0-9]{64}$'),
    check (char_length(expected_agent_id) between 1 and 200),
    check (char_length(agent_config_version) between 1 and 80),
    check (
        (status = 'completed' and completed_at is not null)
        or
        (status <> 'completed')
    )
);

create table if not exists voice_webhook_receipts (
    idempotency_key text primary key,
    event_type text not null,
    status text not null check (status in ('processing', 'processed', 'failed')),
    lease_token uuid,
    lease_expires_at timestamptz,
    retryable boolean not null default false,
    failure_code text,
    attempt_count integer not null default 1 check (attempt_count between 1 and 100),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    processed_at timestamptz,
    check (
        (status = 'processing' and lease_token is not null and lease_expires_at is not null)
        or
        (status <> 'processing' and lease_token is null and lease_expires_at is null)
    )
);

alter table intake_sessions enable row level security;
alter table voice_webhook_receipts enable row level security;
revoke all on intake_sessions, voice_webhook_receipts from anon, authenticated;
grant select, insert, update, delete on intake_sessions, voice_webhook_receipts to service_role;

create or replace function veramove_claim_voice_webhook_receipt(
    p_idempotency_key text,
    p_event_type text,
    p_lease_token uuid,
    p_lease_expires_at timestamptz,
    p_now timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    current_receipt voice_webhook_receipts%rowtype;
begin
    if char_length(p_idempotency_key) not between 1 and 200
       or char_length(p_event_type) not between 1 and 120
       or p_lease_expires_at <= p_now then
        raise exception 'invalid voice receipt claim';
    end if;

    insert into voice_webhook_receipts (
        idempotency_key, event_type, status, lease_token, lease_expires_at,
        retryable, created_at, updated_at
    ) values (
        p_idempotency_key, p_event_type, 'processing', p_lease_token,
        p_lease_expires_at, false, p_now, p_now
    )
    on conflict (idempotency_key) do nothing;

    select * into current_receipt
    from voice_webhook_receipts
    where idempotency_key = p_idempotency_key
    for update;

    if current_receipt.status = 'processed' then
        return jsonb_build_object('claimed', false, 'processed', true);
    end if;
    if current_receipt.status = 'processing'
       and current_receipt.lease_token = p_lease_token then
        return jsonb_build_object('claimed', true, 'processed', false);
    end if;
    if current_receipt.status = 'processing'
       and current_receipt.lease_expires_at > p_now then
        return jsonb_build_object('claimed', false, 'processed', false);
    end if;
    if current_receipt.status = 'failed' and not current_receipt.retryable then
        return jsonb_build_object('claimed', false, 'processed', false);
    end if;

    update voice_webhook_receipts
    set status = 'processing', lease_token = p_lease_token,
        lease_expires_at = p_lease_expires_at, retryable = false,
        failure_code = null, attempt_count = attempt_count + 1, updated_at = p_now
    where idempotency_key = p_idempotency_key;
    return jsonb_build_object('claimed', true, 'processed', false);
end
$$;

create or replace function veramove_fail_voice_webhook_receipt(
    p_idempotency_key text,
    p_lease_token uuid,
    p_failure_code text,
    p_retryable boolean,
    p_now timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
begin
    if char_length(p_failure_code) not between 1 and 80 then
        raise exception 'invalid voice receipt failure code';
    end if;
    update voice_webhook_receipts
    set status = 'failed', lease_token = null, lease_expires_at = null,
        retryable = p_retryable, failure_code = p_failure_code, updated_at = p_now
    where idempotency_key = p_idempotency_key
      and status = 'processing'
      and lease_token = p_lease_token;
    if not found then
        raise exception 'voice receipt lease mismatch';
    end if;
    return jsonb_build_object('failed', true, 'retryable', p_retryable);
end
$$;

create or replace function veramove_finalize_voice_webhook(
    p_idempotency_key text,
    p_lease_token uuid,
    p_attempt jsonb,
    p_call jsonb,
    p_quote jsonb,
    p_evidence jsonb,
    p_job jsonb,
    p_event jsonb,
    p_now timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    forbidden_pattern constant text := '"(analysis|transcript|raw_body|raw_payload|phone|phone_number|from_number|to_number|audio|api_key|secret)"[[:space:]]*:';
    receipt voice_webhook_receipts%rowtype;
begin
    select * into receipt
    from voice_webhook_receipts
    where idempotency_key = p_idempotency_key
    for update;
    if receipt.status = 'processed' then
        return jsonb_build_object('processed', true, 'duplicate', true);
    end if;
    if receipt.status <> 'processing' or receipt.lease_token <> p_lease_token then
        raise exception 'voice receipt lease mismatch';
    end if;
    if concat(p_attempt, p_call, p_quote, p_evidence, p_job, p_event)
       ~* forbidden_pattern then
        raise exception 'unsafe voice materialization payload';
    end if;
    if jsonb_typeof(p_evidence) <> 'array' then
        raise exception 'voice evidence payload must be an array';
    end if;

    update call_attempts
    set status = p_attempt ->> 'status',
        provider_version_id = p_attempt ->> 'provider_version_id',
        payload = p_attempt -> 'payload',
        updated_at = p_now
    where id = (p_attempt ->> 'id')::uuid;
    if not found then
        raise exception 'voice call attempt not found';
    end if;

    insert into calls (
        id, job_id, vendor_id, external_call_id, idempotency_key, status,
        outcome_type, record_type, data_classification, payload, created_at, updated_at
    ) values (
        (p_call ->> 'id')::uuid, (p_call ->> 'job_id')::uuid,
        (p_call ->> 'vendor_id')::uuid, p_call ->> 'external_call_id',
        p_call ->> 'idempotency_key', p_call ->> 'status',
        p_call ->> 'outcome_type', 'canonical', p_call ->> 'data_classification',
        p_call -> 'payload', (p_call ->> 'created_at')::timestamptz, p_now
    ) on conflict (id) do update set
        status = excluded.status, outcome_type = excluded.outcome_type,
        payload = excluded.payload, updated_at = excluded.updated_at;

    if p_quote is not null and p_quote <> 'null'::jsonb then
        insert into quotes (
            id, job_id, vendor_id, call_id, quote_version, job_spec_version,
            verification_status, provisional_payload, verified_payload, provenance,
            manually_fabricated, data_classification, payload, created_at, updated_at
        ) values (
            (p_quote ->> 'id')::uuid, (p_quote ->> 'job_id')::uuid,
            (p_quote ->> 'vendor_id')::uuid, (p_quote ->> 'call_id')::uuid,
            p_quote ->> 'quote_version', p_quote ->> 'job_spec_version',
            p_quote ->> 'verification_status', p_quote -> 'provisional_payload',
            p_quote -> 'verified_payload', p_quote -> 'provenance',
            coalesce((p_quote ->> 'manually_fabricated')::boolean, false),
            p_quote ->> 'data_classification', p_quote -> 'payload', p_now, p_now
        ) on conflict (id) do update set
            verification_status = excluded.verification_status,
            verified_payload = excluded.verified_payload,
            payload = excluded.payload, updated_at = excluded.updated_at;

        insert into transcript_evidence (
            id, job_id, call_id, verification_status, recording_url,
            data_classification, payload, created_at
        )
        select
            (item ->> 'id')::uuid, (item ->> 'job_id')::uuid,
            (item ->> 'call_id')::uuid, item ->> 'verification_status',
            item ->> 'recording_url', item ->> 'data_classification',
            item -> 'payload', p_now
        from jsonb_array_elements(p_evidence) as item
        on conflict (id) do update set
            verification_status = excluded.verification_status,
            recording_url = excluded.recording_url,
            payload = excluded.payload;
    end if;

    update jobs
    set state = p_job ->> 'state', payload = p_job -> 'payload',
        aggregate_revision = aggregate_revision + 1, updated_at = p_now
    where id = (p_job ->> 'id')::uuid
      and aggregate_revision = (p_job ->> 'expected_revision')::bigint;
    if not found then
        raise exception 'voice aggregate revision conflict';
    end if;

    insert into event_log (
        id, job_id, source, event_type, idempotency_key,
        data_classification, payload, created_at
    ) values (
        (p_event ->> 'id')::uuid, (p_event ->> 'job_id')::uuid,
        'veramove', p_event ->> 'event_type', p_event ->> 'idempotency_key',
        p_event ->> 'data_classification', p_event -> 'payload', p_now
    ) on conflict (idempotency_key) do nothing;

    update voice_webhook_receipts
    set status = 'processed', lease_token = null, lease_expires_at = null,
        retryable = false, failure_code = null, processed_at = p_now, updated_at = p_now
    where idempotency_key = p_idempotency_key and lease_token = p_lease_token;
    return jsonb_build_object('processed', true, 'duplicate', false);
end
$$;

revoke all on function veramove_claim_voice_webhook_receipt(text, text, uuid, timestamptz, timestamptz)
    from public, anon, authenticated;
revoke all on function veramove_fail_voice_webhook_receipt(text, uuid, text, boolean, timestamptz)
    from public, anon, authenticated;
revoke all on function veramove_finalize_voice_webhook(
    text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, timestamptz
) from public, anon, authenticated;
grant execute on function veramove_claim_voice_webhook_receipt(text, text, uuid, timestamptz, timestamptz)
    to service_role;
grant execute on function veramove_fail_voice_webhook_receipt(text, uuid, text, boolean, timestamptz)
    to service_role;
grant execute on function veramove_finalize_voice_webhook(
    text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, timestamptz
) to service_role;
