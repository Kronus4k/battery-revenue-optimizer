-- =============================================================================
-- api_reader: read-only login for the Flask API
--
-- Least privilege: the API only reads results, so its login can only:
--   - connect to the warehouse database
--   - see the analytics_marts schema (USAGE)
-- It has no access to raw, analytics_staging or analytics_intermediate.
--
-- Password: passed in by psql, never stored in this file:
--   psql ... -v api_password=%API_READER_PASSWORD% -f sql\002_create_api_reader.sql
--
-- Table-level SELECT is not granted here on purpose: dbt drops and recreates
-- mart tables on every build, which removes grants. dbt re-applies them via
-- "+grants" in dbt_project.yml.
--
-- Rerun note: CREATE ROLE fails if the role exists. To rotate the password:
--   alter role api_reader password '<new>';  (via psql -v, same as above)
-- =============================================================================

create role api_reader login password :'api_password';

grant connect on database battery to api_reader;
-- Fresh setup (CI, new machine): dbt has not created the schema yet. Idempotent.
create schema if not exists analytics_marts;
grant usage on schema analytics_marts to api_reader;