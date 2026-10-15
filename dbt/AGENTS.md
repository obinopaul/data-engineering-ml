# dbt contributor guide

## Scope and entry point

Use `main/.venv` and `python Snowflake/connection.py --dbt ...` from `main/`. Preserve local `profiles.yml`, `.env`, profile name `dbt_project` and the existing starter workload. Read [README.md](README.md) and [INPUT_CONTRACT.md](INPUT_CONTRACT.md) before changing SQL.

## Workloads

`workload: starter` enables the original two models. `demo` enables synthetic seeds and the event pipeline; `events` uses configured RAW sources. Demo and real models use separate schemas derived from `target.schema`. Preserve these boundaries and do not start warehouse writes or schedules merely to validate a code change.

## Model conventions

Use `source()` for RAW inputs and `ref()` for dependencies. Staging normalizes types and field names; intermediate models deduplicate; dimensions define entity grain; facts merge by stable event ID; marts aggregate by entity/day/type. Every model should declare grain and test its keys. Keep real wireline depth frames distinct from timestamped telemetry.

Use pinned `dbt_utils` for deduplication and surrogate keys. Never silently resolve conflicting equal-version records, discard deletion tombstones, or mix measurement units. Facts use `updated_at` lookback with an inclusive boundary, not event-time filtering. `on_schema_change: fail` is deliberate. Wider-window replay/full refresh and physical deletions need explicit handling.

Snapshots track entity attributes at observation time. Do not add sampling limits or assume a delta source is a complete population. Keep optional freshness tied to genuine load timestamps.

## Validation

Run `dbt parse` for starter, demo and events after edits; switching workloads changes dependencies. Data tests and four unit fixtures cover keys, conflicts, latest versions, incremental boundaries, tombstones and reporting. They require Snowflake execution to prove behavior. Never describe parsing as a successful warehouse build. Initial unit-test execution may need the demo relations built first, as documented.

Keep `target/`, `logs/`, downloaded packages and credentials ignored. Update the README and input contract when changing variables, grain or commands. Preserve package attribution and the original tutorial reference; do not copy its generated artifacts.
