-- Headline results per zone for a window of delivery dates (both inclusive).
-- Single source of the results table in README.md and docs/results.md
-- (written there by scripts/make_results.py). Parameters: %(start)s, %(end)s.
--   arbitrage       average daily profit of the best single charge/discharge cycle
--   best_reserve    reserve product with the highest average daily revenue
--   wins            days on which that product was the best single strategy
--   a_best          strategy A: average of each day's best single strategy
--   b_ceiling       strategy B: average theoretical upper bound (ignores state of charge)
--   gain_pct        B / A - 1, in percent
with s as (
    select * from analytics_marts.mart_strategy_daily
    where delivery_date between %(start)s::date and %(end)s::date
),
arb as (
    select bidding_zone as z, avg(revenue_eur) as v
    from s where strategy = 'arbitrage' group by 1
),
res as (
    select bidding_zone as z, strategy, avg(revenue_eur) as v,
           count(*) filter (where is_winner) as wins, count(*) as days,
           row_number() over (partition by bidding_zone order by avg(revenue_eur) desc) as rn
    from s where strategy <> 'arbitrage' group by 1, 2
),
a as (
    select bidding_zone as z, avg(day_best) as v
    from (select bidding_zone, delivery_date, max(revenue_eur) as day_best
          from s group by 1, 2) as per_day
    group by 1
),
b as (
    select bidding_zone as z, avg(upper_bound_eur) as v
    from analytics_marts.mart_upper_bound_daily
    where delivery_date between %(start)s::date and %(end)s::date
    group by 1
),
n as (
    select bidding_zone as z, count(distinct delivery_date) as n from s group by 1
)
select arb.z                         as zone,
       n.n                           as days,
       round(arb.v, 1)               as arbitrage,
       r.strategy                    as best_reserve,
       round(r.v, 1)                 as best_reserve_v,
       r.wins || '/' || r.days       as wins,
       round(a.v, 1)                 as a_best,
       round(b.v, 1)                 as b_ceiling,
       round(100 * (b.v / a.v - 1))  as gain_pct
from arb
join res r on r.z = arb.z and r.rn = 1
join a     on a.z = arb.z
join b     on b.z = arb.z
join n     on n.z = arb.z
order by 1
