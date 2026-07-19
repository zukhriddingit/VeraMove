create extension if not exists pgcrypto;

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    job_spec_version text not null,
    state text not null,
    confirmed_at timestamptz,
    locked_job_spec_version text,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists vendors (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    provenance jsonb not null default '[]'::jsonb,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists calls (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    vendor_id uuid not null references vendors(id) on delete restrict,
    external_call_id text unique,
    idempotency_key text unique,
    status text not null,
    outcome_type text
        check (outcome_type in (
            'itemized_quote',
            'callback_commitment',
            'documented_decline',
            'failed'
        )),
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists quotes (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    vendor_id uuid not null references vendors(id) on delete restrict,
    call_id uuid references calls(id) on delete set null,
    quote_version text not null,
    job_spec_version text not null,
    verification_status text not null default 'provisional'
        check (verification_status in (
            'provisional',
            'partially_verified',
            'verified',
            'rejected'
        )),
    provisional_payload jsonb not null default '{}'::jsonb,
    verified_payload jsonb not null default '{}'::jsonb,
    provenance jsonb not null default '[]'::jsonb,
    manually_fabricated boolean not null default false,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists transcript_evidence (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    call_id uuid not null references calls(id) on delete cascade,
    verification_status text not null default 'provisional'
        check (verification_status in (
            'provisional',
            'partially_verified',
            'verified',
            'rejected'
        )),
    recording_url text,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists recommendations (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    recommendation_version text not null,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    provenance jsonb not null default '[]'::jsonb,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists event_log (
    id uuid primary key default gen_random_uuid(),
    job_id uuid references jobs(id) on delete set null,
    source text not null,
    event_type text not null,
    idempotency_key text not null unique,
    data_classification text not null default 'synthetic'
        check (data_classification in ('synthetic', 'role_play', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists jobs_state_idx on jobs(state);
create index if not exists calls_job_id_idx on calls(job_id);
create index if not exists calls_vendor_id_idx on calls(vendor_id);
create index if not exists calls_status_idx on calls(status);
create index if not exists calls_outcome_type_idx on calls(outcome_type);
create index if not exists quotes_job_id_idx on quotes(job_id);
create index if not exists quotes_vendor_id_idx on quotes(vendor_id);
create index if not exists quotes_verification_status_idx on quotes(verification_status);
create index if not exists quotes_job_spec_version_idx on quotes(job_id, job_spec_version);
create index if not exists transcript_evidence_job_id_idx on transcript_evidence(job_id);
create index if not exists transcript_evidence_call_id_idx on transcript_evidence(call_id);
create index if not exists recommendations_job_id_idx on recommendations(job_id);
create index if not exists event_log_job_id_idx on event_log(job_id);
create index if not exists event_log_source_type_idx on event_log(source, event_type);

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'jobs_lock_consistency'
    ) then
        alter table jobs
            add constraint jobs_lock_consistency
            check (
                (confirmed_at is null and locked_job_spec_version is null)
                or
                (confirmed_at is not null and locked_job_spec_version = job_spec_version)
            );
    end if;
end
$$;
