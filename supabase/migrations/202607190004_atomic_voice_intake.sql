-- Follow-up transactional hardening for already-applied live voice schema.
-- Safe on fresh databases after 202607190003 and on existing databases with 003 applied.

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
    if p_idempotency_key is null
       or char_length(p_idempotency_key) not between 1 and 200
       or p_event_type is null
       or char_length(p_event_type) not between 1 and 120
       or p_lease_token is null
       or p_lease_expires_at is null
       or p_now is null
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

    if current_receipt.event_type is distinct from p_event_type then
        raise exception 'voice receipt event type mismatch';
    end if;
    if current_receipt.status = 'processed' then
        return jsonb_build_object('claimed', false, 'processed', true);
    end if;
    if current_receipt.status = 'processing'
       and current_receipt.lease_token = p_lease_token
       and current_receipt.lease_expires_at > p_now then
        return jsonb_build_object('claimed', true, 'processed', false);
    end if;
    if current_receipt.status = 'processing'
       and current_receipt.lease_expires_at > p_now then
        return jsonb_build_object('claimed', false, 'processed', false);
    end if;
    if current_receipt.status = 'failed' and not current_receipt.retryable then
        return jsonb_build_object('claimed', false, 'processed', false);
    end if;
    if current_receipt.attempt_count >= 100 then
        raise exception 'voice receipt retry limit reached';
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
    if p_idempotency_key is null
       or char_length(p_idempotency_key) not between 1 and 200
       or p_lease_token is null
       or p_failure_code is null
       or p_failure_code !~ '^[a-z0-9_:-]{1,80}$'
       or p_retryable is null
       or p_now is null then
        raise exception 'invalid voice receipt failure code';
    end if;
    update voice_webhook_receipts
    set status = 'failed', lease_token = null, lease_expires_at = null,
        retryable = p_retryable, failure_code = p_failure_code, updated_at = p_now
    where idempotency_key = p_idempotency_key
      and status = 'processing'
      and lease_token = p_lease_token
      and lease_expires_at > p_now;
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
    phone_pattern constant text := '\+[1-9][0-9]{7,14}';
    receipt voice_webhook_receipts%rowtype;
begin
    if p_idempotency_key is null
       or char_length(p_idempotency_key) not between 1 and 200
       or p_lease_token is null
       or p_attempt is null
       or jsonb_typeof(p_attempt) <> 'object'
       or p_call is null
       or jsonb_typeof(p_call) <> 'object'
       or p_job is null
       or jsonb_typeof(p_job) <> 'object'
       or p_event is null
       or jsonb_typeof(p_event) <> 'object'
       or p_evidence is null
       or p_now is null then
        raise exception 'invalid voice materialization payload';
    end if;
    select * into receipt
    from voice_webhook_receipts
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
       or receipt.lease_expires_at <= p_now then
        raise exception 'voice receipt lease mismatch';
    end if;
    if receipt.event_type is distinct from p_event ->> 'event_type'
       or p_event ->> 'idempotency_key' is distinct from p_idempotency_key then
        raise exception 'voice receipt event identity mismatch';
    end if;
    if concat(p_attempt, p_call, p_quote, p_evidence, p_job, p_event)
       ~* forbidden_pattern then
        raise exception 'unsafe voice materialization payload';
    end if;
    if concat(p_attempt, p_call, p_quote, p_evidence, p_job, p_event)
       ~ phone_pattern then
        raise exception 'unsafe voice materialization payload';
    end if;
    if jsonb_typeof(p_evidence) <> 'array' then
        raise exception 'voice evidence payload must be an array';
    end if;
    if coalesce(p_job ->> 'expected_revision', '') !~ '^[0-9]+$'
       or p_attempt ->> 'id' is distinct from p_call ->> 'id'
       or p_attempt ->> 'job_id' is distinct from p_call ->> 'job_id'
       or p_attempt ->> 'vendor_id' is distinct from p_call ->> 'vendor_id'
       or p_job ->> 'id' is distinct from p_call ->> 'job_id'
       or p_event ->> 'job_id' is distinct from p_call ->> 'job_id'
       or p_event ->> 'call_id' is distinct from p_call ->> 'id' then
        raise exception 'voice materialization identity mismatch';
    end if;
    if p_quote is null or p_quote = 'null'::jsonb then
        if jsonb_array_length(p_evidence) <> 0 then
            raise exception 'voice evidence requires a canonical quote';
        end if;
    elsif jsonb_typeof(p_quote) <> 'object'
       or p_quote ->> 'job_id' is distinct from p_call ->> 'job_id'
       or p_quote ->> 'vendor_id' is distinct from p_call ->> 'vendor_id'
       or p_quote ->> 'call_id' is distinct from p_call ->> 'id'
       or exists (
           select 1
           from jsonb_array_elements(p_evidence) as evidence
           where evidence ->> 'job_id' is distinct from p_call ->> 'job_id'
              or evidence ->> 'call_id' is distinct from p_call ->> 'id'
       ) then
        raise exception 'voice quote identity mismatch';
    end if;

    update call_attempts
    set status = p_attempt ->> 'status',
        provider_version_id = p_attempt ->> 'provider_version_id',
        payload = p_attempt -> 'payload',
        updated_at = p_now
    where id = (p_attempt ->> 'id')::uuid
      and job_id = (p_attempt ->> 'job_id')::uuid
      and vendor_id = (p_attempt ->> 'vendor_id')::uuid
      and job_spec_version = p_attempt ->> 'job_spec_version';
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
        payload = excluded.payload, updated_at = excluded.updated_at
    where calls.job_id = excluded.job_id
      and calls.vendor_id = excluded.vendor_id;
    if not found then
        raise exception 'voice canonical call identity conflict';
    end if;

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
            payload = excluded.payload, updated_at = excluded.updated_at
        where quotes.job_id = excluded.job_id
          and quotes.vendor_id = excluded.vendor_id
          and quotes.call_id is not distinct from excluded.call_id;
        if not found then
            raise exception 'voice canonical quote identity conflict';
        end if;

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
            payload = excluded.payload
        where transcript_evidence.job_id = excluded.job_id
          and transcript_evidence.call_id = excluded.call_id;
        if not found and jsonb_array_length(p_evidence) > 0 then
            raise exception 'voice evidence identity conflict';
        end if;
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
    if not exists (
        select 1
        from event_log
        where idempotency_key = p_idempotency_key
          and id = (p_event ->> 'id')::uuid
          and job_id = (p_event ->> 'job_id')::uuid
          and event_type = p_event ->> 'event_type'
    ) then
        raise exception 'voice event identity conflict';
    end if;

    update voice_webhook_receipts
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

create or replace function veramove_finalize_voice_intake_webhook(
    p_idempotency_key text,
    p_lease_token uuid,
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
    receipt voice_webhook_receipts%rowtype;
    current_session intake_sessions%rowtype;
    canonical_job jobs%rowtype;
begin
    if p_idempotency_key is null
       or char_length(p_idempotency_key) not between 1 and 200
       or p_lease_token is null
       or p_kind is null
       or p_kind not in ('completed', 'failed')
       or p_session is null
       or jsonb_typeof(p_session) <> 'object'
       or p_event is null
       or jsonb_typeof(p_event) <> 'object'
       or p_now is null then
        raise exception 'invalid voice intake materialization payload';
    end if;
    if concat(p_session, p_job, p_event) ~* forbidden_pattern
       or concat(p_session, p_job, p_event) ~ phone_pattern then
        raise exception 'unsafe voice intake materialization payload';
    end if;

    select * into receipt
    from voice_webhook_receipts
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
       or receipt.lease_expires_at <= p_now then
        raise exception 'voice receipt lease mismatch';
    end if;
    if receipt.event_type is distinct from p_event ->> 'event_type' then
        raise exception 'voice receipt event type mismatch';
    end if;

    select * into current_session
    from intake_sessions
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
       or current_session.created_at
           is distinct from (p_session ->> 'created_at')::timestamptz
       or (
           current_session.conversation_id is not null
           and current_session.conversation_id
               is distinct from p_session ->> 'conversation_id'
       )
       or (p_session ->> 'updated_at')::timestamptz < current_session.updated_at then
        raise exception 'voice intake session identity mismatch';
    end if;

    if p_kind = 'completed' then
        if p_job is null
           or jsonb_typeof(p_job) <> 'object'
           or p_session ->> 'status' <> 'completed'
           or p_session ->> 'conversation_id' is null
           or p_session ->> 'failure_code' is not null
           or p_session ->> 'completed_at' is null
           or p_job ->> 'id' is distinct from p_session ->> 'reserved_job_id'
           or p_job ->> 'state' <> 'intake_complete'
           or p_job ->> 'confirmed_at' is not null
           or p_job ->> 'locked_job_spec_version' is not null
           or p_event ->> 'idempotency_key' is distinct from p_idempotency_key
           or p_event ->> 'job_id' is distinct from p_job ->> 'id'
           or p_event ->> 'call_id' is not null
           or p_event ->> 'id' is null
           or p_event ->> 'data_classification'
               is distinct from p_job ->> 'data_classification'
           or p_event -> 'payload' ->> 'event_id'
               is distinct from p_event ->> 'id'
           or p_event -> 'payload' ->> 'job_id'
               is distinct from p_event ->> 'job_id'
           or p_event -> 'payload' ->> 'event_type'
               is distinct from p_event ->> 'event_type'
           or p_job -> 'payload' #>> '{job_spec,job_id}'
               is distinct from p_job ->> 'id' then
            raise exception 'invalid voice intake completion';
        end if;
        if (p_session ->> 'completed_at')::timestamptz
               is distinct from (p_event -> 'payload' ->> 'occurred_at')::timestamptz
           or (p_job ->> 'created_at')::timestamptz
               is distinct from (p_event -> 'payload' ->> 'occurred_at')::timestamptz
           or (p_job ->> 'updated_at')::timestamptz
               is distinct from (p_event -> 'payload' ->> 'occurred_at')::timestamptz then
            raise exception 'voice intake completion timestamp mismatch';
        end if;

        insert into jobs (
            id, job_spec_version, state, confirmed_at, locked_job_spec_version,
            data_classification, payload, created_at, updated_at
        ) values (
            (p_job ->> 'id')::uuid, p_job ->> 'job_spec_version',
            p_job ->> 'state', null, null, p_job ->> 'data_classification',
            p_job -> 'payload', (p_job ->> 'created_at')::timestamptz,
            (p_job ->> 'updated_at')::timestamptz
        ) on conflict (id) do nothing;

        select * into canonical_job
        from jobs
        where id = (p_job ->> 'id')::uuid
        for update;
        if canonical_job.job_spec_version is distinct from p_job ->> 'job_spec_version'
           or canonical_job.state is distinct from p_job ->> 'state'
           or canonical_job.confirmed_at is not null
           or canonical_job.locked_job_spec_version is not null
           or canonical_job.data_classification
               is distinct from p_job ->> 'data_classification'
           or canonical_job.payload is distinct from p_job -> 'payload'
           or canonical_job.created_at
               is distinct from (p_job ->> 'created_at')::timestamptz
           or canonical_job.updated_at
               is distinct from (p_job ->> 'updated_at')::timestamptz then
            raise exception 'intake session owns a different canonical job';
        end if;

        insert into event_log (
            id, job_id, source, event_type, idempotency_key,
            data_classification, payload, created_at
        ) values (
            (p_event ->> 'id')::uuid, (p_event ->> 'job_id')::uuid,
            'veramove', p_event ->> 'event_type', p_event ->> 'idempotency_key',
            p_event ->> 'data_classification', p_event -> 'payload', p_now
        ) on conflict (idempotency_key) do nothing;
        if not exists (
            select 1
            from event_log
            where idempotency_key = p_idempotency_key
              and id = (p_event ->> 'id')::uuid
              and job_id = (p_event ->> 'job_id')::uuid
              and event_type = p_event ->> 'event_type'
        ) then
            raise exception 'voice intake event identity conflict';
        end if;
    else
        if (p_job is not null and p_job <> 'null'::jsonb)
           or p_session ->> 'status' <> 'failed'
           or coalesce(p_session ->> 'failure_code', '') !~ '^[a-z0-9_]{1,80}$'
           or p_session ->> 'completed_at' is not null
           or exists (
               select 1
               from jobs
               where id = current_session.reserved_job_id
           ) then
            raise exception 'invalid voice intake failure';
        end if;
    end if;

    update intake_sessions
    set conversation_id = p_session ->> 'conversation_id',
        status = p_session ->> 'status',
        failure_code = p_session ->> 'failure_code',
        updated_at = (p_session ->> 'updated_at')::timestamptz,
        completed_at = (p_session ->> 'completed_at')::timestamptz
    where id = current_session.id
      and status in ('pending', 'in_progress', p_session ->> 'status');
    if not found then
        raise exception 'voice intake terminal state conflict';
    end if;

    update voice_webhook_receipts
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

revoke all on function veramove_claim_voice_webhook_receipt(text, text, uuid, timestamptz, timestamptz)
    from public, anon, authenticated;
revoke all on function veramove_fail_voice_webhook_receipt(text, uuid, text, boolean, timestamptz)
    from public, anon, authenticated;
revoke all on function veramove_finalize_voice_webhook(
    text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, timestamptz
) from public, anon, authenticated;
revoke all on function veramove_finalize_voice_intake_webhook(
    text, uuid, text, jsonb, jsonb, jsonb, timestamptz
) from public, anon, authenticated;
grant execute on function veramove_claim_voice_webhook_receipt(text, text, uuid, timestamptz, timestamptz)
    to service_role;
grant execute on function veramove_fail_voice_webhook_receipt(text, uuid, text, boolean, timestamptz)
    to service_role;
grant execute on function veramove_finalize_voice_webhook(
    text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, timestamptz
) to service_role;
grant execute on function veramove_finalize_voice_intake_webhook(
    text, uuid, text, jsonb, jsonb, jsonb, timestamptz
) to service_role;

