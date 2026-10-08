-- Fails if any (bidding_zone, ts_utc) appears more than once.
-- Why: duplicates (e.g. a file loaded twice under different dates) would
-- double-count prices in the backtest.
select bidding_zone, ts_utc, count(*) as n
from {{ ref('stg_elpris') }}
group by bidding_zone, ts_utc
having count(*) > 1