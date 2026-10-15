select 'active event count does not reconcile' as failure
where (select count(*) from {{ ref('fct_events') }} where not is_deleted)
    <> (select coalesce(sum(event_count), 0) from {{ ref('mart_entity_daily') }})
