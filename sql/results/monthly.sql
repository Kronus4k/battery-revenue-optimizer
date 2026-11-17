-- Monthly averages per zone (EUR per day): arbitrage only, strategy A, strategy B.
-- Parameters: %(start)s, %(end)s (delivery dates, both inclusive).
with s as (
    select * from analytics_marts.mart_strategy_daily
    where delivery_date between %(start)s::date and %(end)s::date
),
per_day as (
    select bidding_zone, delivery_date,
           max(revenue_eur)                                      as a_best,
           max(revenue_eur) filter (where strategy = 'arbitrage') as arbitrage
    from s group by 1, 2
)
select p.bidding_zone                                as zone,
       to_char(p.delivery_date, 'YYYY-MM')           as month,
       count(*)                                      as days,
       round(avg(p.arbitrage), 1)                    as arbitrage,
       round(avg(p.a_best), 1)                       as a_best,
       round(avg(u.upper_bound_eur), 1)              as b_ceiling
from per_day p
join analytics_marts.mart_upper_bound_daily u
  on u.bidding_zone = p.bidding_zone and u.delivery_date = p.delivery_date
group by 1, 2
order by 1, 2
