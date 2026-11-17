-- Days on which each single strategy was the best one (strategy A's daily choice).
-- Parameters: %(start)s, %(end)s. A tie would count for every tied strategy;
-- scripts/make_results.py checks that each zone sums to the number of days.
select bidding_zone as zone, strategy, count(*) as days_won
from analytics_marts.mart_strategy_daily
where is_winner
  and delivery_date between %(start)s::date and %(end)s::date
group by 1, 2
order by 1, 3 desc, 2
