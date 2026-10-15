# Interview Quick Start

**Run commands from `main/`. Every Python tool uses the same `.venv`.**

## Study the complete ML example

Open **[oilfield_ml_case_study.ipynb](oilfield_ml_case_study.ipynb)** for the 20-minute reading route, or [read the executed HTML](oilfield_ml_case_study.html) without Jupyter: real well-log data, preprocessing, grouped tuning, classical models/MLP, performance and Shapley plots, 3W window features/clustering/replay, regression, persistence and optional Snowflake deployment. Keep `interview_starter.ipynb` for the actual assessment.

```bash
source .venv/bin/activate
jupyter lab oilfield_ml_case_study.ipynb
# Or execute the same cells locally without a Jupyter server:
python Airflow/run_study.py
```

Use the `main/.venv` kernel. The headless command writes `.cache/oilfield_ml/study.executed.ipynb`, plots, model files and prediction CSVs. [PowerBI/README.md](PowerBI/README.md) has three existing reports/templates and Snowflake connection steps. For orchestration, `bash Airflow/start.sh`, then manually trigger `interview_oilfield_ml`. [Airflow/README.md](Airflow/README.md) explains UI login versus Snowflake task credentials. Local study execution makes no cloud writes.

## Prepare once

```bash
source .venv/bin/activate
bash install_tools.sh
python -c "import dlt; print(dlt.__version__)"
```

The installer targets `.venv` even without activation. It installs packages; it does not start services or log into Snowflake. **dlt 1.31.0 and the practice CSV preview now work; installed packages pass `pip check`.** External services and vendor authentication still need their own checks. Spark also needs Java 17 (or another supported version); Kafka needs Docker. First Spark use downloads connector JARs.

## Connect Snowflake and dbt

Your profile now contains the account/user you entered and uses the existing **`COMPUTE_WH`**. `INTERVIEW_DB` and `INTERVIEW_ROLE` are intended names; writing them in YAML does **not** create them in Snowflake.

**One-time setup:** open [Snowflake/sql/000_bootstrap.sql](Snowflake/sql/000_bootstrap.sql) in a Snowsight SQL worksheet and run the entire file using your existing admin user. It creates the database/schemas and role, grants access to `COMPUTE_WH`, assigns the role to the signed-in user, and checks reads/writes. It creates no warehouse or extra user. Successful final output is `INTERVIEW_ROLE, 1, 1`. This replaces running the numbered setup pieces separately.

The local profile now selects **password with MFA**, reading `SNOWFLAKE_PASSWORD` from your ignored `.env`. The helper below loads `.env` automatically; activation alone does not load it. A password is not an API key. Keep it local; complete any MFA step required by Snowflake. `externalbrowser` is an alternative for accounts configured for browser-based SSO. [Authentication/setup details](Snowflake/README.md).

After `bash install_tools.sh` succeeds:

```bash
# Tests account/password before requiring the interview role/database.
python Snowflake/connection.py --login-only
# Optional terminal alternative to running 000_bootstrap.sql in Snowsight:
# python Snowflake/connection.py --setup
python Snowflake/connection.py
python Snowflake/connection.py --dbt debug
```

`--setup` needs your user's existing ACCOUNTADMIN access. Normal ingestion/dbt work uses `INTERVIEW_ROLE`. Use the `--dbt` launcher so dbt receives the password from `.env`; it selects this workspace's project, profile and `.venv` automatically. Once setup is complete, do not repeat it for each load.

Snowflake hosts the stored tables. `COMPUTE_WH` supplies query compute. dbt runs locally and sends transformation SQL to Snowflake. Kafka and Spark can start without Snowflake. Airflow and the streaming sink require unattended key-pair authentication before use; password/MFA is for this interactive rehearsal.

**Expanded dbt practice:** [dbt/README.md](dbt/README.md) covers staging, dimensions, incremental facts, reporting marts, seeds, snapshots, macros and tests. Run `python Snowflake/connection.py --dbt deps` once. After connecting Snowflake, start the synthetic demo with `python Snowflake/connection.py --dbt build --vars '{workload: demo}' --exclude test_type:unit`, then run its unit tests as shown in that guide. Demo outputs use `ANALYTICS_DEMO`; existing ingestion commands keep the starter workload. [Input contract](dbt/INPUT_CONTRACT.md) explains adapting real assessment data.

## Load files or an API, then transform

For oilfield practice, start with [the dataset guide](data/README.md): actual Volve wireline curves, FORCE well logs and casing depths, and real 3W telemetry. Five prepared tables have matching `Ingestion/<stem>.example.yml` configs; for example, `python -m Ingestion.run Ingestion/volve_wireline_gr.example.yml --preview 5`.

```bash
# Already prepared: data/practice.csv and Ingestion/pipeline.yml.
# For your own input, change location/glob/primary_key in that YAML.
python -m Ingestion.run Ingestion/pipeline.yml --preview 5
python -m Ingestion.run Ingestion/pipeline.yml
python Snowflake/connection.py --dbt build
```

For REST, copy `Ingestion/api.example.yml` to `Ingestion/api.yml`, set the endpoint, response selector and pagination, then substitute that filename in the commands above. **Examples contain placeholders.** [Ingestion guide](Ingestion/README.md) covers CSV, Excel, Parquet, JSONL, URLs, SQL/ODBC, authentication and a tiny practice file.

`pipeline.yml` currently selects **`main/data/practice.csv`**. For `main/data/interview.csv`, set `location: data` and `glob: interview.csv`. `glob: '*.csv'` selects every matching CSV in that directory. The YAML is read by `python -m Ingestion.run`; it does not execute itself.

Default route: input → `INTERVIEW_DB.RAW.SAMPLE_TABLE` → dbt models in `ANALYTICS`. Set a stable primary key; update the dbt `id` tests if your key differs. Edit the SQL models to implement the assessment's transformations. Supplied Snowflake data can be referenced directly without extraction:

```bash
python Snowflake/connection.py --dbt build \
  --vars '{source_database: SHARED_DB, source_schema: PUBLIC, source_table: PROVIDED_TABLE}'
```

Replace those example names and obtain SELECT access. Your profile database/schema remains the writable destination.

### Third-party application examples

`Ingestion/run.py` is the entry script invoked by `python -m Ingestion.run`. Its `source.type` selects a reader. The [ingestion guide](Ingestion/README.md) now includes official API references and credential setup for **NetSuite customers** (`Ingestion/netsuite.example.yml`) and **US ADP workers** (`Ingestion/adp.example.yml`). Run either with `python -m Ingestion.run PATH_TO_YAML --preview 5`, then remove the preview flag to load its separate RAW table. Both require vendor API access/certificates; Snowflake credentials alone are insufficient.

**Neither example opens a login browser.** An administrator provisions the application's credentials/certificates first; the script exchanges them for an access token automatically. Without vendor API access, start with `Ingestion/pipeline.yml` and the practice CSV after installation succeeds.

For repeated app sync, select `ELT_CONFIG` and `ELT_SOURCE_TABLE` in `Airflow/dags/ingestion_pipeline.py`, test `interview_elt` manually, then set `ELT_SCHEDULE = "*/5 * * * *"` and unpause it. This polls and merges, then runs dbt; it is not instant change capture. [Source choices and live-sync architecture](Ingestion/README.md#ongoing-data-sync).

## Kafka → Spark → Snowflake → dbt

Configure `Ingestion/api.yml`, adapt `Spark/event_schema.example.json` to the event fields, and set up **key-pair authentication** first. Then start Kafka:

```bash
docker compose -p interview-kafka -f Kafka/compose.yml up -d --wait --wait-timeout 120
docker compose -p interview-kafka -f Kafka/compose.yml exec broker kafka-topics --bootstrap-server broker:29092 --create --if-not-exists --topic interview --partitions 1 --replication-factor 1
```

One complete polling cycle, from the same activated terminal:

```bash
set -o pipefail
python -m Ingestion.run Ingestion/api.yml --jsonl | python Kafka/producer.py localhost:9092 interview --key-field id
spark-submit --master 'local[2]' \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0 \
  Spark/kafka_to_snowflake.py Ingestion/api.yml
python Snowflake/connection.py --dbt build
```

Run each command only after the previous succeeds. Match topic/key with your configuration. This polls the API, publishes JSON events, drains Kafka through Spark, merges into Snowflake, then transforms/tests with dbt. Spark exits after available events are processed. For a persistent consumer, add `--continuous` in its own terminal; publish again when new API data is available. dbt must still run separately or on a schedule.

## Start only what the question needs

Activate `.venv` in each new terminal. No reinstall is needed after successful setup.

| Tool | Command / next action |
|---|---|
| ML notebooks | `jupyter lab interview_starter.ipynb` |
| Airflow | `bash Airflow/start.sh`, then open its printed URL/login |
| File/API ELT DAG | Trigger `interview_elt` after configuring `Ingestion/pipeline.yml` |
| Streaming DAG | Trigger `interview_api_stream`; API → Kafka → Spark/load → dbt |
| Spark shell | `pyspark --master 'local[2]'` |
| File preview app | `streamlit run Streamlit/app.py` |

DAGs start **manual** and use unattended Snowflake authentication. The streaming DAG runs a bounded cycle; change its schedule after a successful rehearsal. Do not run it alongside the continuous Spark consumer with the same checkpoint. ML prediction and Power BI remain assessment-specific additions, not automatic parts of this starter.

Stop long-running terminals with Ctrl+C. Stop Kafka without deleting its containers:

```bash
docker compose -p interview-kafka -f Kafka/compose.yml stop
```

Kafka `down` deletes this disposable broker's data. Keep Spark/dlt state in `.cache/` for restarts, and ensure your Snowflake warehouse suspends when idle. Agent instructions: [AGENTS.md](AGENTS.md).
