select entity_id from {{ ref('snap_entities') }}
where dbt_valid_to is null
group by entity_id having count(*) > 1
