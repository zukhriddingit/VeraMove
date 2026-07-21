-- Add structured, resumable voice intake without persisting transcripts or phone data.

alter table public.intake_sessions
    add column if not exists data_mode text not null default 'supervised_role_play',
    add column if not exists partial_job_spec jsonb,
    add column if not exists base_job_spec jsonb,
    add column if not exists missing_fields jsonb not null default '[]'::jsonb,
    add column if not exists terminal_reason text,
    add column if not exists recovery_action text,
    add column if not exists recovery_target_id uuid,
    add column if not exists resumed_from_session_id uuid;

alter table public.intake_sessions
    drop constraint if exists intake_sessions_status_check;
alter table public.intake_sessions
    add constraint intake_sessions_status_check
    check (status in ('pending', 'in_progress', 'incomplete', 'completed', 'failed'));

alter table public.intake_sessions
    drop constraint if exists intake_sessions_data_mode_check;
alter table public.intake_sessions
    add constraint intake_sessions_data_mode_check
    check (data_mode in ('supervised_role_play', 'real_redacted'));

alter table public.intake_sessions
    drop constraint if exists intake_sessions_partial_shape_check;
alter table public.intake_sessions
    add constraint intake_sessions_partial_shape_check
    check (
        (
            status = 'incomplete'
            and conversation_id is not null
            and partial_job_spec is not null
            and jsonb_typeof(partial_job_spec) = 'object'
            and jsonb_typeof(missing_fields) = 'array'
            and char_length(terminal_reason) between 1 and 80
            and failure_code is null
            and completed_at is null
        )
        or
        (
            status <> 'incomplete'
            and partial_job_spec is null
            and missing_fields = '[]'::jsonb
            and terminal_reason is null
            and recovery_action is null
            and recovery_target_id is null
        )
    );

alter table public.intake_sessions
    drop constraint if exists intake_sessions_resume_shape_check;
alter table public.intake_sessions
    add constraint intake_sessions_resume_shape_check
    check (
        (base_job_spec is null and resumed_from_session_id is null)
        or
        (
            base_job_spec is not null
            and jsonb_typeof(base_job_spec) = 'object'
            and resumed_from_session_id is not null
        )
    );

alter table public.intake_sessions
    drop constraint if exists intake_sessions_recovery_shape_check;
alter table public.intake_sessions
    add constraint intake_sessions_recovery_shape_check
    check (
        (recovery_action is null and recovery_target_id is null)
        or
        (
            status = 'incomplete'
            and recovery_action in ('resume', 'manual')
            and recovery_target_id is not null
        )
    );

alter table public.intake_sessions
    drop constraint if exists intake_sessions_structured_payload_safety_check;
alter table public.intake_sessions
    add constraint intake_sessions_structured_payload_safety_check
    check (
        concat(partial_job_spec, base_job_spec)
            !~* '"(analysis|transcript|raw_body|raw_payload|phone|phone_number|from_number|to_number|audio|api_key|secret)"[[:space:]]*:'
        and concat(partial_job_spec, base_job_spec) !~ '\+[1-9][0-9]{7,14}'
    );

create index if not exists intake_sessions_resumed_from_idx
    on public.intake_sessions (resumed_from_session_id)
    where resumed_from_session_id is not null;

-- Keep the existing seven-argument function for old application instances. New instances call
-- this schema-versioned overload, which delegates completed/failed results to the proven function
-- and handles the new incomplete terminal state atomically.
create or replace function public.veramove_finalize_voice_intake_webhook(
    p_idempotency_key text,
    p_lease_token uuid,
    p_schema_version text,
    p_kind text,
    p_session jsonb,
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
    phone_pattern constant text := '\+[1-9][0-9]{7,14}';
    receipt public.voice_webhook_receipts%rowtype;
    current_session public.intake_sessions%rowtype;
begin
    if p_schema_version is distinct from '2026-07-21.2' then
        raise exception 'unsupported voice intake schema version';
    end if;
    if p_kind in ('completed', 'failed') then
        return public.veramove_finalize_voice_intake_webhook(
            p_idempotency_key,
            p_lease_token,
            p_kind,
            p_session,
            p_job,
            p_event,
            p_now
        );
    end if;
    if p_idempotency_key is null
       or char_length(p_idempotency_key) not between 1 and 200
       or p_lease_token is null
       or p_kind is distinct from 'incomplete'
       or p_session is null
       or jsonb_typeof(p_session) <> 'object'
       or p_job is not null
       or p_event is null
       or jsonb_typeof(p_event) <> 'object'
       or p_now is null then
        raise exception 'invalid incomplete voice intake payload';
    end if;
    if concat(p_session, p_event) ~* forbidden_pattern
       or concat(p_session, p_event) ~ phone_pattern then
        raise exception 'unsafe incomplete voice intake payload';
    end if;

    select * into receipt
    from public.voice_webhook_receipts
    where idempotency_key = p_idempotency_key
    for update;
    if not found then
        raise exception 'voice receipt not found';
    end if;
    if receipt.status = 'processed' then
        return jsonb_build_object('processed', true, 'duplicate', true);
    end if;
    if receipt.status <> 'processing'
       or receipt.lease_token <> p_lease_token
       or receipt.lease_expires_at <= p_now
       or receipt.event_type is distinct from p_event ->> 'event_type' then
        raise exception 'voice receipt lease mismatch';
    end if;

    select * into current_session
    from public.intake_sessions
    where id = (p_session ->> 'id')::uuid
    for update;
    if not found then
        raise exception 'voice intake session not found';
    end if;
    if current_session.reserved_job_id::text
           is distinct from p_session ->> 'reserved_job_id'
       or current_session.provider_call_key_hash
           is distinct from p_session ->> 'provider_call_key_hash'
       or current_session.expected_agent_id
           is distinct from p_session ->> 'expected_agent_id'
       or current_session.agent_config_version
           is distinct from p_session ->> 'agent_config_version'
       or current_session.data_mode is distinct from p_session ->> 'data_mode'
       or current_session.created_at
           is distinct from (p_session ->> 'created_at')::timestamptz
       or current_session.recovery_action is not null
       or (
           current_session.conversation_id is not null
           and current_session.conversation_id
               is distinct from p_session ->> 'conversation_id'
       )
       or (p_session ->> 'updated_at')::timestamptz < current_session.updated_at then
        raise exception 'voice intake session identity mismatch';
    end if;
    if p_session ->> 'status' <> 'incomplete'
       or p_session ->> 'conversation_id' is null
       or p_session ->> 'failure_code' is not null
       or p_session ->> 'completed_at' is not null
       or p_session ->> 'terminal_reason' is null
       or p_session -> 'partial_job_spec' is null
       or jsonb_typeof(p_session -> 'partial_job_spec') <> 'object'
       or jsonb_typeof(p_session -> 'missing_fields') <> 'array'
       or p_session -> 'partial_job_spec' ->> 'job_id'
           is distinct from p_session ->> 'reserved_job_id'
       or coalesce((p_session -> 'partial_job_spec' ->> 'confirmed')::boolean, false)
       or p_session -> 'partial_job_spec' ->> 'confirmed_at' is not null
       or p_session -> 'partial_job_spec' ->> 'locked_version' is not null
       or p_session -> 'partial_job_spec' ->> 'intake_source' <> 'voice'
       or (
           p_session ->> 'data_mode' = 'supervised_role_play'
           and p_session -> 'partial_job_spec' ->> 'data_classification' <> 'role_play'
       )
       or (
           p_session ->> 'data_mode' = 'real_redacted'
           and p_session -> 'partial_job_spec' ->> 'data_classification' <> 'real_redacted'
       )
       or exists (
           select 1 from public.jobs
           where id = current_session.reserved_job_id
       ) then
        raise exception 'invalid incomplete voice intake state';
    end if;

    update public.intake_sessions
    set conversation_id = p_session ->> 'conversation_id',
        status = 'incomplete',
        partial_job_spec = p_session -> 'partial_job_spec',
        missing_fields = p_session -> 'missing_fields',
        terminal_reason = p_session ->> 'terminal_reason',
        updated_at = (p_session ->> 'updated_at')::timestamptz
    where id = current_session.id
      and status in ('pending', 'in_progress', 'incomplete')
      and recovery_action is null;
    if not found then
        raise exception 'voice intake terminal state conflict';
    end if;

    update public.voice_webhook_receipts
    set status = 'processed', lease_token = null, lease_expires_at = null,
        retryable = false, failure_code = null, processed_at = p_now, updated_at = p_now
    where idempotency_key = p_idempotency_key
      and status = 'processing'
      and lease_token = p_lease_token
      and lease_expires_at > p_now;
    if not found then
        raise exception 'voice receipt lease mismatch';
    end if;
    return jsonb_build_object('processed', true, 'duplicate', false);
end
$$;

create or replace function public.veramove_claim_intake_resume(
    p_session_id uuid,
    p_child jsonb,
    p_now timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    forbidden_pattern constant text := '"(analysis|transcript|raw_body|raw_payload|phone|phone_number|from_number|to_number|audio|api_key|secret)"[[:space:]]*:';
    phone_pattern constant text := '\+[1-9][0-9]{7,14}';
    source_session public.intake_sessions%rowtype;
    child_session public.intake_sessions%rowtype;
begin
    if p_session_id is null
       or p_child is null
       or jsonb_typeof(p_child) <> 'object'
       or p_now is null
       or p_child::text ~* forbidden_pattern
       or p_child::text ~ phone_pattern then
        raise exception 'invalid intake resume payload';
    end if;
    select * into source_session
    from public.intake_sessions
    where id = p_session_id
    for update;
    if not found then
        raise exception 'intake resume source not found';
    end if;
    if source_session.recovery_action = 'resume' then
        select * into child_session
        from public.intake_sessions
        where id = source_session.recovery_target_id;
        if not found then
            raise exception 'intake resume target missing';
        end if;
        return to_jsonb(child_session);
    end if;
    if source_session.status <> 'incomplete'
       or source_session.recovery_action is not null
       or source_session.partial_job_spec is null
       or p_child ->> 'status' <> 'pending'
       or p_child ->> 'conversation_id' is not null
       or p_child ->> 'provider_call_key_hash' is not null
       or p_child ->> 'data_mode' is distinct from source_session.data_mode
       or p_child ->> 'expected_agent_id' is distinct from source_session.expected_agent_id
       or p_child ->> 'agent_config_version'
           is distinct from source_session.agent_config_version
       or p_child ->> 'resumed_from_session_id' is distinct from source_session.id::text
       or p_child -> 'base_job_spec' is null
       or jsonb_typeof(p_child -> 'base_job_spec') <> 'object'
       or (p_child -> 'base_job_spec') - 'job_id'
           is distinct from source_session.partial_job_spec - 'job_id'
       or p_child -> 'base_job_spec' ->> 'job_id'
           is distinct from p_child ->> 'reserved_job_id'
       or (p_child ->> 'created_at')::timestamptz is distinct from p_now
       or (p_child ->> 'updated_at')::timestamptz is distinct from p_now
       or exists (
           select 1 from public.jobs
           where id = (p_child ->> 'reserved_job_id')::uuid
       ) then
        raise exception 'intake resume conflict';
    end if;

    insert into public.intake_sessions (
        id, reserved_job_id, provider_call_key_hash, conversation_id,
        expected_agent_id, agent_config_version, data_mode, status,
        partial_job_spec, base_job_spec, missing_fields, terminal_reason,
        recovery_action, recovery_target_id, resumed_from_session_id,
        failure_code, created_at, updated_at, completed_at,
        browser_credential_issued_at
    ) values (
        (p_child ->> 'id')::uuid,
        (p_child ->> 'reserved_job_id')::uuid,
        null,
        null,
        p_child ->> 'expected_agent_id',
        p_child ->> 'agent_config_version',
        p_child ->> 'data_mode',
        'pending',
        null,
        p_child -> 'base_job_spec',
        '[]'::jsonb,
        null,
        null,
        null,
        p_session_id,
        null,
        p_now,
        p_now,
        null,
        null
    ) returning * into child_session;

    update public.intake_sessions
    set recovery_action = 'resume',
        recovery_target_id = child_session.id,
        updated_at = p_now
    where id = source_session.id
      and status = 'incomplete'
      and recovery_action is null;
    if not found then
        raise exception 'intake resume conflict';
    end if;
    return to_jsonb(child_session);
end
$$;

create or replace function public.veramove_finish_intake_manually(
    p_session_id uuid,
    p_job jsonb,
    p_now timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    forbidden_pattern constant text := '"(analysis|transcript|raw_body|raw_payload|phone|phone_number|from_number|to_number|audio|api_key|secret)"[[:space:]]*:';
    phone_pattern constant text := '\+[1-9][0-9]{7,14}';
    source_session public.intake_sessions%rowtype;
    canonical_job public.jobs%rowtype;
begin
    if p_session_id is null
       or p_job is null
       or jsonb_typeof(p_job) <> 'object'
       or p_now is null
       or p_job::text ~* forbidden_pattern
       or p_job::text ~ phone_pattern then
        raise exception 'invalid manual intake payload';
    end if;
    select * into source_session
    from public.intake_sessions
    where id = p_session_id
    for update;
    if not found then
        raise exception 'manual intake source not found';
    end if;
    if source_session.recovery_action = 'manual' then
        select * into canonical_job
        from public.jobs
        where id = source_session.recovery_target_id;
        if not found then
            raise exception 'manual intake target missing';
        end if;
        return to_jsonb(canonical_job);
    end if;
    if source_session.status <> 'incomplete'
       or source_session.recovery_action is not null
       or source_session.partial_job_spec is null
       or p_job ->> 'id' is distinct from source_session.reserved_job_id::text
       or p_job ->> 'state' <> 'intake_complete'
       or p_job ->> 'confirmed_at' is not null
       or p_job ->> 'locked_job_spec_version' is not null
       or p_job -> 'payload' -> 'job_spec' is distinct from source_session.partial_job_spec
       or jsonb_array_length(p_job -> 'payload' -> 'calls') <> 0
       or jsonb_array_length(p_job -> 'payload' -> 'quotes') <> 0
       or p_job -> 'payload' -> 'recommendation' <> 'null'::jsonb
       or (p_job ->> 'created_at')::timestamptz is distinct from p_now
       or (p_job ->> 'updated_at')::timestamptz is distinct from p_now then
        raise exception 'manual intake conflict';
    end if;

    insert into public.jobs (
        id, job_spec_version, state, confirmed_at, locked_job_spec_version,
        data_classification, payload, created_at, updated_at
    ) values (
        (p_job ->> 'id')::uuid,
        p_job ->> 'job_spec_version',
        p_job ->> 'state',
        null,
        null,
        p_job ->> 'data_classification',
        p_job -> 'payload',
        p_now,
        p_now
    ) returning * into canonical_job;

    update public.intake_sessions
    set recovery_action = 'manual',
        recovery_target_id = canonical_job.id,
        updated_at = p_now
    where id = source_session.id
      and status = 'incomplete'
      and recovery_action is null;
    if not found then
        raise exception 'manual intake conflict';
    end if;
    return to_jsonb(canonical_job);
end
$$;

revoke all on function public.veramove_finalize_voice_intake_webhook(
    text, uuid, text, text, jsonb, jsonb, jsonb, timestamptz
) from public, anon, authenticated;
revoke all on function public.veramove_claim_intake_resume(uuid, jsonb, timestamptz)
    from public, anon, authenticated;
revoke all on function public.veramove_finish_intake_manually(uuid, jsonb, timestamptz)
    from public, anon, authenticated;

grant execute on function public.veramove_finalize_voice_intake_webhook(
    text, uuid, text, text, jsonb, jsonb, jsonb, timestamptz
) to service_role;
grant execute on function public.veramove_claim_intake_resume(uuid, jsonb, timestamptz)
    to service_role;
grant execute on function public.veramove_finish_intake_manually(uuid, jsonb, timestamptz)
    to service_role;

-- Official-business destinations are server-owned and require affirmative AI-call and recording
-- consent. Raw numbers exist only in this protected authorization table; attempts and events keep
-- the HMAC hash and authorization UUID instead.
create table if not exists public.vendor_call_authorizations (
    id uuid primary key,
    job_id uuid not null references public.jobs(id) on delete cascade,
    job_spec_version text not null check (job_spec_version = '1.0'),
    job_spec_sha256 text not null check (job_spec_sha256 ~ '^[a-f0-9]{64}$'),
    vendor_id uuid not null,
    contact_id uuid not null,
    normalized_number text not null check (normalized_number ~ '^\+1[2-9][0-9]{9}$'),
    display_number text not null check (display_number ~ '^\([2-9][0-9]{2}\) [0-9]{3}-[0-9]{4}$'),
    number_hash text not null check (number_hash ~ '^[a-f0-9]{64}$'),
    recipient_timezone text not null check (char_length(recipient_timezone) between 1 and 64),
    consent_method text not null check (
        consent_method in (
            'direct_recipient_opt_in',
            'existing_business_relationship_confirmation',
            'provider_test_destination'
        )
    ),
    consent_evidence_reference text not null check (
        consent_evidence_reference ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$'
    ),
    consented_at timestamptz not null,
    ai_call_consented boolean not null check (ai_call_consented),
    recording_consented boolean not null check (recording_consented),
    source_url text not null check (source_url ~ '^https://'),
    created_at timestamptz not null,
    check (consented_at <= created_at),
    unique (job_id, job_spec_version, vendor_id),
    unique (job_id, job_spec_version, number_hash)
);

create index if not exists vendor_call_authorizations_job_idx
    on public.vendor_call_authorizations (job_id, job_spec_version);

create table if not exists public.vendor_call_suppressions (
    id uuid primary key,
    number_hash text not null unique check (number_hash ~ '^[a-f0-9]{64}$'),
    reason text not null check (
        reason in ('recipient_opt_out', 'manual_block', 'invalid_destination')
    ),
    created_at timestamptz not null
);

alter table public.vendor_call_authorizations enable row level security;
alter table public.vendor_call_suppressions enable row level security;

revoke all on public.vendor_call_authorizations from anon, authenticated;
revoke all on public.vendor_call_suppressions from anon, authenticated;
grant select, insert, update, delete on public.vendor_call_authorizations to service_role;
grant select, insert, update, delete on public.vendor_call_suppressions to service_role;
