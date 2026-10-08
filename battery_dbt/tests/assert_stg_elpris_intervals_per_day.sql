-- Fails for any zone/day whose row count differs from the real length of
-- that local day: 96 normally, 92 on the spring DST day, 100 in autumn.
-- Catches truncated files, missing quarters, or duplicated quarters.
with per_day as (
    select bidding_zone, delivery_date, count(*) as n
    from {{ ref('stg_elpris') }}
    group by bidding_zone, delivery_date
)
select
    bidding_zone,
    delivery_date,
    n,
    (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 900)::int as expected
from per_day
where n <> (extract(epoch from
        ((delivery_date + 1)::timestamp at time zone 'Europe/Stockholm')
      - (delivery_date::timestamp     at time zone 'Europe/Stockholm')
    ) / 900)::int