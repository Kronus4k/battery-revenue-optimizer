-- ERROR: fails for any zone/direction/day with MORE rows than the real number
-- of hours in that local day (24 normally, 23 / 25 on DST days): duplicates or
-- records leaking in from another day. Fewer rows is a separate warn-level test
-- (assert_stg_mfrr_missing_hours).
with per_day as (
    select bidding_zone, direction, delivery_date, count(*) as n
    from {{ ref('stg_mfrr') }}
    group by bidding_zone, direction, delivery_date
)
select *
from per_day
where n > (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 3600)::int
