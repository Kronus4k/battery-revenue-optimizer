-- B is a CEILING: on every zone/day it must be >= the best strategy-A revenue.
-- Fails if B is below A anywhere (logic error, so B is not a valid bound),
-- or if a day that A covers is missing from B (gap in coverage).
select a.bidding_zone, a.delivery_date,
       a.revenue_eur      as strategy_a_best_eur,
       b.upper_bound_eur
from {{ ref('mart_strategy_daily') }} a
left join {{ ref('mart_upper_bound_daily') }} b
  using (bidding_zone, delivery_date)
where a.is_winner
  and (b.upper_bound_eur is null
       or b.upper_bound_eur < a.revenue_eur - 0.01)   -- 1 cent tolerance for rounding