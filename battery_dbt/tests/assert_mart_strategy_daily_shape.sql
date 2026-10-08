-- Fails for any zone/day that does not have exactly 6 strategies
-- (arbitrage + 5 reserve products) and exactly 1 winner.
-- Catches: a missing product feed, a day with only one side of the data,
-- or ties that would make "the winner" ambiguous.
select bidding_zone, delivery_date,
       count(*)                          as n_strategies,
       count(*) filter (where is_winner) as n_winners
from {{ ref('mart_strategy_daily') }}
group by bidding_zone, delivery_date
having count(*) <> 6
    or count(*) filter (where is_winner) <> 1