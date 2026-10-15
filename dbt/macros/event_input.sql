{% macro event_input(name) %}
  {% if var('workload') == 'demo' %}
    {{ return(ref('demo_' ~ name)) }}
  {% elif var('workload') == 'events' %}
    {{ return(source('event_raw', name)) }}
  {% elif var('workload') == 'starter' and not execute %}
    {# dbt parses disabled models too; do not require their input relations. #}
    {{ return('__disabled_event_input') }}
  {% else %}
    {{ exceptions.raise_compiler_error('Event models require workload: demo or events') }}
  {% endif %}
{% endmacro %}

{% macro event_lookback_days() %}
  {% set days = var('event_lookback_days', 3) %}
  {% if days is not integer or days < 0 or days > 365 %}
    {{ exceptions.raise_compiler_error('event_lookback_days must be an integer from 0 to 365') }}
  {% endif %}
  {{ return(days) }}
{% endmacro %}
