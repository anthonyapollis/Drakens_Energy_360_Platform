{{
    config(
        materialized='table',
        tags=['lpg', 'new_energy', 'daily']
    )
}}

/*
    Grain: one row per LPG sales line.

    LPG is sold by mass, not volume. The measure is kilograms and it is never
    added to the litres in the fuel facts or the kilowatt-hours in the EV
    fact: a "total volume" spanning kilograms, litres and kWh is a number
    without a unit, and the semantic model keeps them in separate measures for
    that reason.

    The line held four products and reported zero on every product chart,
    because this model did not exist. 16,000 rows were sitting in the cleansed
    layer with nothing downstream asking for them.
*/

with lpg_sales as (

    select * from {{ ref('stg_fact_lpg_sales') }}

),

site as (

    select
        site_key, site_id, province, city, country_code,
        urban_class, site_type
    from {{ ref('dim_site') }}
    where is_current

),

product as (

    select
        product_key, product_id, product_name,
        category, subcategory, reporting_line
    from {{ ref('dim_product') }}
    where is_current

)

select
    f.lpg_sale_id,
    f.sale_ts,
    f.date_key,

    coalesce(s.site_key, -1) as site_key,
    coalesce(p.product_key, -1) as product_key,

    f.site_id,
    f.product_id,
    f.customer_id,
    f.cylinder_type_code,
    coalesce(s.province, 'Unknown') as province,
    coalesce(s.city, 'Unknown') as city,
    coalesce(s.country_code, 'ZZ') as country_code,
    coalesce(s.urban_class, 'Unknown') as urban_class,
    coalesce(p.product_name, 'Unknown product') as product_name,
    coalesce(p.subcategory, 'Unknown') as cylinder_size,
    coalesce(p.reporting_line, 'Unknown') as reporting_line,

    s.site_key is null as is_unmatched_site,
    p.product_key is null as is_unmatched_product,

    f.channel,
    f.is_winter_peak,

    -- additive measures. Kilograms, deliberately named so nobody sums them
    -- into a litres column by accident.
    f.quantity_kg,
    {{ zar('f.unit_price_zar') }} as unit_price_zar,
    {{ zar('f.revenue_zar') }} as revenue_zar,
    {{ zar('f.cogs_zar') }} as cogs_zar,
    {{ zar('f.gross_margin_zar') }} as gross_margin_zar,

    {{ safe_divide('f.gross_margin_zar', 'f.revenue_zar') }}
        as line_margin_pct,
    {{ safe_divide('f.gross_margin_zar', 'f.quantity_kg') }}
        as margin_zar_per_kg,

    f.source_system_code,
    f.ingested_at,
    f._cleansed_at

from lpg_sales f
left join site s on f.site_id = s.site_id
left join product p on f.product_id = p.product_id
