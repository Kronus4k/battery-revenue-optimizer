# =============================================================================
# Custom Airflow image = official Airflow + dbt in its OWN virtualenv (D4.1)
#
# Why a separate venv: dbt and Airflow share libraries (jinja2, protobuf, ...).
# Installing dbt into Airflow's Python risks a version clash that breaks the
# SCHEDULER, usually at upgrade time. A venv gives dbt its own dependency tree.
# Rule of thumb (Note 4.1): bake in TOOLS (dbt), mount in CODE (battery_dbt/,
# load_raw.py) so editing a model never needs a rebuild.
# =============================================================================

# Pinned base: same Airflow as before, Python 3.12 (checked: 3.12.11).
FROM apache/airflow:3.0.6

# Root only for the install, so the venv is read-only for tasks at runtime.
USER root

# Same pins as the laptop's .venv-dbt: one source of truth for dbt versions.
COPY requirements-dbt.txt /tmp/requirements-dbt.txt

# 1) create the venv from the image's Python 3.12
# 2) install dbt into it (PIP_USER=false: defensive, see note in chat)
# 3) remove the copied file (keeps the layer clean)
# 4) smoke test: a broken install fails the BUILD, not the first DAG run
RUN python -m venv /opt/dbt-venv \
 && PIP_USER=false /opt/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt \
 && rm /tmp/requirements-dbt.txt \
 && /opt/dbt-venv/bin/dbt --version

# Back to the image's normal non-root user for everything Airflow runs.
USER airflow