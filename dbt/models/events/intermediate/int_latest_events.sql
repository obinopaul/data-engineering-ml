-- Conflicting equal-version records fail staging tests; identical copies collapse.
{{ dbt_utils.deduplicate(
    relation=ref('stg_events'), partition_by='event_id',
    order_by='updated_at desc, event_at desc'
) }}
