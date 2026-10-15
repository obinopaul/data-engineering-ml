# Airflow

From `main/`, run:

```bash
source .venv/bin/activate
bash Airflow/start.sh
```

Open the URL printed in the terminal and use the login information Airflow provides. Trigger a DAG manually:

- `interview_task_dependencies`: a small example of task ordering and parallel tasks.
- `interview_dbt`: checks the dbt connection, then runs its models and tests. Complete [dbt setup](../dbt/README.md) first. Use key-pair authentication for unattended runs.
- `interview_elt`: reads `Ingestion/pipeline.yml`, extracts/loads into Snowflake, then runs dbt models/tests.
- `interview_api_stream`: polls the configured API into Kafka, runs a bounded Spark-to-Snowflake job, then dbt. Start Kafka first and configure `Ingestion/api.yml` and the Spark event schema. Commands are in the [root checklist](../README.md).
- `interview_oilfield_ml`: checks the two practice inputs in parallel, executes the study notebook, then verifies prediction files. Entirely local; no Snowflake login needed. See [the worked notebook](../oilfield_ml_case_study.ipynb). Do not run it concurrently with manual notebook execution.

The ingestion DAGs start with `schedule=None`. After a successful manual run, set an appropriate cron schedule if required. Keep one active run and do not also run the same Spark pipeline continuously. All scheduled Snowflake tasks need key-pair authentication. For production, replace this standalone service with durable scheduler/worker infrastructure.

`start.sh` only sets the local Airflow paths and starts the service using `.venv`. It replaces the old `activate.sh`; you do not source it or switch Python environments. Logs and Airflow's database are created under `.cache/airflow/` when started. Stop with Ctrl+C.

Adapted from the [Apache Airflow tutorial](https://github.com/apache/airflow/blob/main/airflow-core/src/airflow/example_dags/tutorial.py) and Stage Two's Airbyte dbt DAG.

## Where the DAG and credentials live

A **directed acyclic graph** describes tasks and dependencies. Its Python file lives in `Airflow/dags/`. Airflow's scheduler discovers it; the UI shows its graph and task runs. Airflow stores serialized definitions, task states and scheduling records in its **metadata database**, here under `.cache/airflow/`. Your oilfield data lives separately in files or Snowflake. You do not upload a DAG into the Snowflake database.

There are two different logins:

1. **Airflow UI:** `start.sh` launches local standalone Airflow with its Simple auth manager. Use the URL and generated login shown by that process. `owner='interview'` is metadata, not a username/password. Simple auth is intended for development; production needs an appropriate auth manager and access controls.
2. **Task → Snowflake:** existing ingestion/dbt tasks call scripts that load `main/.env` and `dbt/profiles.yml` through `Snowflake/connection.py`. The worker needs access to those local files. This workspace does not additionally require an Airflow Connection for those Bash tasks. Use unattended key-pair authentication before scheduling them.

For a native Snowflake operator/hook, create an Airflow Connection named `snowflake_interview` (type Snowflake) in the UI's Connections screen, or supply it through a supported secrets backend. Configure account, login, role, warehouse, database and private-key authentication there. A hook would then use `SnowflakeHook(snowflake_conn_id='snowflake_interview').get_first('SELECT CURRENT_ROLE()')` **inside a task**. The connection ID is a lookup name; it does not provision the role or grant database access. Do not place credentials directly in a DAG file. [Airflow connections](https://airflow.apache.org/docs/apache-airflow/stable/howto/connection.html), [Simple auth](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/auth-manager/simple/index.html).

## What the supplied mini-project contributed

Reviewed `../apache-airflow-mini-project-main/apache-airflow-mini-project-main/`: its market-volume DAG runs two downloads in parallel, checks files, then calculates an aggregate. `oilfield_study.py` reuses that dependency pattern for the actual local study. Its older `schedule_interval`, operator imports and `provide_context` calls were not copied into Airflow 3. The stock-specific Docker paths, downloads and startup configuration are unnecessary here.

Its `scripts/log_analyzer.py` expects manually combined stock logs. Airflow's task-log viewer already provides per-run logs, so we retain that script in the reference project rather than install a mismatched log parser. Open a failed task → Logs; fix the cause → clear/rerun that task and affected downstream tasks. Retries are safe only when the task's writes are idempotent.

To execute the study without starting Airflow: `python Airflow/run_study.py`. It runs the notebook's cells with IPython in the same `.venv`, captures tables/plots, and writes `.cache/oilfield_ml/study.executed.ipynb`. It does not start a separate kernel/server. The DAG remains manual and uses the same command. Multi-worker production deployment would need shared artifact storage and distributed locking instead of these local paths.
