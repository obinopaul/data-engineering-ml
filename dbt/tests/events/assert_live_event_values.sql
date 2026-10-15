select event_id from {{ ref('stg_events') }}
where not is_deleted and metric_value is null
