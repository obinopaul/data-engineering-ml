{{ config(
    materialized='incremental', incremental_strategy='merge',
    unique_key='event_id', on_schema_change='fail'
) }}
select
    event_id,
    {{ dbt_utils.generate_surrogate_key(['entity_id']) }} as entity_key,
    entity_id, event_type, event_at, updated_at, metric_value, is_deleted
from {{ ref('int_latest_events') }}
{% if is_incremental() %}
where updated_at >= dateadd(
    day, -{{ event_lookback_days() }},
    (select coalesce(max(updated_at), '1900-01-01'::timestamp_ntz) from {{ this }})
)
{% endif %}
-- Retain tombstones; downstream active marts exclude them.
-- Physical deletions and corrections older than the lookback need reconciliation.
