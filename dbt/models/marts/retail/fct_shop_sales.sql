{{
    config(
        materialized='table',
        tags=['retail', 'convenience', 'hourly']
    )
}}

/*
    Grain: one row per convenience shop sales line.

    This model did not exist, and its absence was invisible in the obvious
    way: the Convenience reporting line held eight products, every product
    chart showed it at zero, and a reader would reasonably conclude the
    business does not sell convenience. It sells 120,000 lines of it. The data
    reached the cleansed layer and stopped there, because nothing downstream
    ever asked for it.

    That is the failure mode a coverage matrix exists to catch: a gap between
    what the warehouse holds and what the model exposes looks exactly like an
    absence of data, and only one of those is worth fixing by generating more.

    Non-fuel margin is the point of this table. Forecourt fuel is a
    price-regulated, thin-margin business -- 8.9% in this network -- and the
    shop is where the rate is. Reporting them separately is what makes the mix
    argument checkable rather than asserted.
*/

with shop_sales as (

    select * from {{ ref('stg_fact_shop_sales') }}

),

site as (

    select
        site_key, site_id, province, city, country_code,
        urban_class, site_type, ownership_model, demand_band
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
    f.shop_line_id,
    f.basket_id,
    f.transaction_ts,
    f.date_key,
    f.time_key,

    -- Resolved to the unknown member, never nulled. A line carrying a site
    -- code the dimension never received is still a real sale with real
    -- margin; a null key drops it from every inner join and from any total
    -- grouped by province.
    coalesce(s.site_key, -1) as site_key,
    coalesce(p.product_key, -1) as product_key,

    f.site_id,
    f.product_id,
    coalesce(s.province, 'Unknown') as province,
    coalesce(s.city, 'Unknown') as city,
    coalesce(s.country_code, 'ZZ') as country_code,
    coalesce(s.urban_class, 'Unknown') as urban_class,
    coalesce(s.site_type, 'Unknown') as site_type,
    coalesce(p.product_name, 'Unknown product') as product_name,
    coalesce(p.category, 'Unknown') as category,
    coalesce(p.subcategory, 'Unknown') as subcategory,
    coalesce(p.reporting_line, 'Unknown') as reporting_line,

    s.site_key is null as is_unmatched_site,
    p.product_key is null as is_unmatched_product,

    f.promotion_applied,
    f.payment_method,

    -- additive measures
    f.quantity,
    {{ zar('f.unit_price_zar') }} as unit_price_zar,
    {{ zar('f.gross_sales_zar') }} as gross_sales_zar,
    {{ zar('f.cogs_zar') }} as cogs_zar,
    {{ zar('f.gross_margin_zar') }} as gross_margin_zar,

    -- Non-additive, kept for row inspection only. The semantic model
    -- recomputes the rate as SUM(margin)/SUM(revenue) so that filtering a
    -- subset cannot average an average.
    {{ safe_divide('f.gross_margin_zar', 'f.gross_sales_zar') }}
        as line_margin_pct,

    f.source_system_code,
    f.ingested_at,
    f._cleansed_at

from shop_sales f
left join site s on f.site_id = s.site_id
left join product p on f.product_id = p.product_id
