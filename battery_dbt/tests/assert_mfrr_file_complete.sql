-- Fails if an mFRR file holds fewer records than the API said exist ('total').
-- Guards against silent truncation when a day exceeds the API page 'limit'.
-- Reads the SOURCE, not the model: it checks the file itself.
with files as (
    select delivery_date, convert_from(content, 'UTF8')::jsonb as doc
    from {{ source('raw', 'landing_files') }}
    where source = 'svk_mfrr'
)
select
    delivery_date,
    (doc -> 'result' ->> 'total')::int              as api_total,
    jsonb_array_length(doc -> 'result' -> 'records') as records_in_file
from files
where (doc -> 'result' ->> 'total')::int
   <> jsonb_array_length(doc -> 'result' -> 'records')