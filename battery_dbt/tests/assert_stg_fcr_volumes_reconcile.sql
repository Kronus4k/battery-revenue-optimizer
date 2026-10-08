-- Fails if SE1..SE4 + DK2 volumes don't add up to SvK's own Total column.
-- Proves the CSV field POSITIONS are mapped to the right zones and products:
-- a shifted column makes the sum wrong. Tolerance covers decimal rounding.
select ts_utc, product,
       sum(volume_mw) + max(dk2_volume_mw) as sum_of_parts,
       max(product_total_mw)               as svk_total
from {{ ref('stg_fcr') }}
group by ts_utc, product
having abs(sum(volume_mw) + max(dk2_volume_mw) - max(product_total_mw)) > 0.01