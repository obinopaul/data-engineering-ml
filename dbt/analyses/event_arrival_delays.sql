{{ config(enabled=var('workload') in ['demo', 'events']) }}
-- Compile for investigation; dbt run does not materialize analyses.
select entity_id, event_type, count(*) as event_count,
    max(datediff('second', event_at, updated_at)) as maximum_update_delay_seconds
from {{ ref('fct_events') }}
where not is_deleted
group by entity_id, event_type
-- updated_at is source update time, not necessarily warehouse arrival time.
