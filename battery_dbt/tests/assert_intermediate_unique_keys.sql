-- Fails if either intermediate model has a duplicate key.
-- A duplicate here would double-count revenue in every mart built on top.
select 'int_spot_hourly' as model, bidding_zone, ts_utc, null as product, count(*) as n
from {{ ref('int_spot_hourly') }}
group by bidding_zone, ts_utc
having count(*) > 1

union all

select 'int_reserve_prices_hourly', bidding_zone, ts_utc, product, count(*)
from {{ ref('int_reserve_prices_hourly') }}
group by bidding_zone, ts_utc, product
having count(*) > 1