# Extract, load, then transform

This component uses the existing open-source [dlt project](https://github.com/dlt-hub/dlt). Its maintained REST, SQL and filesystem readers do the extraction, and its Snowflake destination does the loading. `run.py` is a small workspace adapter that selects those components and reuses your dbt profile. No extra server, Python environment or cloned example project is needed. dlt 1.31.0 is installed and the practice CSV preview works. Vendor authentication and Snowflake loading remain separate validation steps.

## Which Python file runs?

Yes: **`Ingestion/run.py`** is the entry script. From `main/`:

```bash
python -m Ingestion.run Ingestion/pipeline.yml --preview 5
```

`-m Ingestion.run` tells Python to run that module; `Ingestion/pipeline.yml` is its configuration argument. Prefer this form over `python Ingestion/run.py` because the module form keeps imports from other workspace folders working.

The call sequence is `main()` → `read_config()` → `source_resource()` → preview or `load()`. `read_config()` turns YAML into a Python dictionary. `source = config["source"]` selects its `source:` section; `source["type"]` chooses the reader. A REST source reads `base_url` from that same section in `api.example.yml`. It does not come from Snowflake or a hidden configuration file.

**dlt** means **data load tool**, an open-source Python library for extraction, normalization and loading; it is separate from dbt's SQL transformations. [dlt introduction](https://dlthub.com/docs/intro).

It is already declared as `dlt[snowflake,sql_database]==1.31.0` in `pyproject.toml`; the NetSuite adapter additionally uses `PyJWT[crypto]`. Install everything into the existing environment:

```bash
source .venv/bin/activate
bash install_tools.sh
python -c "import dlt; print(dlt.__version__)"
```

The focused equivalent is `python -m pip install 'dlt[snowflake,sql_database]==1.31.0' 'PyJWT[crypto]>=2.10,<3' python-dotenv`, using that same activated `.venv`. The complete installer remains preferred when preparing the entire workspace. No reinstall is needed for the working dlt installation.

If you see `ModuleNotFoundError: No module named 'dlt'`, installation has not completed for the Python interpreter running the command. Activating `.venv` only selects the environment; it does not install anything. Run the installer successfully before ingestion. If it fails, keep its first error: a DNS failure, a version-resolution failure and a missing system driver require different fixes. The CLI now checks for dlt before contacting any source and prints the installation command.

## Will OAuth open a browser?

**No browser opens in these two examples.** OAuth has several authorization flows; these adapters use client credentials for application-to-application access. A browser login/consent flow would require a different implementation, including a registered redirect URL and token handling.

1. **Provision access once:** your NetSuite administrator registers/maps the integration, role and public certificate; your ADP provider provisions the entitled application, client credentials and accepted certificate. This administrative work may happen in their websites.
2. **Configure locally:** put the resulting IDs/secret and certificate file paths in the existing `main/.env`, following the vendor sections below. These are application credentials, not your Snowflake login or an ordinary portal password.
3. **Run extraction:** when the reader first requests data, it contacts the vendor token endpoint, obtains an access token and uses it for API calls. The adapters request a replacement before token expiry during a long run.

Even `--preview 5` requires real vendor API access: preview skips Snowflake loading, not source authentication. If you do not have NetSuite/ADP API access yet, use `Ingestion/pipeline.yml` to learn with `data/practice.csv`; the application YAMLs are integration templates, not public demo accounts. [NetSuite client credentials](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162755359851.html), [ADP system-to-system authorization](https://marketplace-cdn.adp.com/dev-portal/pdf/Understanding_the_Data_Connector_App_Authorization_Process).

## Source types and systems

`source.type` is a selector implemented by our code. Writing a new name in YAML does not automatically install or implement a connector.

| Source | How this starter handles it |
|---|---|
| CSV, Parquet, JSONL | `type: files`; choose `format`, `location`, `glob` |
| Excel `.xlsx` | `type: excel`; choose `path` and `sheet` |
| Generic REST API | `type: rest`; endpoint, selector, paginator and optional bearer token |
| PostgreSQL / other SQL databases | `type: sql`; SQLAlchemy URL plus a compatible driver |
| ODBC database | Still `type: sql`, e.g. SQL Server through `mssql+pyodbc`; requires the vendor ODBC driver |
| Object storage / files in a data lake | `type: files` with a URL such as `s3://bucket/prefix`; cloud filesystem driver and credentials are additional requirements |
| Athena / Databricks | Need their query connector/dialect, permissions and supported query route; not preconfigured by changing the type |
| MongoDB | Needs a MongoDB reader/connector; it is not covered by our SQL-table reader |
| Stripe, HubSpot, GitHub, Linear, etc. | Use their supported REST contract or an existing vendor connector; OAuth, permissions and pagination vary |
| NetSuite / ADP | New `type: netsuite` / `type: adp` adapters in `vendor_sources.py`; setup below |

## Where each step happens

**dlt** is the Python data-loading library doing the extract/load work; **dbt** is the separate SQL transformation tool. `__init__.py` is simply the Python package marker, not an ingestion job.

## What `pipeline.yml` actually does

`Ingestion/pipeline.yml` is a text configuration file. It does nothing on its own. This command reads it and calls the matching dlt reader/loader:

```bash
python -m Ingestion.run Ingestion/pipeline.yml
```

The current practice configuration is:

```yaml
pipeline_name: interview_files
dataset: raw
table: sample_table
primary_key: id
write_disposition: merge
source:
  type: files
  location: data
  glob: practice.csv
  format: csv
```

| Setting | Meaning in this workspace |
|---|---|
| `pipeline_name` | Name for dlt's processing state under `.cache/dlt/` |
| `dataset: raw` | Snowflake schema `RAW`, inside the profile's `INTERVIEW_DB` |
| `table: sample_table` | Destination table `RAW.SAMPLE_TABLE` |
| `primary_key: id` | Input column identifying a record |
| `write_disposition: merge` | Update matching IDs and insert new IDs; reruns do not simply append every row |
| `location: data` | Directory `main/data/`, not `main/Ingestion/data/` |
| `glob: practice.csv` | Only `main/data/practice.csv` |
| `glob: '*.csv'` | Every matching CSV in `main/data/`, loaded into the same table; use compatible schemas |
| `format: csv` | Select dlt's CSV reader |

To use your own file, put it at **`main/data/interview.csv`**, set `glob: interview.csv`, and update `primary_key` if it has no `id` column. For a different directory, change `location` to that directory or an absolute path. The `.example.yml` file is only a reusable template; your command explicitly selects which YAML to run.

Start with `python -m Ingestion.run Ingestion/pipeline.yml --preview 5`: it prints input rows without loading Snowflake. Remove `--preview 5` to load. Then run `python Snowflake/connection.py --dbt build` to transform/test the loaded table. Preview still requires the dlt package to be installed.

## Pipeline flow

```mermaid
flowchart LR
    A[CSV / Excel / Parquet / REST / SQL] --> B[dlt extraction]
    B --> C[Snowflake RAW]
    C --> D[dbt SQL and tests]
    D --> E[Snowflake ANALYTICS]
    E -. future integration .-> F[ML / Power BI]
    G[REST polling] --> H[Kafka topic]
    H --> I[Spark microbatches]
    I --> J[dlt loader]
    J --> C
```

**Extract** reads the source. **Load** writes warehouse tables. **Transform** runs your business SQL. That ordering is ELT; Spark transformations before loading add an ETL step. Airflow coordinates these commands; it is not the database or message broker.

| File | Change here |
|---|---|
| `pipeline.example.yml` → `pipeline.yml` | File/Excel/SQL source, target schema/table, stable primary key |
| `api.example.yml` → `api.yml` | API endpoint, pagination, selector, optional bearer token variable |
| `run.py` | Existing reader selection and shared Snowflake loading adapter |
| `../Spark/event_schema.example.json` | JSON fields/types expected by Spark |
| `../Spark/kafka_to_snowflake.py` | Add Spark transformations or inference before `write_batch` |
| `../dbt/models/` | Business SQL, model relationships and quality tests |
| `../Airflow/dags/ingestion_pipeline.py` | Ordered batch/streaming tasks and schedule |

## First file load

Run from `main/`, using `.venv`. Configure Snowflake as described in the root README first. A two-row practice file and local YAML have already been created. If recreating them later, use the following only when the practice file is absent:

```bash
mkdir -p data
printf 'id,event_time,value\n1,2026-01-01T00:00:00Z,10\n2,2026-01-01T00:01:00Z,12\n' > data/practice.csv
test -e Ingestion/pipeline.yml || cp Ingestion/pipeline.example.yml Ingestion/pipeline.yml
```

Set `glob: practice.csv` in that local configuration. `dataset: raw` and `table: sample_table` match the dbt starter. `primary_key: id` identifies a record for merge updates.

```bash
python -m Ingestion.run Ingestion/pipeline.yml --preview 5
python -m Ingestion.run Ingestion/pipeline.yml
python Snowflake/connection.py --dbt build
```

Preview reads the source but does not connect to Snowflake. It displays actual rows locally. Loading prints a load report and raises on failed jobs. In Snowsight, verify:

```sql
SELECT * FROM INTERVIEW_DB.RAW.SAMPLE_TABLE LIMIT 10;
SELECT * FROM INTERVIEW_DB.ANALYTICS.MY_SECOND_DBT_MODEL LIMIT 10;
```

Rerunning merges rows sharing the configured key. Use a unique **event ID** to keep event history; an entity ID instead keeps that entity's latest loaded record. Null keys fail. Repeated keys with conflicting values in one ordinary file/API load require an explicit ordering rule before loading. The starter reads the selected source again on each run; it does not automatically implement source change tracking or deletes.

## Other inputs

- **Parquet / JSONL:** change `format` and `glob`. CSV accepts pandas `reader_options`, such as `delimiter` or `dtype` to preserve identifiers. Paths resolve from `main/`.
- **Excel:** use the commented `type: excel`, `path`, and `sheet` block. pandas/openpyxl reads one worksheet into memory; use CSV/Parquet for large extracts.
- **File URL:** set `location` to the full downloadable CSV/Parquet/JSONL URL and `glob: ''`. An HTML page containing a download link is not itself a data file.
- **SQL / ODBC:** use the commented `type: sql` block. The SQLAlchemy reader fetches a named table in chunks. For SQL Server, the connection URL can look like `mssql+pyodbc://user:URL_ENCODED_PASSWORD@host/database?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes`. `pyodbc` is declared; unixODBC and the vendor driver must also be installed on the machine. PostgreSQL/MySQL need their corresponding Python drivers. [SQL source reference](https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration).

Set a source connection string without putting it in shell history:

```bash
read -rsp 'Source database URL: ' SOURCE_DATABASE_URL; echo
export SOURCE_DATABASE_URL
```

This is a connection setting, not a second Python environment. Airflow must inherit it when started, or use a deployment secret manager. The Snowflake destination still uses `dbt/profiles.yml`.

## REST APIs

Copy `api.example.yml` once. Replace `base_url`, endpoint `path`, `data_selector` and paginator with the API's actual contract. The supplied example expects `{"data": [...], "next": "next-page-url-or-null"}`. For a single JSON array, use `data_selector: '$'` and `paginator: single_page`. dlt also supports page-number, offset and cursor pagination; use the provider's documented fields. [REST configuration](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic).

For bearer authentication, uncomment `token_env: SOURCE_API_TOKEN` and enter it locally:

```bash
read -rsp 'API token: ' SOURCE_API_TOKEN; echo
export SOURCE_API_TOKEN
python -m Ingestion.run Ingestion/api.yml --preview 5
python -m Ingestion.run Ingestion/api.yml
```

Preview may fetch an entire API page to display five records. The generic `type: rest` adapter supports public APIs or bearer tokens. The NetSuite/ADP adapters below add their specific OAuth and certificate flows; other authentication schemes still need a matching adapter. Configure timeouts/rate limits and pagination against the real endpoint before scheduling. Do not assume every API uses `page`, `since`, or `next`.

## NetSuite example: ERP customers

Use [netsuite.example.yml](netsuite.example.yml). It selects `type: netsuite`, the customer query, and destination `RAW.NETSUITE_CUSTOMERS`. Both examples are **REST integrations**; the application name selects the vendor-specific adapter.

The NetSuite adapter calls these account-specific endpoints:

```text
POST https://<account-id>.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token
POST https://<account-id>.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql
```

The second POST executes a read-only query, not a customer update. The default query is `SELECT id, entityid FROM customer ORDER BY id`; confirm those fields and permissions in your account's Records Catalog. Requests use `Prefer: transient`, `limit` and `offset`; records come from the response's `items` array. [Oracle SuiteQL documentation](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157909186990.html).

Before connecting, a NetSuite administrator must enable the required REST/OAuth features, create an integration with the M2M client-credentials grant, and map the integration, entity, role and public certificate. Obtain the client ID and generated certificate ID. Use the appropriate read permissions for customer analytics. Sandbox mappings must be configured separately. [Integration records](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157771733782.html), [certificate mapping](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162686838198.html).

Add these values to your **existing** `main/.env`, preserving its Snowflake entry:

```dotenv
NETSUITE_ACCOUNT_ID=YOUR_ACCOUNT_URL_PREFIX
NETSUITE_CLIENT_ID=YOUR_INTEGRATION_CLIENT_ID
NETSUITE_CERTIFICATE_ID=YOUR_MAPPED_CERTIFICATE_ID
NETSUITE_PRIVATE_KEY_PATH=.cache/keys/netsuite_private.pem
# NETSUITE_PRIVATE_KEY_PASSPHRASE=YOUR_PASSPHRASE_IF_ENCRYPTED
```

The account prefix is the one used in your NetSuite URL, for example `1234567-sb1`; it is not your Snowflake account. This adapter signs PS256 assertions, so supply the matching **RSA** private key and registered X.509 certificate. Oracle accepts RSA keys of 3072 or 4096 bits. [Certificate conditions](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/subsect_162755332391.html).

The signed assertion contains the client ID, certificate ID, REST scope, token URL and expiry; it is exchanged for a bearer access token. dlt caches that token in memory and requests another before expiry. No NetSuite user password or client-secret substitution is involved in this M2M flow. [Token request](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162755359851.html), [assertion structure](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162790605110.html).

After installation and vendor setup, from `main/`:

```bash
python -m Ingestion.run Ingestion/netsuite.example.yml --preview 5
python -m Ingestion.run Ingestion/netsuite.example.yml
python Snowflake/connection.py --dbt build --vars '{source_table: NETSUITE_CUSTOMERS}'
```

Preview may retrieve a whole page. Copy the example to `netsuite.yml` if you want a personal query. The query needs a unique ordering; use bounded ID/date ranges for large extracts. SuiteQL has a 100,000-result ceiling and collection paging has a 1,000-page bound. The adapter fails conservatively at either bound rather than claiming a complete extraction. [Collection paging](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156414087576.html).

## ADP example: HRIS worker records

Use [adp.example.yml](adp.example.yml), which loads `RAW.ADP_WORKERS`. This targets the **US Workforce Now workers contract**, not every ADP payroll/product API:

```text
POST https://accounts.adp.com/auth/oauth/v2/token
GET  https://api.adp.com/hr/v2/workers?$top=50&$skip=0
```

You need an ADP application/subscription entitled to this client's workers data, its client ID/secret, and an ADP-accepted client certificate with its matching private key. A normal portal login alone does not provide this API access. Other ADP regions/products can have different endpoints, entitlements and response fields. [Product API guides](https://developers.adp.com/guides/api-guides).

Add to your existing `.env`:

```dotenv
ADP_CLIENT_ID=YOUR_CLIENT_ID
ADP_CLIENT_SECRET=YOUR_CLIENT_SECRET
ADP_CERT_PATH=.cache/keys/adp_client_certificate.pem
ADP_PRIVATE_KEY_PATH=.cache/keys/adp_private_key.pem
```

The certificate authenticates the application at the TLS connection layer; the bearer token authorizes API access. The adapter sends the certificate for **both token and worker requests**, and uses HTTP Basic client credentials for the token exchange. [ADP data-connector authorization flow](https://marketplace-cdn.adp.com/dev-portal/pdf/Understanding_the_Data_Connector_App_Authorization_Process).

This Requests-based mTLS path requires a PEM private key readable without an interactive passphrase; provision and protect it according to your ADP credential process. Server certificate verification stays enabled. [Requests certificate support](https://docs.python-requests.org/en/latest/user/advanced/#client-side-certificates).

Workers are read from the `workers` response array using `$top`/`$skip`, continuing until HTTP 204 or an empty array. The adapter maps `associateOID` to `id` for the common merge key and retains only the top-level fields in `include_fields` (default: identifier and worker status). That projection happens **after** receiving the response; it does not reduce what ADP sends. [Workforce Now workers/pagination](https://developers.adp.com/articles/preview/guide-worker-management-api-guide-for-adp-workforce-now-1?chapter=2).

```bash
python -m Ingestion.run Ingestion/adp.example.yml --preview 5
python -m Ingestion.run Ingestion/adp.example.yml
python Snowflake/connection.py --dbt build --vars '{source_table: ADP_WORKERS}'
```

Use authorized test data for the preview, which prints selected rows. `max_pages` is a failure guard, not a request to silently stop after that many pages. Identical consecutive pages fail so an ignored `$skip` cannot create an endless successful-looking extraction.

Both dbt commands reuse the same starter output model names: running one after the other replaces those model outputs with the selected source's data. For simultaneous ERP/HRIS analytics, create separate dbt models and relationships. The RAW source tables remain separate.

## Reliability and scope of the app examples

`vendor_sources.py` supplies the vendor-specific OAuth request and response checks. It reuses **dlt RESTClient, OffsetPaginator and OAuth2ClientCredentials**, plus Requests/urllib3 retry handling and PyJWT signing. It does not replace those libraries with a new ingestion framework. [dlt REST/OAuth extension points](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced).

Connections have timeouts; transient HTTP 429/5xx responses receive bounded retry counts with backoff/Retry-After handling. Unexpected redirects, authentication/permission failures, missing response arrays and invalid token responses fail the extraction. Tokens refresh on expiry; revoked-token HTTP 401 errors fail the run rather than looping forever. Provider credentials are not written into YAML or printed by the adapters.

These are **full paginated polls**, with Snowflake merge loads. They do not implement vendor CDC, deletion capture or durable source watermarks. Offset pages can shift while source records change; production incremental loads need the vendor's supported change contract, overlap/reconciliation and stable keys. The examples have not been authenticated against real NetSuite/ADP accounts.

For Airflow, select the vendor YAML and matching source table using the settings below. For telemetry, keep the existing **producer → Kafka → Spark → Snowflake** route, with a device/event schema and event ID. ERP/HRIS polling is useful for contextual joins; it is not itself an IoT event stream. A real device protocol or vendor event feed still needs its own producer/consumer adapter.

## Ongoing data sync

### How production connectors keep data current

The **dlt library** can handle extraction, normalization, loading and persisted incremental state in a production pipeline. Our Python command runs once and exits; Airflow or another scheduler must invoke it again. Adding credentials does not register a subscription to future source changes. [dlt production execution](https://dlthub.com/docs/running-in-production/running).

A typical polling cycle is: **scheduler → queued job → connector worker → read saved cursor → fetch changed records → load/merge → commit checkpoint → run downstream transformations**. The first run often copies a snapshot. Later runs can request changes since a timestamp or vendor change token. Advance a committed checkpoint only when the corresponding destination data is durable. Retrying may reread records, so stable keys and idempotent writes are essential. Use an overlap window/reconciliation for late updates and a separate deletion strategy when the API does not expose deleted records. [dlt cursor handling](https://dlthub.com/docs/general-usage/incremental/cursor), [state persistence](https://dlthub.com/docs/general-usage/incremental/advanced-state).

Airbyte supplies a platform around connectors: stored connection/job metadata, scheduling/workflows, workers and workload launching, plus logging and alerting. Its documented architecture uses Temporal task queues and Kubernetes connector workloads. This describes Airbyte's architecture; it is not a claim about Fivetran's private internals. [Airbyte architecture](https://docs.airbyte.com/platform/understanding-airbyte/high-level-view).

| Mechanism | How changes are discovered | What controls freshness |
|---|---|---|
| API polling | Ask for records changed since a saved timestamp/token, when supported | Schedule, source visibility delay, quotas and job duration |
| Database CDC | Read committed inserts/updates/deletes from a database change log | Connector mode, log retention and consumption/flush lag |
| Webhooks/event streams | Source sends an event to a receiver or broker | Event delivery, durable queue and consumer lag |

CDC describes how changes are captured, not necessarily continuous execution: Airbyte documents scheduled CDC runs that resume from the prior log position. [Airbyte CDC](https://docs.airbyte.com/platform/understanding-airbyte/cdc).

Fivetran documents fixed intervals, cron schedules and manual triggers. One-minute sync is available for eligible plans/connectors; this does not mean all sources can sync every second or that destination data appears instantly. [Fivetran sync scheduling](https://fivetran.com/docs/core-concepts/syncoverview).

A cron job can start a simple pipeline. A managed platform additionally needs concurrency control, retries/backoff, checkpoint storage, credentials, schema handling, monitoring and recovery. Second-level event delivery normally uses a running receiver/consumer rather than launching a fresh Airflow/dbt process for every record. dbt and dashboard refresh introduce their own latency.

**Current workspace limit:** the NetSuite/ADP adapters perform full paginated reads followed by merges. They do not yet persist a source change cursor, process deletion events or receive webhooks. Their source-specific change contract must be implemented and tested before describing them as incremental production sync.

### Our two data paths

There are two different ways to keep data current:

```mermaid
flowchart LR
    A[NetSuite or ADP REST API] -->|Scheduled polling| B[dlt extract and merge]
    B --> C[Snowflake RAW]
    C --> D[dbt build and tests]
    D --> E[Snowflake ANALYTICS]
    F[Airflow schedule] -. orchestrates each cycle .-> B
    G[Device events or vendor event feed] --> H[Source-specific receiver: still required]
    H --> I[Kafka]
    I --> J[Continuous Spark microbatches]
    J --> C
```

**Periodic application sync:** the existing `interview_elt` DAG can run one selected app's complete extract/load/transform cycle repeatedly. Edit these three settings near the top of `../Airflow/dags/ingestion_pipeline.py`:

| Input | `ELT_CONFIG` | `ELT_SOURCE_TABLE` |
|---|---|---|
| Practice CSV | `"Ingestion/pipeline.yml"` | `"SAMPLE_TABLE"` |
| NetSuite customers | `"Ingestion/netsuite.example.yml"` | `"NETSUITE_CUSTOMERS"` |
| ADP workers | `"Ingestion/adp.example.yml"` | `"ADP_WORKERS"` |

Keep `ELT_SCHEDULE = None` while installing packages, configuring credentials and testing a manual run. With unattended Snowflake authentication configured, start Airflow using `bash Airflow/start.sh`, open its UI and trigger `interview_elt`. Confirm both tasks succeed and inspect the resulting tables. Then change `ELT_SCHEDULE = "*/5 * * * *"`, let Airflow reload the DAG and unpause it. Choose a cadence allowed by the vendor's rate limits and your workload. A five-minute schedule is an example, not a freshness guarantee: polling duration and dbt runtime add latency.

Each cycle merges matching IDs into RAW and runs dbt only after extraction/loading succeeds. Retries and one active run per DAG are configured. The source readers still fetch full results: they have no persisted change cursor or deletion capture. Do not run this DAG and another writer against the same dlt pipeline state, or different source builds against the same dbt output models. This starter selects one source at a time; simultaneous ERP and HRIS reporting needs separate dbt models.

**Event-driven telemetry:** keep Kafka and Spark running while an actual source publishes events. The existing Spark sink supports `--continuous` and checkpoints; the included REST-to-Kafka command publishes one poll, then exits. A continuous producer, authenticated webhook receiver or vendor-supported event consumer must be connected for true ongoing event delivery. Those source-specific components are not implemented by the NetSuite/ADP polling templates. Adding Kafka alone does not turn a periodically queried REST API into a push feed.

Do not put a never-ending Spark job before dbt in the same sequential DAG: dbt would never start. The bounded `interview_api_stream` DAG drains available Kafka events and then builds dbt. With a continuous Spark consumer, schedule dbt separately and give that consumer its own checkpoint/pipeline state. Business-level incremental transformations, late-event handling, deletions, alerts and source-to-warehouse reconciliation still require the actual data contract.

The main Snowflake/dbt route is **ELT**: extract, load RAW, then transform with dbt. Transforming events in Spark before loading is an **ETL** step. Neither route is verified live until dependencies, source access and destination authentication work.

## Streaming and orchestration

Use the exact Kafka/Spark commands in the [root checklist](../README.md). The existing Confluent producer accepts `--key-field id` to route the same key to the same partition. It waits for acknowledgements and reports failed deliveries. `--jsonl` extracts records to that producer without loading Snowflake directly; shell `pipefail` makes extraction failures fail the task.

Spark validates JSON using your schema, retains the original payload and Kafka coordinates, and sends each microbatch to the same dlt merge loader. Malformed JSON or missing keys fail the batch; they are not silently skipped. The default bounded run drains available events and exits. `--continuous` waits for future events. API polling must run again to publish those events; REST polling is not a native change feed.

`interview_elt` performs **extract/load → dbt build**. `interview_api_stream` performs **API poll/publish → Spark/load → dbt build**. Start the broker separately. Both DAGs use `.venv`, retries, a timeout and one active run. Configure the profile for key-pair authentication before triggering. To repeat cycles, change the relevant DAG's `schedule=None` to a suitable cron expression, such as `"*/5 * * * *"`, after testing. Adjust its hardcoded topic/key if you change the defaults.

## What changes for production

This is a configurable local starter, not a deployed production service. The complete path still needs a live rehearsal with installed packages and your account.

| Concern | Starter behavior / production action |
|---|---|
| Recovery | Spark checkpoints and dlt load state are under `.cache/`. Preserve them; only one writer may use each pipeline/checkpoint. Use durable storage in deployment. |
| Duplicate delivery | Microbatch loading can replay. Merge keys handle repeated IDs; producer idempotence alone does not prevent duplicates across restarts. Spark uses descending Kafka offset for same-key duplicates within a batch. Keep keys on the same partition and partition count stable; define event-version handling for out-of-order business updates. |
| API completeness | Full configured polls; no automatic durable API cursor/CDC. Large sources need a provider-supported incremental cursor, overlap strategy and deletion handling. |
| Scale | The sink transfers one partition at a time through the Spark driver into dlt. Suitable for small rehearsals; a distributed Snowflake connector or durable object-store staging is needed for larger workloads. |
| Operations | Replace disposable Kafka/local Airflow with durable services, access control, monitoring, alerts and a controlled schema evolution/quarantine policy. Inspect source counts, Kafka lag, load failures and dbt tests. |
| Analytics / ML | Add actual dbt business rules and a separately trained model; connect Power BI to curated tables and configure its refresh mode. No prediction or dashboard is preselected. |

Library references: [Snowflake destination](https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake), [file readers](https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem), [merge semantics](https://dlthub.com/docs/general-usage/merge-loading). Local adapter checks: `python -m unittest discover -s Ingestion/tests -v`.
