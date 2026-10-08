-- stg_elpris: unpack elpris spot-price files into one row per 15-minute interval.
-- Grain: bidding_zone x ts_utc (15-min). No aggregation here (that's intermediate).

with files as (
    -- One row per raw file; bytes -> text -> JSON. Raw bytes stay untouched in landing.
    select
        zone,
        delivery_date,
        convert_from(content, 'UTF8')::jsonb as doc
    from {{ source('raw', 'landing_files') }}
    where source = 'elpris'
),

records as (
    -- Unpack the JSON array: 96 records per normal day (92/100 on DST days).
    select f.zone, f.delivery_date, r.rec
    from files f
    cross join lateral jsonb_array_elements(f.doc) as r(rec)
)

select
    zone                                             as bidding_zone,
    delivery_date,
    -- The timestamp carries its offset (+01:00/+02:00), so this is an exact instant.
    -- ts_utc is our key (locked decision: UTC keeps keys unique across DST).
    (rec ->> 'time_start')::timestamptz              as ts_utc,
    -- Local time is DERIVED here, never stored independently upstream.
    (rec ->> 'time_start')::timestamptz
        at time zone 'Europe/Stockholm'               as ts_local,
    -- Should always be 15; a test will prove it.
    (extract(epoch from (rec ->> 'time_end')::timestamptz
                      - (rec ->> 'time_start')::timestamptz) / 60)::int
                                                     as interval_minutes,
    -- Units: API gives per kWh; reserve markets use per MWh -> x 1000.
    (rec ->> 'EUR_per_kWh')::numeric * 1000          as price_eur_mwh,
    (rec ->> 'SEK_per_kWh')::numeric * 1000          as price_sek_mwh,
    (rec ->> 'EXR')::numeric                         as eur_sek_rate
from records