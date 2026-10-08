-- Fails for any zone/direction/day whose row count differs from the real
-- number of hours in that local day: 24 normally, 23 / 25 on DST days.
with per_day as (
    select bidding_zone, direction, delivery_date, count(*) as n
    from {{ ref('stg_mfrr') }}
    group by bidding_zone, direction, delivery_date
)
select *
from per_day
where n <> (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 3600)::int