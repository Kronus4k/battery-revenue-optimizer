-- stg_mfrr: unpack SVK Data Service mFRR capacity-market files.
-- Grain: bidding_zone x ts_utc (hourly) x direction. One file covers all zones.

with files as (
    select delivery_date, convert_from(content, 'UTF8')::jsonb as doc
    from {{ source('raw', 'landing_files') }}
    where source = 'svk_mfrr'
),

records as (
    -- The records sit inside an envelope: {"help", "success", "result": {"records": [...]}}
    select f.delivery_date, r.rec
    from files f
    cross join lateral jsonb_array_elements(f.doc -> 'result' -> 'records') as r(rec)
)

select
    rec ->> 'bidding_zone'                                   as bidding_zone,
    delivery_date,
    -- start_time_utc has NO offset. Declare it UTC explicitly; a plain ::timestamptz
    -- cast uses the SESSION time zone: correct on a UTC server by luck, wrong by
    -- 1-2 h in Europe/Stockholm (red test: 19,008 of 19,008 rows failed).
    (rec ->> 'start_time_utc')::timestamp at time zone 'UTC' as ts_utc,
    ((rec ->> 'start_time_utc')::timestamp at time zone 'UTC')
        at time zone 'Europe/Stockholm'                      as ts_local,
    -- SvK's own local time, kept only to cross-check our DST handling in a test.
    (rec ->> 'start_time_sweden')::timestamp                 as ts_local_svk,
    rec ->> 'reserve_product'                                as reserve_product,
    rec ->> 'reserve_direction'                              as direction,
    -- Capacity price: EUR per MW per hour (price_unit 'EUR-MW'), tested below.
    (rec ->> 'price')::numeric                               as price_eur_mw_h,
    (rec ->> 'volume')::numeric                              as volume_mw,
    rec ->> 'price_unit'                                     as price_unit,
    rec ->> 'volume_unit'                                    as volume_unit
from records