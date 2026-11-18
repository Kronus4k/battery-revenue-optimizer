# battery_dbt

dbt project of the Battery Revenue Optimizer: raw landing files -> staging (parse and type) -> intermediate (align grains) -> marts (daily strategies and the upper bound).

Run it from this folder with the `.venv-dbt` environment: `dbt build`. Connection settings come from environment variables (see `profiles.yml`). Project overview, data flow and tests: the [main README](../README.md).
