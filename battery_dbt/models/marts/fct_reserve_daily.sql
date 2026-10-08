-- fct_reserve_daily: strategy A, reserve leg. Revenue per zone, day and product
-- if the full battery power is offered in that ONE product for every hour of the day.
-- Simplifications (README): capacity payment only (no activation energy),
-- no endurance / state-of-charge rules, no stacking of products.

{% set power = var('battery_power_mw') %}

select
    bidding_zone,
    delivery_date,
    market,
    product,
    count(*)                                         as n_hours,     -- 24 (23/25 on DST days)
    round(sum(price_eur_mw_h) * {{ power }}, 2)      as reserve_revenue_eur
from {{ ref('int_reserve_prices_hourly') }}
group by bidding_zone, delivery_date, market, product