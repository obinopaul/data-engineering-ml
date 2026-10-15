# dbt interview workspace

Use `main/.venv` and run commands from **`main/`**. `Snowflake/connection.py --dbt ...` loads your existing `.env` and selects this project/profile. Keep the current credentials; no new account or environment is needed.

## Start with the working demo

After [Snowflake setup](../Snowflake/README.md) and a successful connection check:

```bash
source .venv/bin/activate
python Snowflake/connection.py --dbt deps
python Snowflake/connection.py --dbt parse --vars '{workload: demo}'
# First build creates relations needed by warehouse-backed unit tests:
python Snowflake/connection.py --dbt build --vars '{workload: demo}' --exclude test_type:unit
python Snowflake/connection.py --dbt test --vars '{workload: demo}' --select test_type:unit
# Subsequent builds run the complete graph and its tests:
python Snowflake/connection.py --dbt build --vars '{workload: demo}'
```

`deps` installs the pinned **dbt_utils 1.4.1** SQL macro package into `dbt_packages/`; pip installs the dbt executable. They are different dependency types. This workspace already has the macro package downloaded and checksum-verified; normal `dbt deps` should be used on a network-enabled machine when restoring it.

The demo uses tiny **synthetic seeds**, not the real oilfield datasets. It needs Snowflake to execute SQL, but no API account or file ingestion. Expected results: **2 entities, 5 latest events (one deleted), 4 active events and 3 daily reporting rows**. Asset A pressure averages **100 kPa** from values 110 and 90. The deletion marker removes event e4 from reporting without deleting its fact history record.

## Choose a workload

| Variable | Inputs | Outputs with the current profile |
|---|---|---|
| `workload: starter` (default) | Existing configurable `SAMPLE_TABLE` source | Original models in `ANALYTICS` |
| `workload: demo` | `seeds/demo/` | New pipeline in `ANALYTICS_DEMO` |
| `workload: events` | Your `RAW.EVENTS` and `RAW.ENTITIES` | New pipeline in `ANALYTICS_EVENTS` |

The existing ingestion/Airflow commands remain on the starter workload. A different profile schema prefixes the demo/events schemas. Your role needs permission to create these schemas; the existing bootstrap grants it. Do not run concurrent builds against the same workload/schema.

For real data, first follow [INPUT_CONTRACT.md](INPUT_CONTRACT.md), then:

```bash
python Snowflake/connection.py --dbt build --vars '{workload: events, events_table: EVENTS, entities_table: ENTITIES}'
```

Also set `source_database` / `source_schema` when needed. On a first deployment, use the same build-without-unit-tests then unit-test sequence shown above. These models cannot infer arbitrary vendor/file columns. Adapt the two staging SQL files and lookup seed to the assessment's grain and meanings.

## Read the project in this order

```text
seeds (demo) or RAW sources
  -> stg_events -> int_latest_events -> fct_events -> mart_entity_daily
  -> stg_entities -> dim_entities ------------------^
                         -> snap_entities (SCD2 history)
event_type_lookup --------------------------------^
```

| Folder/file | What you learn or edit |
|---|---|
| `models/events/staging/` | Explicit fields, type conversion and input validation |
| `models/events/intermediate/` | Latest-record deduplication as an ephemeral CTE |
| `models/events/dimensions/` | Current entity attributes and stable surrogate keys |
| `models/events/facts/` | Incremental MERGE with a unique key and update lookback |
| `models/events/marts/` | Reporting aggregates, joins and consistent measurement units |
| `models/events/schema.yml` | Keys, relationships, required values and conflicting-version tests |
| `models/events/unit_tests.yml` | Fixtures for latest versions, late updates, initial loads and deletions |
| `seeds/` | Tiny demo inputs and editable event-type/unit reference data |
| `snapshots/snap_entities.yml` | Attribute history using the check strategy; no arbitrary row limit |
| `macros/` | Input switching, validated lookback, required-field and conflict tests |
| `tests/events/` | Cross-model reconciliation and snapshot-current-row checks |
| `analyses/` | Investigative SQL; compiled but not materialized by normal runs |
| `packages.yml`, `package-lock.yml` | Pinned reusable dbt utilities |
| `selectors.yml` | Named starter/events selections; these do not enable workloads |

## Incremental updates and history

Facts merge by `event_id`. The default three-day lookback uses **source `updated_at`**, not event time, and includes the boundary. Re-reading a record updates it rather than blindly appending it. Equal-key/equal-version conflicting payloads fail staging tests. Source tombstones remain in the fact; active marts exclude them. This still scans staging for latest versions; it is not source-side CDC or a large-scale ingestion optimization.

Older corrections need a wider window or an intentional `--full-refresh` of the fact and downstream models. The source must retain history if a rebuild is expected to reproduce it. Physical deletions are not inferred. Read the input contract before changing this behavior.

Snapshots track entity attribute changes observed when the job runs. They cannot reconstruct changes between runs. Missing entities are not automatically treated as deletions; this avoids interpreting an incomplete extract as a deletion. The reporting mart joins **current** entity attributes; it is not a historical as-of join to the snapshot.

## Useful commands

```bash
python Snowflake/connection.py --dbt ls --vars '{workload: demo}' --selector events
python Snowflake/connection.py --dbt docs generate --vars '{workload: demo}'
python Snowflake/connection.py --dbt docs serve
python Snowflake/connection.py --dbt compile --vars '{workload: demo}' --select event_arrival_delays
```

`parse` validates the project without a warehouse query. `compile`, unit tests, `build` and catalog generation may require Snowflake access. `logs/`, `target/` and `dbt_packages/` are generated/ignored directories; do not copy someone else's runtime outputs. The original Netflix tutorial remains untouched as a reference.

## Reference and validation

The local `../dbt-databuildtool--masterclass-netflix-project-main/netflix/` tutorial informed the staging/dimension/fact/seed/snapshot layout. Its actual domain is MovieLens ratings despite the Netflix folder name. This adaptation removes hardcoded MOVIELENS references, adds merge keys and lookback handling, and replaces the limited snapshot and blanket all-column null check. Reusable deduplication, key generation and generic tests come from [dbt_utils](https://hub.getdbt.com/dbt-labs/dbt_utils/1.4.1/).

All three workloads parse with installed dbt Core 1.12.6 and Snowflake adapter 1.12.3. SQL execution, MERGE behavior and warehouse-backed unit tests still require a live Snowflake run. The offline compilation attempt reached the incremental model's relation-metadata requirement; a full successful compile is not claimed.
