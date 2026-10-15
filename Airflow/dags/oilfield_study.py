"""Manual local ML rehearsal: parallel inputs → validation → notebook → outputs.

Dependency pattern inspired by the supplied mini-project's marketvol_dag.py.
Airflow 3 APIs; no stock downloads, cloud writes, or import-time training.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shlex import quote

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

ROOT = Path(__file__).resolve().parents[2]
PYTHON = quote(str(ROOT / ".venv/bin/python"))


def task(name, code):
    return BashOperator(
        task_id=name, bash_command=f"{PYTHON} - <<'PY'\n{code}\nPY\n",
        cwd=str(ROOT), execution_timeout=timedelta(minutes=20),
    )


with DAG(
    dag_id="interview_oilfield_ml", schedule=None, catchup=False,
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc), max_active_runs=1,
    default_args={"owner": "interview", "retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["interview", "local", "ml"],
    doc_md="""Runs the visible study notebook locally. Input checks run in parallel;
    a failed check blocks training. No Snowflake connection is required. Outputs
    go to `.cache/oilfield_ml/`. Do not run this and a manual notebook concurrently.
    `owner` identifies responsibility, not a database login.""",
) as dag:
    logs = task("check_well_logs", """
import pandas as pd
d = pd.read_parquet('data/force2020_logs.parquet')
assert d['id'].is_unique and d['WELL'].nunique() == 5
assert {'GR', 'RHOB', 'NPHI', 'DTC', 'RDEP', 'CALI', 'SP', 'FORCE_2020_LITHOFACIES_LITHOLOGY'} <= set(d)
print('Well-log input checked:', len(d))
""")
    telemetry = task("check_telemetry", """
import pandas as pd
d = pd.read_parquet('data/threew_real_events.parquet')
assert d['id'].is_unique and d['source_file'].nunique() == 2
assert {'timestamp', 'P-TPT', 'T-TPT', 'P-MON-CKP', 'T-JUS-CKP', 'class'} <= set(d)
assert not d.duplicated(['source_file', 'timestamp']).any()
print('Telemetry input checked:', len(d))
""")
    train = BashOperator(
        task_id="execute_study", bash_command=f"{PYTHON} Airflow/run_study.py",
        cwd=str(ROOT), execution_timeout=timedelta(minutes=30),
    )
    verify = task("verify_predictions", """
import json
from pathlib import Path
import pandas as pd
p = Path('.cache/oilfield_ml')
card = json.loads((p / 'model_card.json').read_text())
assert card['cloud_deployed'] is False
for name, probability in [('log_predictions.csv', 'probability_sandstone'),
                           ('telemetry_predictions.csv', 'probability_slugging')]:
    d = pd.read_csv(p / name)
    assert len(d) and d['id'].is_unique and d[probability].between(0, 1).all()
    assert d['model_version'].notna().all()
    print(name, len(d), 'valid predictions')
""")
    [logs, telemetry] >> train >> verify
