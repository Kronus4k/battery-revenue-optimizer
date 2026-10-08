-- int_spot_hourly: 15-min spot prices averaged to hourly, per zone.
-- Used by strategy B (hourly comparison with reserves). Strategy A's arbitrage
-- uses the 15-min data directly (averaging flattens peaks -> understates arbitrage).

select
    bidding_zone,
    -- 3-argument date_trunc: cut the hour in UTC explicitly. The 2-argument form
    -- uses the SESSION time zone (red test: every hour split 2+2 in a UTC+5:30 session).
    date_trunc('hour', ts_utc, 'UTC')                                  as ts_utc,
    date_trunc('hour', ts_utc, 'UTC') at time zone 'Europe/Stockholm' as ts_local,
    min(delivery_date)                                                 as delivery_date,
    avg(price_eur_mwh)                                                 as price_eur_mwh,
    min(price_eur_mwh)                                                 as min_quarter_price_eur_mwh,
    max(price_eur_mwh)                                                 as max_quarter_price_eur_mwh,
    count(*)                                                           as n_quarters  -- must be 4 (tested)
from {{ ref('stg_elpris') }}
group by bidding_zone, date_trunc('hour', ts_utc, 'UTC')