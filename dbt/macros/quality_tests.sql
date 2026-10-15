{% test not_blank(model, column_name) %}
select {{ column_name }} from {{ model }}
where {{ column_name }} is null or trim(to_varchar({{ column_name }})) = ''
{% endtest %}

{% test no_conflicting_versions(model, key_column, version_column, payload_columns) %}
select {{ key_column }}, {{ version_column }} from {{ model }}
group by {{ key_column }}, {{ version_column }}
having count(distinct {{ dbt_utils.generate_surrogate_key(payload_columns) }}) > 1
{% endtest %}
