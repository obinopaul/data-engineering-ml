select
    nullif(trim(to_varchar(entity_id)), '') as entity_id,
    nullif(trim(to_varchar(entity_name)), '') as entity_name,
    lower(nullif(trim(to_varchar(entity_type)), '')) as entity_type,
    lower(nullif(trim(to_varchar(status)), '')) as status,
    try_to_timestamp_ntz(to_varchar(updated_at)) as updated_at
from {{ event_input('entities') }}
