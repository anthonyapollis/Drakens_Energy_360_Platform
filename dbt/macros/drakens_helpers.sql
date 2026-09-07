{#
    Cross-adapter helpers so the same models run on DuckDB (local/CI) and on
    Databricks (dev/test/prod) without branching inside every model.
#}

{% macro dbt_load_timestamp() %}
    {%- if target.type == 'duckdb' -%}
        current_timestamp
    {%- else -%}
        current_timestamp()
    {%- endif -%}
{% endmacro %}


{% macro date_key_from(ts_column) %}
    {#- Integer yyyymmdd key joining any timestamp to dim_date. -#}
    {%- if target.type == 'duckdb' -%}
        cast(strftime({{ ts_column }}, '%Y%m%d') as integer)
    {%- else -%}
        cast(date_format({{ ts_column }}, 'yyyyMMdd') as int)
    {%- endif -%}
{% endmacro %}


{% macro safe_divide(numerator, denominator, default=0) %}
    {#-
        Division that yields `default` rather than an error or infinity.

        Both arguments are parenthesised. Without this, a call such as
        safe_divide('a - b', 'c') expands to `a - b / c`, which SQL evaluates
        as `a - (b / c)` -- a silent, plausible-looking wrong answer rather
        than an error. The whole CASE is wrapped too, so a trailing `* 100`
        multiplies the result and not just the ELSE branch.
    -#}
    (case
        when ({{ denominator }}) is null or ({{ denominator }}) = 0 then ({{ default }})
        else ({{ numerator }}) / nullif(({{ denominator }}), 0)
    end)
{% endmacro %}


{% macro zar(amount) %}
    cast(round({{ amount }}, 2) as decimal(18, 2))
{% endmacro %}


{% macro incremental_window(ts_column) %}
    {#- Standard late-arriving-data window for every incremental fact model. -#}
    {% if is_incremental() %}
        where {{ ts_column }} >= (
            select coalesce(max({{ ts_column }}), cast('1900-01-01' as timestamp))
                   - interval '{{ var("incremental_lookback_days") }}' day
            from {{ this }}
        )
    {% endif %}
{% endmacro %}


{% macro cluster_or_partition(columns) %}
    {#-
        Databricks liquid clustering where available; DuckDB has no equivalent
        so the hint is simply omitted there.
    -#}
    {%- if target.type == 'databricks' -%}
        cluster_by = {{ columns }}
    {%- endif -%}
{% endmacro %}


{% macro log_run_results() %}
    {#- Emitted by on-run-end so pipeline duration lands in the run log. -#}
    {% if execute and results %}
        {% set failed = results | selectattr('status', 'in', ['error', 'fail']) | list %}
        {{ log("drakens360: " ~ results | length ~ " nodes, "
               ~ failed | length ~ " failed", info=true) }}
    {% endif %}
{% endmacro %}


{% test volume_within_tolerance(model, column_name, min_value, max_value) %}
    {#-
        A business-plausibility test rather than a null check: flags any row
        whose measure falls outside a physically sensible range. Catches unit
        errors (litres vs kilolitres) that `not_null` never would.
    -#}
    select *
    from {{ model }}
    where {{ column_name }} is not null
      and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}


{% test margin_is_reconcilable(model, revenue_column, cogs_column, margin_column, tolerance=0.02) %}
    {#- Gross margin must equal revenue minus cost, within rounding. -#}
    select *
    from {{ model }}
    where abs(coalesce({{ margin_column }}, 0)
              - (coalesce({{ revenue_column }}, 0) - coalesce({{ cogs_column }}, 0)))
          > {{ tolerance }}
{% endtest %}
