# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Adapted excerpt from Apache Airflow's tutorial.py; source in ../README.md.
from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    "interview_task_dependencies",
    default_args={"depends_on_past": False, "retries": 1, "retry_delay": timedelta(minutes=5)},
    schedule=None,
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["interview", "example"],
) as dag:
    t1 = BashOperator(task_id="print_date", bash_command="date")
    t2 = BashOperator(task_id="sleep", bash_command="sleep 5", retries=3)
    t3 = BashOperator(
        task_id="templated",
        bash_command='echo "{{ ds }}"; echo "{{ macros.ds_add(ds, 7) }}"',
    )
    t1 >> [t2, t3]
