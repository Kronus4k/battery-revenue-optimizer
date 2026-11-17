-- fct_reserve_daily: strategy A, reserve leg. Revenue per zone, day and product
-- if the full battery power is offered in that ONE product for every hour of the day.
-- Simplifications (README): capacity payment only (no activation energy),
-- no endurance / state-of-charge rules, no stacking of products.
-- Missing hours: revenue sums the hours the source published, so a missing hour
-- earns 0 (conservative). n_hours < expected_hours makes such a gap visible
-- (mFRR SE1 up from 2026-10-16; see assert_stg_mfrr_missing_hours).

{% set power = var('battery_power_mw') %}

select
    bidding_zone,
    delivery_date,
    market,
    product,
    count(*)                                         as n_hours,     -- hours with a price
    -- Hours in the local day: 24, or 23 / 25 on DST days.
    (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 3600)::int                                   as expected_hours,
    round(sum(price_eur_mw_h) * {{ power }}, 2)      as reserve_revenue_eur
from {{ ref('int_reserve_prices_hourly') }}
group by bidding_zone, delivery_date, market, product
