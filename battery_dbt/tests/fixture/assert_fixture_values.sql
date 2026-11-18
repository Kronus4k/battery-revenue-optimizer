-- Exact mart values for SE3 and SE4 on two real days loaded from tests/fixtures/raw/:
-- 2026-10-09 (normal, 96 quarters) and 2026-10-25 (autumn DST day, 25 hours, 100 quarters).
-- Returns every row that is missing, extra or different, in either direction.
--
-- Runs only in CI, which loads exactly these fixtures: dbt build --vars '{fixture_values: true}'.
-- The daily transform runs plain `dbt build`, so a later revision by a source can never fail
-- production through this test.
--
-- Independently checked by hand from the raw fixture files (Python, not the dbt SQL):
--   (a) SE3 FCR-N 2026-10-25 = 280.21: sum of the 25 hourly FCR-N prices in the Mimer CSV
--       (280.214160; the repeated hour is labelled 02:00 and 02:01).
--   (b) SE3 arbitrage 2026-10-09 = 89.51: best 8-quarter charge block from 03:30 (cost 25.76),
--       later 8-quarter discharge block from 18:00 (115.27 after the 0.85 round-trip efficiency).
-- All other values are regression values from the production marts on 2026-11-18.

{{ config(enabled=var('fixture_values', false)) }}

with expected_strategy (bidding_zone, delivery_date, strategy, revenue_eur, revenue_rank, is_winner) as (
    values
    ('SE3', date '2026-10-09', 'fcr_n', 374.22, 1, true),
    ('SE3', date '2026-10-09', 'fcr_d_down', 113.16, 2, false),
    ('SE3', date '2026-10-09', 'fcr_d_up', 97.50, 3, false),
    ('SE3', date '2026-10-09', 'arbitrage', 89.51, 4, false),
    ('SE3', date '2026-10-09', 'mfrr_up', 69.25, 5, false),
    ('SE3', date '2026-10-09', 'mfrr_down', 28.68, 6, false),
    ('SE3', date '2026-10-25', 'fcr_n', 280.21, 1, true),
    ('SE3', date '2026-10-25', 'fcr_d_up', 55.89, 2, false),
    ('SE3', date '2026-10-25', 'mfrr_up', 37.56, 3, false),
    ('SE3', date '2026-10-25', 'fcr_d_down', 35.34, 4, false),
    ('SE3', date '2026-10-25', 'mfrr_down', 26.15, 5, false),
    ('SE3', date '2026-10-25', 'arbitrage', 14.25, 6, false),
    ('SE4', date '2026-10-09', 'mfrr_up', 634.85, 1, true),
    ('SE4', date '2026-10-09', 'fcr_n', 374.22, 2, false),
    ('SE4', date '2026-10-09', 'arbitrage', 164.90, 3, false),
    ('SE4', date '2026-10-09', 'fcr_d_down', 113.16, 4, false),
    ('SE4', date '2026-10-09', 'fcr_d_up', 97.50, 5, false),
    ('SE4', date '2026-10-09', 'mfrr_down', 28.68, 6, false),
    ('SE4', date '2026-10-25', 'mfrr_up', 401.24, 1, true),
    ('SE4', date '2026-10-25', 'fcr_n', 280.21, 2, false),
    ('SE4', date '2026-10-25', 'arbitrage', 71.36, 3, false),
    ('SE4', date '2026-10-25', 'fcr_d_up', 55.89, 4, false),
    ('SE4', date '2026-10-25', 'fcr_d_down', 35.34, 5, false),
    ('SE4', date '2026-10-25', 'mfrr_down', 26.15, 6, false)
),

expected_upper (bidding_zone, delivery_date, n_quarters, upper_bound_eur) as (
    values
    ('SE3', date '2026-10-09', 96, 515.44),
    ('SE3', date '2026-10-25', 100, 280.21),
    ('SE4', date '2026-10-09', 96, 845.32),
    ('SE4', date '2026-10-25', 100, 474.05)
),

expected_arbitrage (bidding_zone, delivery_date, cycled, charge_start_local, discharge_start_local,
                    charge_cost_eur, discharge_revenue_eur, arbitrage_profit_eur) as (
    values
    ('SE3', date '2026-10-09', true, timestamp '2026-10-09 03:30', timestamp '2026-10-09 18:00', 25.76, 115.27, 89.51),
    ('SE3', date '2026-10-25', true, timestamp '2026-10-25 02:00', timestamp '2026-10-25 16:15', -1.32, 12.93, 14.25),
    ('SE4', date '2026-10-09', true, timestamp '2026-10-09 03:30', timestamp '2026-10-09 18:15', 26.06, 190.95, 164.90),
    ('SE4', date '2026-10-25', true, timestamp '2026-10-25 02:00', timestamp '2026-10-25 17:00', -0.72, 70.64, 71.36)
),

actual_strategy as (
    select bidding_zone, delivery_date, strategy, revenue_eur, revenue_rank, is_winner
    from {{ ref('mart_strategy_daily') }}
    where bidding_zone in ('SE3', 'SE4')
      and delivery_date in (date '2026-10-09', date '2026-10-25')
),

actual_upper as (
    select bidding_zone, delivery_date, n_quarters, upper_bound_eur
    from {{ ref('mart_upper_bound_daily') }}
    where bidding_zone in ('SE3', 'SE4')
      and delivery_date in (date '2026-10-09', date '2026-10-25')
),

actual_arbitrage as (
    select bidding_zone, delivery_date, cycled, charge_start_local, discharge_start_local,
           charge_cost_eur, discharge_revenue_eur, arbitrage_profit_eur
    from {{ ref('fct_arbitrage_daily') }}
    where bidding_zone in ('SE3', 'SE4')
      and delivery_date in (date '2026-10-09', date '2026-10-25')
)

select 'strategy: expected, not found' as problem, bidding_zone, delivery_date, strategy as detail
from (select * from expected_strategy except select * from actual_strategy) as d
union all
select 'strategy: found, not expected', bidding_zone, delivery_date, strategy
from (select * from actual_strategy except select * from expected_strategy) as d
union all
select 'upper bound: expected, not found', bidding_zone, delivery_date, n_quarters::text
from (select * from expected_upper except select * from actual_upper) as d
union all
select 'upper bound: found, not expected', bidding_zone, delivery_date, n_quarters::text
from (select * from actual_upper except select * from expected_upper) as d
union all
select 'arbitrage: expected, not found', bidding_zone, delivery_date, charge_start_local::text
from (select * from expected_arbitrage except select * from actual_arbitrage) as d
union all
select 'arbitrage: found, not expected', bidding_zone, delivery_date, charge_start_local::text
from (select * from actual_arbitrage except select * from expected_arbitrage) as d
