#!/usr/bin/env bash
# Uses the shared .venv; keeps Airflow's database/logs inside .cache.
set -euo pipefail
MAIN_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$MAIN_ROOT/.venv/bin/airflow" ]]; then
    echo 'Run bash install_tools.sh from main first.' >&2
    exit 1
fi
export AIRFLOW_HOME="$MAIN_ROOT/.cache/airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$MAIN_ROOT/Airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False
export AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=True
export PATH="$MAIN_ROOT/.venv/bin:$PATH"
exec "$MAIN_ROOT/.venv/bin/airflow" standalone
