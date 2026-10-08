-- Landing zone in the warehouse: one row per raw file, bytes untouched.
-- All parsing and quirk fixes happen downstream in dbt staging.
create schema if not exists raw;

create table if not exists raw.landing_files (
    source         text        not null,  -- elpris | svk_fcr | svk_mfrr
    zone           text        not null,  -- SE1..SE4 or ALL
    delivery_date  date        not null,  -- local delivery date from the S3 path
    s3_key         text        not null,  -- full key of the data file
    content        bytea       not null,  -- file bytes exactly as stored in S3
    meta           jsonb,                 -- the _meta.json written by ingestion
    loaded_at      timestamptz not null default now(),
    primary key (source, zone, delivery_date)  -- rerun = replace, never duplicate
);