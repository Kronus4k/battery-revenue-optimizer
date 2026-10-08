-- fct_arbitrage_daily: strategy A, arbitrage leg. Best single charge/discharge
-- cycle per zone and day, on 15-minute spot prices (perfect foresight).
--
-- Rules (README "Simplifications"):
--   * charge for n consecutive quarters at full power, then discharge for n
--     consecutive quarters at full power, discharge starting after charging ends
--   * same delivery day only (no overnight cycle), at most one cycle per day
--   * round-trip losses applied to the discharge revenue
--   * if no cycle is profitable, the battery idles: profit 0
-- n = energy / power * 4 quarters (2 MWh / 1 MW = 2 h = 8 quarters).

{% set n_q = (var('battery_energy_mwh') / var('battery_power_mw') * 4) | int %}
{% set mwh_per_quarter = var('battery_power_mw') * 0.25 %}
{% set eff = var('round_trip_efficiency') %}

with quarters as (
    -- Number the quarters of each day in time order (92/96/100 on DST days).
    select
        bidding_zone,
        delivery_date,
        ts_local,
        price_eur_mwh,
        row_number() over (partition by bidding_zone, delivery_date order by ts_utc) as q_idx
    from {{ ref('stg_elpris') }}
),

windows as (
    -- Every possible block of n consecutive quarters, with its summed price.
    select
        bidding_zone,
        delivery_date,
        q_idx    as start_idx,
        ts_local as start_local,
        sum(price_eur_mwh) over w as price_sum,
        count(*)           over w as n_quarters
    from quarters
    window w as (
        partition by bidding_zone, delivery_date
        order by q_idx
        rows between current row and {{ n_q - 1 }} following
    )
),

full_windows as (
    -- Blocks near the end of the day are shorter than n quarters: drop them.
    select * from windows where n_quarters = {{ n_q }}
),

pairs as (
    -- Every charge block combined with every discharge block that starts
    -- after the charge block has ended.
    select
        c.bidding_zone,
        c.delivery_date,
        c.start_local                                          as charge_start_local,
        d.start_local                                          as discharge_start_local,
        c.price_sum * {{ mwh_per_quarter }}                    as charge_cost_eur,
        d.price_sum * {{ mwh_per_quarter }} * {{ eff }}        as discharge_revenue_eur
    from full_windows c
    join full_windows d
      on  d.bidding_zone  = c.bidding_zone
      and d.delivery_date = c.delivery_date
      and d.start_idx    >= c.start_idx + {{ n_q }}
),

best as (
    -- Postgres DISTINCT ON: keep the single most profitable pair per zone/day.
    select distinct on (bidding_zone, delivery_date)
        *,
        discharge_revenue_eur - charge_cost_eur as gross_profit_eur
    from pairs
    order by bidding_zone, delivery_date, discharge_revenue_eur - charge_cost_eur desc
)

select
    bidding_zone,
    delivery_date,
    gross_profit_eur > 0                                                     as cycled,
    case when gross_profit_eur > 0 then charge_start_local    end            as charge_start_local,
    case when gross_profit_eur > 0 then discharge_start_local end            as discharge_start_local,
    round(case when gross_profit_eur > 0 then charge_cost_eur       else 0 end, 2) as charge_cost_eur,
    round(case when gross_profit_eur > 0 then discharge_revenue_eur else 0 end, 2) as discharge_revenue_eur,
    round(greatest(gross_profit_eur, 0), 2)                                  as arbitrage_profit_eur  -- euros, 2 decimals
from best