-- Fails if an hour/product/zone appears twice (e.g. the Summa row or a
-- duplicated line slipping through the filter).
select ts_utc, product, bidding_zone, count(*) as n
from {{ ref('stg_fcr') }}
group by ts_utc, product, bidding_zone
having count(*) > 1