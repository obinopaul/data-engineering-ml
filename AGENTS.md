# Interview Workspace Guide

## Scope

Work in `main/`. Keep each tool directly in its own folder. Reuse focused components rather than copying complete example projects or datasets. Keep instructions short and practical.

## One environment

Use **only `main/.venv`** for every script and notebook. All runtime requirements are in `pyproject.toml`; `bash install_tools.sh` installs them together. Do not create additional environments or separate setup/source documents. The installation is not verified until dependency resolution and package checks pass.

## Components

| Component | Entry point and responsibility |
|---|---|
| ThreeWToolkit | Read [its API guide](ThreeWToolkit/AGENTS.md); use `interview_starter.ipynb` for ML |
| Airflow | `Airflow/start.sh` starts local Airflow; `Airflow/dags/` contains task and dbt DAGs |
| Ingestion | `python -m Ingestion.run CONFIG` uses dlt REST/SQL/file readers and Snowflake loading; read [its guide](Ingestion/README.md) |
| dbt | Starter plus demo/real event workloads; read [README](dbt/README.md), [input contract](dbt/INPUT_CONTRACT.md) and [contributor guide](dbt/AGENTS.md) before edits |
| Snowflake | `Snowflake/connection.py` reads the same local `dbt/profiles.yml`; SQL setup lives in `Snowflake/sql/` |
| Kafka | `Kafka/producer.py`, `consumer.py`, and optional local broker `compose.yml` |
| Spark | `datasources.py` for files/JDBC; `kafka_wordcount.py` demo; `kafka_to_snowflake.py` connects JSON microbatches to the dlt loader |
| Streamlit | `Streamlit/app.py` previews user-supplied CSV/Parquet files |
| Worked ML study | `oilfield_ml_case_study.ipynb`: executed FORCE held-out-well classification/regression and limited 3W window/clustering/replay examples; preserve `interview_starter.ipynb` |
| Power BI | `PowerBI/README.md`: three focused existing reports/templates, Snowflake connector instructions and model-output dashboard recipe |

## Working conventions

`Ingestion/vendor_sources.py` contains read-only NetSuite SuiteQL and US ADP Workforce Now adapters. Reuse dlt's OAuth/pagination helpers. Keep vendor credentials/certificates out of YAML and tests. Do not assume a new source-type string supplies a connector, or that an ADP contract covers every product/region. Vendor examples load separate RAW tables; use the dbt source_table variable and review transformations before building.

Keep connection settings in ignored `dbt/profiles.yml` and secrets in ignored `.env`. The shared helper resolves exact env_var references. Use `python Snowflake/connection.py --dbt COMMAND` to load `.env` before dbt. Do not print or commit credentials. Keep existing source credits in code comments.

Use `COMPUTE_WH` for this user's initial connection. Account name alone is insufficient; obtain the organization-account identifier. Ingestion uses a stable primary key and merge loads into RAW; dbt builds ANALYTICS. Preserve this separation. API pagination, keys and Spark schema must match the supplied data. Use only one writer per pipeline/checkpoint; keep Airflow DAGs manual until tested. Browser login is interactive; scheduled jobs require unattended authentication.

`Snowflake/sql/000_bootstrap.sql` provisions the interview database/role and assigns the current user; YAML names do not prove cloud objects exist. `--login-only` avoids depending on those objects. Password/MFA is interactive too; use key pairs for unattended tasks. The local `data/practice.csv` is only a tiny rehearsal input, selected by `Ingestion/pipeline.yml`.

No interview dataset is selected. Leave ingestion, training, exports and cloud operations explicitly configurable. For ML, split before fitting preprocessing and keep identifiers/targets out of features. Preserve notebook placeholders.

`data/README.md` describes four public oilfield practice datasets in five tables, with matching ingestion YAMLs. Preserve provenance, original nulls and separate Volve acquisition frames. Depth-indexed wireline logs are not timestamped telemetry; the 3W subset supports historical replay. Technical row IDs and source-instance labels are not model features. Prepared examples do not authorize starting cloud loads or schedules.

Use `.cache/` for generated service state. Avoid adding empty runtime/output folders; toolkit runs may create their own output when used. Check changed code and report actual validation. Do not describe syntax checks as a running pipeline. Keep the root README as the main starting point.

For requested analytics/ML changes, add documented cells to the working study notebook so the workflow remains visible. `python Airflow/run_study.py` executes those same cells with IPython and captures outputs without kernel sockets. Its manual `interview_oilfield_ml` DAG checks inputs in parallel, executes the notebook and verifies exports. Artifacts live in `.cache/oilfield_ml/`; do not run two study executions concurrently. Do not select models on the final test well or describe the two same-well 3W recordings as independent validation. Registry code is opt-in and unverified remotely. Power BI archive inspection is not Desktop rendering or refresh validation.
