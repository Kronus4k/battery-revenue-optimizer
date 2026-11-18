-- WARN (not error): lists zone/direction/days with fewer rows than the real
-- number of hours in that local day.
-- Why warn: the SVK Data Service omits some hours instead of publishing them.
-- Seen for SE1 up only, from 2026-10-16 (e.g. 2026-10-17: 5 of 24 hours), still
-- absent when re-fetched a month later; the API's result.total matches the
-- records returned, so the file is not truncated (assert_mfrr_file_complete,
-- error level, guards that). Most likely no capacity was procured in those
-- hours; not confirmed by SvK's documentation (question to SvK open data pending).
-- Modelling consequence: a missing hour earns 0 (fct_reserve_daily sums the
-- hours present; n_hours vs expected_hours shows the gap).
{{ config(severity='warn') }}
with per_day as (
    select bidding_zone, direction, delivery_date, count(*) as n
    from {{ ref('stg_mfrr') }}
    group by bidding_zone, direction, delivery_date
)
select *,
       (extract(epoch from
            ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
          - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
        ) / 3600)::int as expected
from per_day
where n < (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 3600)::int
