select
    f.entity_key, f.entity_id, d.entity_name, d.entity_type,
    cast(f.event_at as date) as event_date,
    f.event_type, t.metric_unit,
    count(*) as event_count,
    count(f.metric_value) as measured_count,
    avg(f.metric_value) as average_value,
    min(f.metric_value) as minimum_value,
    max(f.metric_value) as maximum_value
from {{ ref('fct_events') }} f
left join {{ ref('dim_entities') }} d on f.entity_key = d.entity_key
left join {{ ref('event_type_lookup') }} t on f.event_type = t.event_type
where not f.is_deleted
group by 1, 2, 3, 4, 5, 6, 7
