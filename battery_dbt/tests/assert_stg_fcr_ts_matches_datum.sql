-- Fails if our computed local time (midnight + row index) disagrees with
-- SvK's Datum text. Catches a dropped or extra row shifting every later hour.
-- On the October DST day both 02:00 rows still match the text, by design.
select delivery_date, hour_index, ts_local, datum_text
from {{ ref('stg_fcr') }}
where to_char(ts_local, 'YYYY-MM-DD HH24:MI:SS') <> datum_text
