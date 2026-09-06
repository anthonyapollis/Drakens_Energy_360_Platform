{{
    config(
        materialized='table',
        tags=['observability', 'controls', 'finance']
    )
}}

/*
    Grain: one row per control check.

    Financial and volumetric reconciliation controls. These are the checks a
    finance function signs off on, and they are deliberately expressed as data
    rather than as dbt tests: a failing control needs to be *visible and
    trended* on a dashboard, not just fail a pipeline run.

    Each control states its own tolerance, so tightening a threshold is a
    reviewable change with a reason attached.
*/

with retail_margin as (

    select
        'RETAIL_MARGIN_RECONCILES' as control_code,
        'Retail fuel gross margin equals revenue less cost of sales'
            as control_description,
        'Finance' as control_owner,
        cast(sum(gross_sales_zar) - sum(cogs_zar) as double) as expected_value,
        cast(sum(gross_margin_zar) as double) as actual_value,
        0.01 as tolerance_pct
    from {{ ref('fct_retail_fuel_sales') }}

),

gl_balanced as (

    select
        'GL_DEBITS_EQUAL_CREDITS' as control_code,
        'Posted journal debits equal credits across the ledger' as control_description,
        'Finance' as control_owner,
        cast(sum(debit_amount_zar) as double) as expected_value,
        cast(sum(credit_amount_zar) as double) as actual_value,
        0.01 as tolerance_pct
    from {{ ref('fct_general_ledger') }}

),

volume_tieout as (

    select
        'RETAIL_VOLUME_TIES_TO_DAILY_AGG' as control_code,
        'Transaction-level litres tie to the site-day aggregate'
            as control_description,
        'Supply' as control_owner,
        cast((select sum(litres) from {{ ref('fct_retail_fuel_sales') }}) as double)
            as expected_value,
        cast((select sum(litres) from {{ ref('agg_site_daily_fuel') }}) as double)
            as actual_value,
        0.001 as tolerance_pct

),

delivery_completeness as (

    select
        'DELIVERIES_HAVE_KNOWN_DESTINATION' as control_code,
        'Every delivery resolves to a site in the conformed dimension'
            as control_description,
        'Supply' as control_owner,
        cast(count(*) as double) as expected_value,
        cast(sum(case when destination_site_key is not null then 1 else 0 end) as double)
            as actual_value,
        0.0 as tolerance_pct
    from {{ ref('fct_deliveries') }}

),

orders_have_customer as (

    select
        'ORDERS_HAVE_KNOWN_CUSTOMER' as control_code,
        'Every commercial order resolves to a customer in the dimension'
            as control_description,
        'Commercial' as control_owner,
        cast(count(*) as double) as expected_value,
        cast(sum(case when customer_key is not null then 1 else 0 end) as double)
            as actual_value,
        0.0 as tolerance_pct
    from {{ ref('fct_commercial_orders') }}

),

all_controls as (
    select * from retail_margin
    union all select * from gl_balanced
    union all select * from volume_tieout
    union all select * from delivery_completeness
    union all select * from orders_have_customer
)

select
    control_code,
    control_description,
    control_owner,
    expected_value,
    actual_value,
    actual_value - expected_value as variance_absolute,
    {{ safe_divide('abs(actual_value - expected_value)', 'nullif(abs(expected_value), 0)') }} * 100
        as variance_pct,
    tolerance_pct,
    case
        when expected_value = 0 and actual_value = 0 then true
        else {{ safe_divide('abs(actual_value - expected_value)',
                            'nullif(abs(expected_value), 0)') }} * 100 <= tolerance_pct
    end as is_passing,
    {{ dbt_load_timestamp() }} as evaluated_at
from all_controls
