{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        incremental_strategy='merge' if target.type == 'databricks' else 'delete+insert',
        partition_by=['date_key'] if target.type == 'databricks' else none,
        tags=['retail', 'high_volume', 'hourly']
    )
}}

/*
    Grain: one row per retail fuel sales transaction line.

    The largest fact in the model (5,000,000 rows at portfolio scale). It is
    incremental with a lookback window rather than a full rebuild, because a
    full refresh of this table is the single most expensive job in the platform.

    On Databricks this merges into a Delta table partitioned by date_key and
    liquid-clustered on site_id; on DuckDB it uses delete+insert, which is the
    closest equivalent.
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

        -- conformed dimension keys
        s.site_key,
        p.product_key,

        -- degenerate and descriptive attributes
        f.site_id,
        f.product_id,
        s.province,
        s.city,
        s.country_code,
        s.urban_class,
        s.site_type,
        s.ownership_model,
        s.demand_band,
        p.product_name,
        p.subcategory as fuel_grade,
        p.reporting_line,
        p.regulated as is_regulated_price,
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
