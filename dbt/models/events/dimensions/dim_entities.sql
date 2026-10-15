with latest as (
    {{ dbt_utils.deduplicate(
        relation=ref('stg_entities'), partition_by='entity_id', order_by='updated_at desc'
    ) }}
)
select
    {{ dbt_utils.generate_surrogate_key(['entity_id']) }} as entity_key,
    entity_id, entity_name, entity_type, status, updated_at
from latest
