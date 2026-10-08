-- mart_upper_bound_daily: strategy B, a theoretical CEILING per zone and day.
-- Each 15-min quarter takes the best of: reserve capacity, discharging (bought at
-- the day's cheapest quarter), or idle. Ignores state of charge, so no real
-- battery can execute it. Computed per QUARTER (not per hour) so it provably
-- bounds any 15-min plan, incl. a full optimiser (C) and strategy A (tested).
-- Label: "theoretical upper bound, ignores state of charge" (Note 3.1).

{% set power = var('battery_power_mw') %}
{% set eff = var('round_trip_efficiency') %}

with quarters as (
    select
        bidding_zone,
        delivery_date,
        price_eur_mwh,
        date_trunc('hour', ts_utc, 'UTC')                                   as hour_utc,
        min(price_eur_mwh) over (partition by bidding_zone, delivery_date)  as day_min_price
    from {{ ref('stg_elpris') }}
),

best_reserve as (
    -- Best single reserve product per zone and hour (no stacking, like strategy A).
    select bidding_zone, ts_utc as hour_utc, max(price_eur_mw_h) as best_reserve_price
    from {{ ref('int_reserve_prices_hourly') }}
    group by bidding_zone, ts_utc
),

valued as (
    -- Inner join: only quarters whose hour has reserve data (same days as A).
    select
        q.bidding_zone,
        q.delivery_date,
        greatest(
            r.best_reserve_price * {{ power }} * 0.25,  
            ({{ eff }} * q.price_eur_mwh - q.day_min_price) * {{ power }} * 0.25,
            0
        ) as quarter_value_eur
    from quarters q
    join best_reserve r using (bidding_zone, hour_utc)
)

select
    bidding_zone,
    delivery_date,
    count(*)                          as n_quarters,
    round(sum(quarter_value_eur), 2)  as upper_bound_eur
from valued
group by bidding_zone, delivery_date