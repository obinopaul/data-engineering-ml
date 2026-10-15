"""dbt-only excerpt adapted from Airbyte quickstarts' my_elt_dag.py.

See ../README.md for source and changes. No source-system or dataset is selected.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

MAIN_ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXECUTABLE = str(MAIN_ROOT / ".venv/bin/python")
SNOWFLAKE_HELPER = str(MAIN_ROOT / "Snowflake/connection.py")

with DAG(
    dag_id="interview_dbt",
    default_args={"owner": "airflow", "retries": 1, "retry_delay": timedelta(minutes=5)},
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["interview", "dbt"],
) as dag:
    run_dbt_check_task = BashOperator(
        task_id="run_dbt_precheck",
        bash_command='"$PYTHON_EXECUTABLE" "$SNOWFLAKE_HELPER" --dbt debug && "$PYTHON_EXECUTABLE" "$SNOWFLAKE_HELPER" --dbt list',
        cwd=str(MAIN_ROOT),
        env={"PYTHON_EXECUTABLE": PYTHON_EXECUTABLE, "SNOWFLAKE_HELPER": SNOWFLAKE_HELPER},
        append_env=True,
    )
    run_dbt_model_task = BashOperator(
        task_id="run_dbt_build",
        bash_command='"$PYTHON_EXECUTABLE" "$SNOWFLAKE_HELPER" --dbt build',
        cwd=str(MAIN_ROOT),
        env={"PYTHON_EXECUTABLE": PYTHON_EXECUTABLE, "SNOWFLAKE_HELPER": SNOWFLAKE_HELPER},
        append_env=True,
    )
    run_dbt_check_task >> run_dbt_model_task
