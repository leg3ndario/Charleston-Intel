-- ============================================================================
-- CHARLESTON COUNTY MOTIVATED SELLER LEADS — SUPABASE SCHEMA
-- ============================================================================
-- Run this in your Supabase SQL editor on first setup.
-- Designed for: dedup across sources, scoring, audit trail, idempotent scraping.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- PROPERTIES — canonical parcel records (one row per real-world property)
-- ---------------------------------------------------------------------------
create table if not exists properties (
    id              uuid primary key default gen_random_uuid(),
    tms             text unique,                  -- Tax Map Series (Charleston County PIN)
    address_norm    text not null,                -- normalized address for matching
    address_raw     text,                         -- as-found
    city            text,
    zip             text,
    county          text default 'Charleston',
    state           text default 'SC',
    latitude        numeric,
    longitude       numeric,
    -- enrichment fields populated by tax-portal lookup
    owner_name_norm text,
    owner_name_raw  text,
    mailing_address text,
    mailing_state   text,
    is_absentee     boolean default false,
    is_out_of_state boolean default false,
    assessed_value  numeric,
    last_sale_date  date,
    last_sale_price numeric,
    enriched_at     timestamptz,
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);
create index if not exists idx_properties_address on properties(address_norm);
create index if not exists idx_properties_owner on properties(owner_name_norm);
create index if not exists idx_properties_absentee on properties(is_absentee) where is_absentee;
create index if not exists idx_properties_oos on properties(is_out_of_state) where is_out_of_state;

-- ---------------------------------------------------------------------------
-- LEADS — one row per distress signal. Multiple leads can map to one property.
-- ---------------------------------------------------------------------------
create table if not exists leads (
    id              uuid primary key default gen_random_uuid(),
    property_id     uuid references properties(id) on delete set null,
    -- source identification (used for idempotent upserts)
    source          text not null,                -- e.g. 'rp_tax_sale_xlsx', 'rod_daybook'
    source_record_id text,                        -- portal-specific id (case#, TMS, etc.)
    -- lead content
    lead_type       text not null,                -- LP, TAX, PROB, CODE, LIEN, FCL, EVCT, OTH
    owner_raw       text,
    owner_norm      text,
    address_raw     text,
    address_norm    text,
    case_number     text,
    amount          numeric,
    filing_date     date,
    plaintiff       text,
    notes           text,
    -- scoring
    flags           text[] default '{}',          -- array of flag strings
    score           int default 0,
    -- lifecycle
    status          text default 'new',           -- new, working, contacted, dead, deal
    skip_traced_at  timestamptz,
    exported_at     timestamptz,
    -- audit
    raw_data        jsonb,                        -- full original record from scraper
    created_at      timestamptz default now(),
    updated_at      timestamptz default now(),
    -- dedup constraint: same source can only produce one lead per source_record_id
    unique (source, source_record_id)
);
create index if not exists idx_leads_property on leads(property_id);
create index if not exists idx_leads_score on leads(score desc);
create index if not exists idx_leads_status on leads(status);
create index if not exists idx_leads_owner_norm on leads(owner_norm);
create index if not exists idx_leads_address_norm on leads(address_norm);
create index if not exists idx_leads_filing_date on leads(filing_date desc);

-- ---------------------------------------------------------------------------
-- SCRAPE_RUNS — audit log for every scraper execution
-- ---------------------------------------------------------------------------
create table if not exists scrape_runs (
    id              uuid primary key default gen_random_uuid(),
    source          text not null,
    started_at      timestamptz default now(),
    finished_at     timestamptz,
    status          text default 'running',       -- running, success, failed
    records_found   int default 0,
    records_new     int default 0,
    records_updated int default 0,
    error_message   text,
    raw_log         text
);
create index if not exists idx_scrape_runs_source on scrape_runs(source, started_at desc);

-- ---------------------------------------------------------------------------
-- ENRICHMENT_QUEUE — properties needing tax-portal enrichment
-- ---------------------------------------------------------------------------
create table if not exists enrichment_queue (
    id              uuid primary key default gen_random_uuid(),
    property_id     uuid references properties(id) on delete cascade,
    lead_id         uuid references leads(id) on delete cascade,
    priority        int default 5,                -- 1=high, 10=low
    attempts        int default 0,
    last_attempt    timestamptz,
    last_error      text,
    completed_at    timestamptz,
    created_at      timestamptz default now()
);
create index if not exists idx_enrich_queue_pending on enrichment_queue(priority, created_at)
    where completed_at is null;

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_properties_updated on properties;
create trigger trg_properties_updated before update on properties
    for each row execute function set_updated_at();

drop trigger if exists trg_leads_updated on leads;
create trigger trg_leads_updated before update on leads
    for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Convenience view: leads with property enrichment merged in
-- ---------------------------------------------------------------------------
create or replace view v_leads_enriched as
select
    l.id,
    l.lead_type,
    l.owner_raw,
    l.owner_norm,
    coalesce(p.address_norm, l.address_norm) as address,
    p.city,
    p.zip,
    p.tms,
    coalesce(p.mailing_address, '') as mailing_address,
    p.mailing_state,
    p.is_absentee,
    p.is_out_of_state,
    p.assessed_value,
    l.case_number,
    l.amount,
    l.filing_date,
    l.plaintiff,
    l.flags,
    l.score,
    l.status,
    l.source,
    l.notes,
    l.created_at
from leads l
left join properties p on p.id = l.property_id
order by l.score desc, l.created_at desc;
