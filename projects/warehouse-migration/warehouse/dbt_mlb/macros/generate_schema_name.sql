{# Build into exactly the schema named in profiles.yml (ANALYTICS),
   instead of dbt's default of prefixing custom schema names. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name or target.schema }}
{%- endmacro %}
