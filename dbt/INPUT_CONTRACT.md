# Adapt this pipeline to the interview data

Choose the row grain and business keys before changing SQL. The event pipeline is a reusable example, not an automatic schema detector. Ingestion loads RAW tables; dbt reads those tables and transforms them.

## Events input

`workload: events` reads `source_database.source_schema.events_table` (defaults: profile database, `RAW`, `EVENTS`). Required column names:

| Field | Meaning and requirement |
|---|---|
| `event_id` | Stable, nonblank event key; updates keep the same key |
| `entity_id` | Stable key matching an entity master row |
| `event_type` | Key in `event_type_lookup`; demo types are pressure and temperature |
| `event_at` | When the event happened; consistently normalized UTC timestamp text/native timestamp |
| `updated_at` | Source version time, advanced on every correction or deletion |
| `metric_value` | Numeric value in the unit declared for its event type; required for non-deleted events |
| `is_deleted` | Explicit boolean; use false for a confirmed insert/update-only source |

The staging model uses `TIMESTAMP_NTZ`. Normalize offsets/timezones upstream; do not silently strip a local timezone or mix epoch integers with formatted timestamps. Failed conversions become null and fail tests. A new ID sequence alone cannot detect updates to older records.

RAW may contain multiple retained versions per event, or a current-state row per event. Exact duplicate versions can collapse. Conflicting payloads at the same `event_id` + `updated_at` fail. For a delta-only landing table, retain prior data elsewhere before using full refresh or rebuilding dimensions.

## Entities input

The configurable `entities_table` defaults to `ENTITIES`. Columns: `entity_id`, `entity_name`, `entity_type`, `status`, `updated_at`. IDs and strings must be nonblank; dates must parse. `dim_entities` selects the latest version per key; all event entity keys must resolve to it. Keep inactive/deleted entities with an explicit status when facts still reference them.

The snapshot compares name, type and status. It records observation-time SCD2 history and ignores missing rows. To enable hard-delete invalidation, first guarantee that the input represents a complete authoritative entity population on every run. Source delta pages are not such a population.

## Map the supplied oilfield datasets

- **3W:** entity = well; an event = one selected sensor at a timestamp. Unpivot sensor columns and form an ID from source file, timestamp and sensor. Convert pressure from Pa to kPa if using the demo lookup. `class`, `state` and `instance_type` are labels/context, not pressure values. The historical files have no reliable change timestamp: choose an explicit replay/ingestion timestamp for the exercise and label it as such. Do not invent source update times.
- **Volve:** the wireline samples are depth-indexed. Build a separate depth-grain model keyed by run/frame/depth (or supplied stable sample ID). The header `log_date` is not an event timestamp for every sample. Keep the two frames separate or define an explicit resampling rule. Do not force these records into a daily telemetry fact simply to match the example.
- **FORCE:** log samples belong in a well/depth fact and casing records in a separate geometry/reference table. Define intervals before joining; a well-only join multiplies rows. The existing starter workload can load/explore these raw tables while you adapt the event layout to a depth-based layout.
- **ERP/HRIS:** choose transaction/worker keys and the vendor's actual change field; retain fields relevant to that problem. A customer or worker snapshot is not automatically a measurement event.

## Freshness and recovery

Only enable freshness if your ingestion writes a real load timestamp. Example (replace `INGESTED_AT` with an existing timestamp column):

```bash
python Snowflake/connection.py --dbt source freshness --select source:event_raw.events \
  --vars '{workload: events, events_loaded_at_field: INGESTED_AT, events_freshness: {warn_after: {count: 30, period: minute}, error_after: {count: 60, period: minute}}}'
```

Historical `event_at` values are not ingestion freshness. Thresholds must match the source delivery contract. Freshness runs separately from `dbt build`.

The fact's lookback is configurable with `event_lookback_days` (integer 0–365). A future-dated `updated_at` can move its watermark forward, so validate source clocks and monitor freshness/reconciliation in your real deployment. Corrections outside the window and physical deletions require a planned recovery strategy. `on_schema_change: fail` makes structural drift visible instead of silently accepting it.

After a successful manual rehearsal, an Airflow task can invoke the same launcher with `--vars '{workload: events}'` after ingestion. Use unattended Snowflake authentication, one writer per destination and a separate schedule for source freshness. No new schedule is enabled by this project.
