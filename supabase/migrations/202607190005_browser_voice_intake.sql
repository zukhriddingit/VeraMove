alter table public.intake_sessions
    add column if not exists browser_credential_issued_at timestamptz;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'intake_sessions_browser_credential_shape_check'
          and conrelid = 'public.intake_sessions'::regclass
    ) then
        alter table public.intake_sessions
            add constraint intake_sessions_browser_credential_shape_check
            check (
                browser_credential_issued_at is null
                or (
                    provider_call_key_hash is null
                    and browser_credential_issued_at >= created_at
                )
            );
    end if;
end
$$;

create or replace function public.veramove_reserve_browser_voice_credential(
    p_session_id uuid,
    p_issued_at timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    reserved intake_sessions%rowtype;
begin
    if p_session_id is null or p_issued_at is null then
        raise exception 'invalid browser credential reservation';
    end if;
    update intake_sessions
    set browser_credential_issued_at = p_issued_at,
        updated_at = p_issued_at
    where id = p_session_id
      and status = 'pending'
      and provider_call_key_hash is null
      and browser_credential_issued_at is null
      and p_issued_at >= created_at
    returning * into reserved;
    if not found then
        raise exception 'browser credential reservation conflict';
    end if;
    return to_jsonb(reserved);
end
$$;

revoke all on function public.veramove_reserve_browser_voice_credential(uuid, timestamptz)
    from public, anon, authenticated;
grant execute on function public.veramove_reserve_browser_voice_credential(uuid, timestamptz)
    to service_role;
