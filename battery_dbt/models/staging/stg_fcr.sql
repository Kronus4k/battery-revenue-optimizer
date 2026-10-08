-- stg_fcr: parse Mimer FCR CSV files (FCR-N, FCR-D up, FCR-D down) in SQL.
-- Grain: ts_utc (hourly) x product x bidding_zone (SE1-SE4). DK2 dropped.
-- Quirks handled: BOM + header (skipped), CRLF, ';' separator, decimal comma,
-- 'Summa' totals row (excluded), trailing ';' (ignored), local time without offset.

with files as (
    select delivery_date, convert_from(content, 'UTF8') as txt
    from {{ source('raw', 'landing_files') }}
    where source = 'svk_fcr'
),

lines as (
    -- Split into numbered lines; strip the Windows carriage return (CR).
    select f.delivery_date, t.n, replace(t.line, chr(13), '') as line
    from files f
    cross join lateral string_to_table(f.txt, chr(10)) with ordinality as t(line, n)
),

data_rows as (
    -- Skip the header (line 1, carries the BOM), the empty last line and the
    -- 'Summa' totals row. Number the remaining hourly rows 1, 2, 3 ... per day.
    select delivery_date, line,
           row_number() over (partition by delivery_date order by n) as hour_index
    from lines
    where n > 1
      and line <> ''
      and line not like 'Summa;%'
),

hours as (
    -- Datum has no offset and 02:00 occurs twice on the October DST day, so we
    -- don't parse it. ts_utc = local midnight + (hour_index - 1) hours, which is
    -- exact on every day (23 / 24 / 25 hours). A test compares it with Datum.
    select delivery_date, line, hour_index,
           (delivery_date::timestamp at time zone 'Europe/Stockholm')
               + (hour_index - 1) * interval '1 hour' as ts_utc
    from data_rows
)

select
    v.zone                                                                   as bidding_zone,
    h.delivery_date,
    h.ts_utc,
    h.ts_utc at time zone 'Europe/Stockholm'                                 as ts_local,
    split_part(h.line, ';', 1)                                               as datum_text,
    h.hour_index,
    v.product,
    -- One market price per product (same for every zone); decimal comma -> point.
    replace(split_part(h.line, ';', v.price_pos),  ',', '.')::numeric       as price_eur_mw_h,
    replace(split_part(h.line, ';', v.volume_pos), ',', '.')::numeric       as volume_mw,
    -- Kept only for the column-mapping test: SE1..SE4 + DK2 must equal Total.
    replace(split_part(h.line, ';', v.total_pos),  ',', '.')::numeric       as product_total_mw,
    replace(split_part(h.line, ';', v.dk2_pos),    ',', '.')::numeric       as dk2_volume_mw
from hours h
cross join lateral (values
    -- product,      zone,  price, volume, total, dk2   (CSV field positions)
    ('fcr_n',      'SE1',  2,  4,  3,  8),
    ('fcr_n',      'SE2',  2,  5,  3,  8),
    ('fcr_n',      'SE3',  2,  6,  3,  8),
    ('fcr_n',      'SE4',  2,  7,  3,  8),
    ('fcr_d_up',   'SE1',  9, 11, 10, 15),
    ('fcr_d_up',   'SE2',  9, 12, 10, 15),
    ('fcr_d_up',   'SE3',  9, 13, 10, 15),
    ('fcr_d_up',   'SE4',  9, 14, 10, 15),
    ('fcr_d_down', 'SE1', 16, 18, 17, 22),
    ('fcr_d_down', 'SE2', 16, 19, 17, 22),
    ('fcr_d_down', 'SE3', 16, 20, 17, 22),
    ('fcr_d_down', 'SE4', 16, 21, 17, 22)
) as v(product, zone, price_pos, volume_pos, total_pos, dk2_pos)