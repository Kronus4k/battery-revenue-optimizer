-- mart_strategy_daily: strategy A result. Per zone and day, the revenue of each
-- of the 6 single-strategy choices (arbitrage + 5 reserve products) and the winner.
-- Perfect foresight: an upper estimate, not expected revenue (Note 3.1).

with arbitrage as (
    select bidding_zone, delivery_date, 'arbitrage' as strategy,
           arbitrage_profit_eur as revenue_eur
    from {{ ref('fct_arbitrage_daily') }}
),

reserves as (
    select bidding_zone, delivery_date, product as strategy,
           reserve_revenue_eur as revenue_eur
    from {{ ref('fct_reserve_daily') }}
),

complete_days as (
    -- Only days where BOTH spot and reserve data exist (elpris runs a day ahead
    -- of SvK), so every strategy is compared on exactly the same days.
    select distinct a.bidding_zone, a.delivery_date
    from arbitrage a
    join reserves r using (bidding_zone, delivery_date)
),

all_strategies as (
    select * from arbitrage
    union all
    select * from reserves
)

select
    s.bidding_zone,
    s.delivery_date,
    s.strategy,
    s.revenue_eur,
    rank() over (partition by s.bidding_zone, s.delivery_date
                 order by s.revenue_eur desc)          as revenue_rank,
    rank() over (partition by s.bidding_zone, s.delivery_date
                 order by s.revenue_eur desc) = 1     as is_winner
from all_strategies s
join complete_days d using (bidding_zone, delivery_date)