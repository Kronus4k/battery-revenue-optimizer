-- Fails if any FCR file's header differs from the layout stg_fcr's field
-- POSITIONS were written for. If SvK reorders/renames columns, the build
-- stops here instead of silently mapping prices to the wrong products.
-- chr(65279) = the BOM, which is part of the contract (known quirk).
with files as (
    select delivery_date, convert_from(content, 'UTF8') as txt
    from {{ source('raw', 'landing_files') }}
    where source = 'svk_fcr'
)
select delivery_date,
       replace(split_part(txt, chr(10), 1), chr(13), '') as header
from files
where replace(split_part(txt, chr(10), 1), chr(13), '') <>
      chr(65279) || 'Datum;FCR-N Pris (EUR/MW);Total;SE1 FCRN;SE2 FCRN;SE3 FCRN;SE4 FCRN;DK2 FCRN;'
                 || 'FCR-D upp Pris (EUR/MW);Total FCRD upp;SE1 FCRD upp;SE2 FCRD upp;SE3 FCRD upp;SE4 FCRD upp;DK2 FCRD upp;'
                 || 'FCR-D ned Pris (EUR/MW);Total FCRD ned;SE1 FCRD ned;SE2 FCRD ned;SE3 FCRD ned;SE4 FCRD ned;DK2 FCRD ned;'