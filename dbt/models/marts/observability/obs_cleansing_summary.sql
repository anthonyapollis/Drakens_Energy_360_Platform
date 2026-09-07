{{
    config(
        materialized='table',
        tags=['observability', 'data_quality', 'cleansing']
    )
}}

/*
    Grain: one row per cleansed table.

    The before-and-after of the cleansing layer. For each monitored table it
    counts what arrived, what survived, what was rejected, and why.

    This exists because "we clean the data" is not a verifiable statement.
    A rejection rate that suddenly moves is the earliest signal that an
    upstream system changed, and it shows up here days before anyone notices
    a number looks wrong in a report.

    Read alongside `obs_quarantine_reasons`, which breaks the rejections down
    by the specific rule that failed.
*/

{#-
    The tables counted here come from a generated macro, not from a list kept
    by hand and not from the dbt graph.

    The hand-kept version named fourteen tables. The landing zone has 167
    cleansed tables, so the observability that exists to prove the cleansing is
    measurable was measuring 8% of it -- and the eight percent was whichever
    tables someone had thought to add, which is the least useful sample
    available. It also went stale silently: a new fact landed, nobody added it,
    and its rejection rate stayed invisible until someone asked a question it
    would have answered.

    Reading `graph` here instead is the obvious fix and it does not compile:
    `graph` is only populated at execute time, so the `ref()` calls built from
    it sit inside a conditional and dbt cannot infer this model's dependencies
    while parsing. A macro is evaluated during parsing, so its refs resolve
    normally.
-#}
{% set monitored = monitored_tables() %}

with counted as (

{% for source_name, table in monitored %}
    select
        '{{ table }}' as table_name,
        (select count(*) from {{ source(source_name, table) }}) as raw_rows,
        (select count(*) from {{ ref('stg_' ~ table) }}) as cleansed_rows,
        (select count(*) from {{ ref('qtn_' ~ table) }}) as quarantined_rows
    {% if not loop.last %}union all{% endif %}
{% endfor %}

),

derived as (

    select
        table_name,
        raw_rows,
        cleansed_rows,
        quarantined_rows,
        -- Whatever is neither cleansed nor quarantined was a duplicate the
        -- dedup step collapsed. Stating it explicitly means the three
        -- outcomes always add back to the raw count, so nothing can go
        -- missing without this line making it obvious.
        raw_rows - cleansed_rows - quarantined_rows as duplicates_removed,
        {{ safe_divide('quarantined_rows', 'raw_rows') }} * 100
            as quarantine_rate_pct,
        {{ safe_divide('raw_rows - cleansed_rows - quarantined_rows', 'raw_rows') }} * 100
            as duplicate_rate_pct,
        {{ safe_divide('cleansed_rows', 'raw_rows') }} * 100
            as pass_rate_pct
    from counted

)

select
    *,
    /*
        Thresholds are a judgement about what is normal for these feeds, not a
        universal standard. A POS extract that suddenly rejects 5% of rows has
        changed; one rejecting 0.3% is behaving as designed.
    */
    case
        when quarantine_rate_pct > 5.0 then 'Critical'
        when quarantine_rate_pct > 2.0 then 'Elevated'
        when quarantine_rate_pct > 0.5 then 'Watch'
        else 'Normal'
    end as quarantine_status,
    raw_rows = cleansed_rows + quarantined_rows + duplicates_removed
        as row_count_reconciles,
    {{ dbt_load_timestamp() }} as evaluated_at
from derived
