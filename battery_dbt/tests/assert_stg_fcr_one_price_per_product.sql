-- Fails if a product has different prices across zones in the same hour.
-- FCR is one Swedish market: one price per product (known quirk). Different
-- prices would mean a column mix-up in the parser.
select ts_utc, product, count(distinct price_eur_mw_h) as distinct_prices
from {{ ref('stg_fcr') }}
group by ts_utc, product
having count(distinct price_eur_mw_h) > 1