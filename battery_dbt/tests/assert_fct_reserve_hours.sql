-- Fails if a reserve day has more hours than the local day has (duplicates),
-- or if an FCR product is missing any hour (Mimer publishes every hour; only
-- mFRR may have gaps, see assert_stg_mfrr_missing_hours).
select bidding_zone, delivery_date, product, n_hours, expected_hours
from {{ ref('fct_reserve_daily') }}
where n_hours > expected_hours
   or (market = 'fcr' and n_hours <> expected_hours)
