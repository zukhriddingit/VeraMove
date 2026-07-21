create table if not exists vendor_research (
    id uuid primary key,
    job_id uuid not null references jobs(id) on delete cascade,
    job_spec_version text not null,
    data_classification text not null default 'real_redacted'
        check (data_classification in ('synthetic', 'real_redacted')),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (job_id, job_spec_version)
);

alter table vendor_research enable row level security;

revoke all on vendor_research from anon, authenticated;

grant select, insert, update, delete on vendor_research to service_role;

create index if not exists vendor_research_job_version_idx
    on vendor_research(job_id, job_spec_version);
