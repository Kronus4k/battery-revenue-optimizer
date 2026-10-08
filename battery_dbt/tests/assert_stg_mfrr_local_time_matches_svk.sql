-- Fails if OUR derived local time differs from SvK's own start_time_sweden.
-- Guards the UTC parsing of the offset-less start_time_utc (a naive
-- ::timestamptz cast is off by 1-2 h). Real proof only on DST days
-- (next: 2026-10-25), so this test keeps running on every build.
select bidding_zone, direction, ts_utc, ts_local, ts_local_svk
from {{ ref('stg_mfrr') }}
where ts_local <> ts_local_svk