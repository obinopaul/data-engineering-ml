"""Local bounded ELT DAGs. Same .venv and dbt profile; no credentials in tasks."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shlex import quote

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

ROOT = Path(__file__).resolve().parents[2]
ENV = {"PATH": f"{ROOT / '.venv/bin'}:/usr/local/bin:/usr/bin:/bin"}

# Select one source for interview_elt; see Ingestion/README.md's sync table.
ELT_CONFIG = "Ingestion/pipeline.yml"
ELT_SOURCE_TABLE = "SAMPLE_TABLE"
# After a successful manual run, "*/5 * * * *" polls every five minutes.
ELT_SCHEDULE = None


def task(task_id, command):
    return BashOperator(
        task_id=task_id, bash_command="set -euo pipefail\n" + command,
        cwd=str(ROOT), env=ENV, append_env=True,
        execution_timeout=timedelta(minutes=30),
    )


defaults = {"retries": 1, "retry_delay": timedelta(minutes=1)}

with DAG(
    "interview_elt", start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=ELT_SCHEDULE, catchup=False, max_active_runs=1,
    default_args=defaults, tags=["interview", "ingestion", "dbt"],
) as elt:
    extract_load = task("extract_load", f"python -m Ingestion.run {quote(ELT_CONFIG)} --unattended")
    transform = task(
        "transform_test",
        "python Snowflake/connection.py --dbt build --vars "
        + quote("{source_table: " + ELT_SOURCE_TABLE + "}"),
    )
    extract_load >> transform

with DAG(
    "interview_api_stream", start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=None, catchup=False, max_active_runs=1,
    default_args=defaults, tags=["interview", "kafka", "spark"],
) as streaming:
    # Defaults match api.example.yml; update broker/topic/key below if changed.
    publish = task("poll_api_to_kafka", """
python -m Ingestion.run Ingestion/api.yml --jsonl |
python Kafka/producer.py localhost:9092 interview --key-field id
""")
    consume_load = task("spark_load", """
spark-submit --master 'local[2]' \\
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0 \\
  Spark/kafka_to_snowflake.py Ingestion/api.yml
""")
    transform = task("transform_test", "python Snowflake/connection.py --dbt build")
    publish >> consume_load >> transform
