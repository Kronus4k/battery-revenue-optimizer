-- RED TEST: REVERT (never merge). Proves the CI dbt job fails on broken SQL.
select no_such_column from {{ ref('mart_strategy_daily') }}
