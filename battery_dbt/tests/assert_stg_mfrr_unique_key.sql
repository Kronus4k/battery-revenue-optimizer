-- Fails if a zone/hour/direction appears more than once.
-- mFRR grain is hourly AND per direction, so direction is part of the key.
select bidding_zone, ts_utc, direction, count(*) as n
from {{ ref('stg_mfrr') }}
group by bidding_zone, ts_utc, direction
having count(*) > 1