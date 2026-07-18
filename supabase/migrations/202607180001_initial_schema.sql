create extension if not exists pgcrypto;

create table if not exists jobs (
    id uuid primary key default gen_random_uuid(),
    job_spec_version text not null,
    state text not null,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists vendors (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists calls (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    vendor_id uuid not null references vendors(id) on delete restrict,
    status text not null,
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
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists transcript_evidence (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    call_id uuid not null references calls(id) on delete cascade,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists recommendations (
    id uuid primary key default gen_random_uuid(),
    job_id uuid not null references jobs(id) on delete cascade,
    recommendation_version text not null,
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
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists jobs_state_idx on jobs(state);
create index if not exists calls_job_id_idx on calls(job_id);
create index if not exists calls_vendor_id_idx on calls(vendor_id);
create index if not exists calls_status_idx on calls(status);
create index if not exists quotes_job_id_idx on quotes(job_id);
create index if not exists quotes_vendor_id_idx on quotes(vendor_id);
create index if not exists transcript_evidence_job_id_idx on transcript_evidence(job_id);
create index if not exists transcript_evidence_call_id_idx on transcript_evidence(call_id);
create index if not exists recommendations_job_id_idx on recommendations(job_id);
create index if not exists event_log_job_id_idx on event_log(job_id);
create index if not exists event_log_source_type_idx on event_log(source, event_type);
