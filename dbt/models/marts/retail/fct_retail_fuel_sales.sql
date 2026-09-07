{#
    Not partitioned by date_key. That is the obvious choice -- every query
    filters on a date range -- and it is wrong here: 974 days in the window
    means 974 partitions of a fraction of a megabyte each, and OPTIMIZE never
    merges across a partition boundary, so those small files are permanent.
    Measured, not assumed: see docs/portfolio_case_study.md. Liquid clustering
    gives the same data skipping without fixing the physical layout.
#}
{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        incremental_strategy='merge' if target.type == 'databricks' else 'delete+insert',
        liquid_clustered_by=['date_key', 'site_id'] if target.type == 'databricks' else none,
        tags=['retail', 'high_volume', 'hourly']
    )
}}

/*
    Grain: one row per retail fuel sales transaction line.

    The largest fact in the model (5,000,000 rows at portfolio scale). It is
    incremental with a lookback window rather than a full rebuild, because a
    full refresh of this table is the single most expensive job in the platform.

    On Databricks this merges into a Delta table liquid-clustered on
    (date_key, site_id); on DuckDB it uses delete+insert, which is the closest
    equivalent.
*/

with fuel_sales as (

    select * from {{ ref('stg_fact_retail_fuel_sales') }}
    {{ incremental_window('transaction_ts') }}

),

site as (

    select
        site_key,
        site_id,
        province,
        city,
        country_code,
        urban_class,
        site_type,
        ownership_model,
        demand_band
    from {{ ref('dim_site') }}
    where is_current

),

product as (

    select
        product_key,
        product_id,
        product_name,
        category,
        subcategory,
        reporting_line,
        regulated
    from {{ ref('dim_product') }}
    where is_current

),

joined as (

    select
        f.transaction_id,
        f.transaction_ts,
        f.date_key,
        f.time_key,

        -- Conformed dimension keys, resolved to the unknown member rather
        -- than left null. The landing zone contains referential drift by
        -- design; a fact carrying a site code the dimension never received is
        -- still a real transaction with real litres and real margin. Nulling
        -- its key would drop it from every inner join and from any total
        -- grouped by province, which is how revenue goes quietly missing.
        coalesce(s.site_key, -1) as site_key,
        coalesce(p.product_key, -1) as product_key,

        -- degenerate and descriptive attributes
        f.site_id,
        f.product_id,
        coalesce(s.province, 'Unknown') as province,
        coalesce(s.city, 'Unknown') as city,
        coalesce(s.country_code, 'ZZ') as country_code,
        coalesce(s.urban_class, 'Unknown') as urban_class,
        coalesce(s.site_type, 'Unknown') as site_type,
        coalesce(s.ownership_model, 'Unknown') as ownership_model,
        coalesce(s.demand_band, 'Unknown') as demand_band,
        coalesce(p.product_name, 'Unknown product') as product_name,
        coalesce(p.subcategory, 'Unknown') as fuel_grade,
        coalesce(p.reporting_line, 'Unknown') as reporting_line,
        coalesce(p.regulated, false) as is_regulated_price,

        -- Makes the drift countable without needing to know the sentinel.
        s.site_key is null as is_unmatched_site,
        p.product_key is null as is_unmatched_product,
        f.pump_number,
        f.forecourt_lane,
        f.shift_name,
        f.payment_method,
        f.loyalty_flag,
        f.loyalty_member_id,
        f.is_fleet_sale,

        -- additive measures
        f.litres,
        {{ zar('f.gross_sales_zar') }} as gross_sales_zar,
        {{ zar('f.cogs_zar') }} as cogs_zar,
        {{ zar('f.gross_margin_zar') }} as gross_margin_zar,

        -- non-additive: kept as a ratio for inspection only. The semantic
        -- model recomputes margin % as SUM(margin)/SUM(revenue), never as an
        -- average of this column.
        f.unit_price_zar,
        {{ safe_divide('f.gross_margin_zar', 'f.gross_sales_zar') }} * 100
            as line_margin_pct,
        {{ safe_divide('f.gross_margin_zar', 'f.litres') }} * 100
            as margin_cents_per_litre,

        f.source_system_code,
        f.ingested_at,
        f._cleansed_at

    from fuel_sales f
    left join site s on f.site_id = s.site_id
    left join product p on f.product_id = p.product_id

)

select * from joined
