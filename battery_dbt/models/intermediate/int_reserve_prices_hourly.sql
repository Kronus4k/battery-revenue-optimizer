-- int_reserve_prices_hourly: every reserve product in ONE long table.
-- Grain: bidding_zone x ts_utc (hourly) x product.
-- Products: fcr_n, fcr_d_up, fcr_d_down (FCR, one Swedish price per product)
--           mfrr_up, mfrr_down (mFRR capacity market, price per zone).
-- Price unit for all: EUR per MW per hour (capacity payment for availability).

select
    bidding_zone,
    ts_utc,
    ts_local,
    delivery_date,
    'fcr'                as market,
    product,
    price_eur_mw_h,
    volume_mw
from {{ ref('stg_fcr') }}

union all

select
    bidding_zone,
    ts_utc,
    ts_local,
    delivery_date,
    'mfrr'               as market,
    'mfrr_' || direction as product,   -- up/down -> mfrr_up / mfrr_down
    price_eur_mw_h,
    volume_mw
from {{ ref('stg_mfrr') }}