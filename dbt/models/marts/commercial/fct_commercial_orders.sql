{{
    config(
        materialized='incremental',
        unique_key='order_id',
        incremental_strategy='merge' if target.type == 'databricks' else 'delete+insert',
        tags=['commercial', 'daily']
    )
}}

/*
    Grain: one row per commercial (B2B) order header.
*/

with orders as (

    select * from {{ ref('stg_fact_commercial_orders') }}
    {{ incremental_window('order_ts') }}

),

customer as (
    select
        customer_key, customer_id, customer_name, sector, segment,
        country_code, credit_band, credit_risk_tier, service_model,
        is_industrial, revenue_index
    from {{ ref('dim_customer') }} where is_current
),

product as (
    select product_key, product_id, product_name, category, reporting_line
    from {{ ref('dim_product') }} where is_current
)

select
    o.order_id,
    o.order_ts,
    o.date_key,

    c.customer_key,
    p.product_key,

    o.customer_id,
    o.contract_id,
    o.product_id,
    c.customer_name,
    c.sector,
    c.segment,
    c.credit_band,
    c.credit_risk_tier,
    c.service_model,
    c.is_industrial,
    p.product_name,
    p.reporting_line,
    o.channel,
    o.order_status,
    o.requested_delivery_date,
    o.payment_terms_days,

    o.volume_litres,
    o.list_price_zar,
    o.discount_cents_per_litre,
    o.net_price_zar,
    {{ zar('o.revenue_zar') }} as revenue_zar,
    {{ zar('o.cogs_zar') }} as cogs_zar,
    {{ zar('o.gross_margin_zar') }} as gross_margin_zar,

    -- Discount leakage: what the discount actually cost in rand terms. This is
    -- the number commercial review meetings are actually about.
    {{ zar('o.volume_litres * o.discount_cents_per_litre / 100.0') }}
        as discount_value_zar,

    {{ safe_divide('o.gross_margin_zar', 'o.revenue_zar') }} * 100 as margin_pct,
    {{ safe_divide('o.gross_margin_zar', 'o.volume_litres') }} * 100
        as margin_cents_per_litre,

    o.order_status in ('Draft', 'Confirmed', 'Allocated') as is_open_order,
    o.order_status = 'Cancelled' as is_cancelled,

    case
        when o.volume_litres >= 500000 then 'Very Large'
        when o.volume_litres >= 100000 then 'Large'
        when o.volume_litres >= 20000 then 'Medium'
        else 'Small'
    end as order_size_band,

    o.source_system_code,
    o.ingested_at,
    o._dbt_loaded_at

from orders o
left join customer c on o.customer_id = c.customer_id
left join product p on o.product_id = p.product_id
