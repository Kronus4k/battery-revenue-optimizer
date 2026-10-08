-- Fails for any record whose local timestamp is not on the delivery date it
-- was filed under. Catches files stored or loaded under the wrong date
-- (found by a red test: the unique test only caught that bug because the
-- real copy was also present; without it, all other tests passed).
select bidding_zone, delivery_date, ts_utc, ts_local
from {{ ref('stg_elpris') }}
where ts_local::date <> delivery_date