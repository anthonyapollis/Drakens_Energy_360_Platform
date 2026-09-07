{{
    config(
        materialized='table',
        tags=['supply', 'inventory', 'hourly']
    )
}}

/*
    Grain: one row per location, product and snapshot timestamp.

    A semi-additive fact: stock-on-hand may be summed across locations but
    never across time. The semantic model must use LASTNONBLANK over the date
    axis, which is documented on the measure in powerbi/semantic_model.md.
*/

with snapshots as (

    select * from {{ ref('stg_fact_inventory_snapshot') }}

),

site as (
    select site_key, site_id, province, urban_class, demand_band
    from {{ ref('dim_site') }} where is_current
),

product as (
    select product_key, product_id, product_name, subcategory
    from {{ ref('dim_product') }} where is_current
)

select
    s.snapshot_id,
    s.snapshot_ts,
    s.date_key,
    s.location_type,
    s.site_id,
    s.terminal_id,
    s.product_id,

    si.site_key,
    p.product_key,
    si.province,
    si.demand_band,
    p.product_name,
    p.subcategory as fuel_grade,

    s.capacity_litres,
    s.stock_on_hand_litres,
    s.ullage_litres,
    s.fill_pct,
    s.average_daily_usage_litres,
    s.days_of_cover,
    s.reorder_point_litres,

    -- Conformed stock-out risk definition, used by the ML model and the alert.
    s.days_of_cover < {{ var('stock_out_cover_days') }} as is_stock_out_risk,

    case
        when s.days_of_cover < 0.5 then 'Critical'
        when s.days_of_cover < {{ var('stock_out_cover_days') }} then 'At Risk'
        when s.days_of_cover < 4 then 'Healthy'
        when s.days_of_cover < 10 then 'Long'
        else 'Overstocked'
    end as cover_band,

    s.stock_on_hand_litres <= s.reorder_point_litres as below_reorder_point,

    s.source_system_code,
    s.ingested_at,
    s._cleansed_at

from snapshots s
left join site si on s.site_id = si.site_id
left join product p on s.product_id = p.product_id
