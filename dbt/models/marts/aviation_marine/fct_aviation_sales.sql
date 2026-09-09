{{
    config(
        materialized='table',
        tags=['aviation', 'commercial', 'daily']
    )
}}

/*
    Grain: one row per aviation fuel uplift.

    Aviation does not resolve to a service station, and pretending otherwise
    would be the easy mistake here. An uplift happens at an airport, to an
    airline, often through an into-plane agent -- so the site key is
    deliberately absent rather than forced to the unknown member. A fact that
    has no site is different from a fact whose site could not be resolved, and
    collapsing the two would put every aviation litre into the same bucket the
    platform uses for referential drift.

    The customer dimension does apply: airlines are commercial customers, and
    the airline code resolves against the same conformed dimension the B2B
    orders use.
*/

with aviation as (

    select * from {{ ref('stg_fact_aviation_sales') }}

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
    f.aviation_sale_id,
    f.sale_ts,
    f.date_key,

    coalesce(p.product_key, -1) as product_key,
    coalesce(c.customer_key, -1) as customer_key,

    f.product_id,
    f.customer_id,
    f.airport_code,
    f.airline_code,
    coalesce(p.product_name, 'Unknown product') as product_name,
    coalesce(p.subcategory, 'Unknown') as fuel_grade,
    coalesce(p.reporting_line, 'Unknown') as reporting_line,
    coalesce(c.customer_name, 'Unknown customer') as customer_name,
    coalesce(c.sector, 'Unknown') as sector,
    coalesce(c.credit_band, 'Unknown') as credit_band,

    p.product_key is null as is_unmatched_product,
    c.customer_key is null as is_unmatched_customer,

    f.flight_type,
    f.is_into_plane,

    -- additive measures
    f.uplift_litres,
    {{ zar('f.unit_price_zar') }} as unit_price_zar,
    {{ zar('f.revenue_zar') }} as revenue_zar,
    {{ zar('f.cogs_zar') }} as cogs_zar,
    {{ zar('f.revenue_zar - f.cogs_zar') }} as gross_margin_zar,

    {{ safe_divide('f.revenue_zar - f.cogs_zar', 'f.revenue_zar') }}
        as line_margin_pct,

    f.source_system_code,
    f.ingested_at,
    f._cleansed_at

from aviation f
left join product p on f.product_id = p.product_id
left join customer c on f.customer_id = c.customer_id
