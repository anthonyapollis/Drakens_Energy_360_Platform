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

{% set monitored = [
    'fact_retail_fuel_sales',
    'fact_shop_sales',
    'fact_commercial_orders',
    'fact_deliveries',
    'fact_inventory_snapshot',
    'fact_tank_dips',
    'fact_pump_meter_readings',
    'fact_ev_charging_sessions',
    'fact_solar_generation',
    'fact_general_ledger',
    'fact_maintenance_work_orders',
    'fact_hsseq_incidents',
    'fact_loyalty_transactions',
    'fact_digital_events'
] %}

with counted as (

{% for table in monitored %}
    select
        '{{ table }}' as table_name,
        (select count(*) from {{ source('lake_facts', table) }}) as raw_rows,
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
