-- Failed casts remain visible to data tests; upstream timestamps must share UTC convention.
select
    nullif(trim(to_varchar(event_id)), '') as event_id,
    nullif(trim(to_varchar(entity_id)), '') as entity_id,
    lower(nullif(trim(to_varchar(event_type)), '')) as event_type,
    try_to_timestamp_ntz(to_varchar(event_at)) as event_at,
    try_to_timestamp_ntz(to_varchar(updated_at)) as updated_at,
    try_to_double(to_varchar(metric_value)) as metric_value,
    try_to_boolean(to_varchar(is_deleted)) as is_deleted
from {{ event_input('events') }}
