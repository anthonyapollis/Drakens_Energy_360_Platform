{{
    config(
        materialized='table',
        tags=['marine', 'commercial', 'daily']
    )
}}

/*
    Grain: one row per marine bunker sale.

    Like aviation, a bunker sale has no service station: it happens at a port,
    to a vessel. The site key is absent rather than unknown, for the same
    reason -- "this fact has no site" and "this fact's site did not resolve"
    are different statements and the platform counts the second one.

    sulphur_pct is carried because it is the regulatory attribute of the
    product: IMO 2020 caps sulphur at 0.50% outside emission control areas,
    and a bunker book that cannot report on it cannot answer the only
    compliance question anyone asks of it.
*/

with marine as (

    select * from {{ ref('stg_fact_marine_sales') }}

),

product as (

    select product_key, product_id, product_name, subcategory, reporting_line
    from {{ ref('dim_product') }}
    where is_current

),

customer as (

    select customer_key, customer_id, customer_name, sector, credit_band
    from {{ ref('dim_customer') }}
    where is_current

)

select
    f.marine_sale_id,
    f.sale_ts,
    f.date_key,

    coalesce(p.product_key, -1) as product_key,
    coalesce(c.customer_key, -1) as customer_key,

    f.product_id,
    f.customer_id,
    f.port_code,
    f.vessel_imo,
    f.vessel_class,
    coalesce(p.product_name, 'Unknown product') as product_name,
    coalesce(p.subcategory, 'Unknown') as fuel_grade,
    coalesce(p.reporting_line, 'Unknown') as reporting_line,
    coalesce(c.customer_name, 'Unknown customer') as customer_name,
    coalesce(c.sector, 'Unknown') as sector,
    coalesce(c.credit_band, 'Unknown') as credit_band,

    p.product_key is null as is_unmatched_product,
    c.customer_key is null as is_unmatched_customer,

    f.sulphur_pct,
    f.sulphur_pct <= 0.50 as is_imo2020_compliant,

    -- additive measures
    f.bunker_litres,
    {{ zar('f.unit_price_zar') }} as unit_price_zar,
    {{ zar('f.revenue_zar') }} as revenue_zar,
    {{ zar('f.cogs_zar') }} as cogs_zar,
    {{ zar('f.revenue_zar - f.cogs_zar') }} as gross_margin_zar,

    {{ safe_divide('f.revenue_zar - f.cogs_zar', 'f.revenue_zar') }}
        as line_margin_pct,

    f.source_system_code,
    f.ingested_at,
    f._cleansed_at

from marine f
left join product p on f.product_id = p.product_id
left join customer c on f.customer_id = c.customer_id
