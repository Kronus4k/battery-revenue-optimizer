-- Fails if our computed local time (midnight + row index) disagrees with
-- SvK's Datum text. Catches a dropped or extra row shifting every later hour.
-- October DST day: Mimer labels the repeated 02:00 hour '02:01:00' (seen in the
-- 2026-10-25 file). stg_fcr normalizes that label in datum_local, but only on the
-- row it flags as is_repeated_hour; any other non-':00:00' Datum still fails.
-- Not yet proven: how Mimer labels the spring DST day (23 hours, March).
select delivery_date, hour_index, ts_local, datum_text, datum_local,
       'local time differs from Datum' as problem
from {{ ref('stg_fcr') }}
where to_char(ts_local, 'YYYY-MM-DD HH24:MI:SS') <> datum_local

union all

select delivery_date, hour_index, ts_local, datum_text, datum_local,
       'unexpected minutes in Datum' as problem
from {{ ref('stg_fcr') }}
where datum_text !~ ':00:00$'
  and not (is_repeated_hour and datum_text ~ ':01:00$')
