-- Reserve products with hours the source did not publish (they count as 0 revenue).
-- Parameters: %(start)s, %(end)s.
select bidding_zone as zone, product,
       sum(n_hours)        as n_hours,
       sum(expected_hours) as expected_hours,
       count(*) filter (where n_hours < expected_hours) as short_days
from analytics_marts.fct_reserve_daily
where delivery_date between %(start)s::date and %(end)s::date
group by 1, 2
having sum(n_hours) <> sum(expected_hours)
order by 1, 2
