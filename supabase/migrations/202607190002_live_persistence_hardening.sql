alter table calls
    add column if not exists record_type text not null default 'canonical';

update calls
set record_type = 'canonical'
where record_type <> 'canonical';

alter table calls
    alter column record_type set default 'canonical';

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'calls_record_type_check'
    ) then
        alter table calls
            add constraint calls_record_type_check
            check (record_type in ('attempt', 'canonical'));
    end if;
end
$$;

create table if not exists call_attempts (
    id uuid primary key,
    job_id uuid not null references jobs(id) on delete cascade,
    vendor_id uuid not null references vendors(id) on delete restrict,
    conversation_id text unique,
    external_call_id text unique,
    idempotency_key text not null unique,
    status text not null,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table jobs enable row level security;
alter table vendors enable row level security;
alter table call_attempts enable row level security;
alter table calls enable row level security;
alter table quotes enable row level security;
alter table transcript_evidence enable row level security;
alter table recommendations enable row level security;
alter table event_log enable row level security;

revoke all on jobs, vendors, call_attempts, calls, quotes, transcript_evidence,
    recommendations, event_log from anon, authenticated;

grant select, insert, update, delete on jobs, vendors, call_attempts, calls, quotes,
    transcript_evidence, recommendations, event_log to service_role;

create index if not exists call_attempts_job_id_idx on call_attempts(job_id);
create index if not exists call_attempts_vendor_id_idx on call_attempts(vendor_id);
create index if not exists call_attempts_status_idx on call_attempts(status);
create index if not exists call_attempts_conversation_id_idx
    on call_attempts(conversation_id);
create index if not exists calls_record_type_idx on calls(record_type);
