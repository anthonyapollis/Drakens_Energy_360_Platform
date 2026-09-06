{{
    config(
        materialized='table',
        tags=['observability', 'data_quality', 'cleansing']
    )
}}

/*
    Grain: one row per table per failed rule.

    `obs_cleansing_summary` says how much was rejected; this says why. The
    distinction matters operationally: 2,000 rows rejected for a missing
    site_id is a broken upstream join and someone must fix the source, whereas
    2,000 rows rejected for a negative amount is usually a legitimate credit
    note arriving on the wrong feed. The same headline number, two entirely
    different responses.

    Rules are stored as a comma-separated list on the quarantined row, so a
    row failing three rules is counted once against each of them. Counts here
    will therefore exceed the row count in the summary model, which is
    intended -- this measures rule failures, not rows.
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

with all_quarantined as (

{% for table in monitored %}
    select
        '{{ table }}' as table_name,
        _dq_failed_rules
    from {{ ref('qtn_' ~ table) }}
    {% if not loop.last %}union all{% endif %}
{% endfor %}

),

exploded as (

    -- One row per (table, failed rule).
    select
        table_name,
        trim(rule_name) as failed_rule
    from all_quarantined,
        {% if target.type == 'duckdb' %}
        unnest(string_split(_dq_failed_rules, ',')) as t(rule_name)
        {% else %}
        lateral view explode(split(_dq_failed_rules, ',')) t as rule_name
        {% endif %}
    where _dq_failed_rules is not null
      and trim(coalesce(_dq_failed_rules, '')) <> ''

),

counted as (

    select
        table_name,
        failed_rule,
        count(*) as failure_count
    from exploded
    where failed_rule <> ''
    group by 1, 2

)

select
    table_name,
    failed_rule,
    failure_count,
    -- Classifying the rule tells the reader which team owns the fix.
    case
        when failed_rule like '%_present' then 'Missing Required Field'
        when failed_rule like '%_non_negative' then 'Invalid Sign'
        when failed_rule like '%_within_range' then 'Out of Range'
        when failed_rule like 'event_timestamp%' then 'Invalid Timestamp'
        else 'Other'
    end as failure_category,
    case
        when failed_rule like '%_present' then 'Source System'
        when failed_rule like 'event_timestamp%' then 'Source System'
        when failed_rule like '%_non_negative' then 'Business Process'
        when failed_rule like '%_within_range' then 'Data Entry'
        else 'Data Platform'
    end as likely_owner,
    {{ dbt_load_timestamp() }} as evaluated_at
from counted
order by failure_count desc
