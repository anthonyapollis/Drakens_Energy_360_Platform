{{
    config(
        materialized='incremental',
        unique_key='delivery_id',
        incremental_strategy='merge' if target.type == 'databricks' else 'delete+insert',
        tags=['supply', 'logistics', 'hourly']
    )
}}

/*
    Grain: one row per physical primary-distribution delivery.

    OTIF is defined once here -- on time within the configured threshold AND
    delivered in full -- so every downstream report and the late-delivery ML
    model use the identical definition. Redefining OTIF in the BI layer is the
    classic way two dashboards end up disagreeing.
*/

with deliveries as (

    select * from {{ ref('stg_fact_deliveries') }}
    {{ incremental_window('planned_arrival_ts') }}

),

site as (
    select site_key, site_id, province, city, urban_class, country_code
    from {{ ref('dim_site') }} where is_current
),

product as (
    select product_key, product_id, product_name, subcategory
    from {{ ref('dim_product') }} where is_current
)

select
    d.delivery_id,
    d.planned_arrival_ts,
    d.actual_arrival_ts,
    d.date_key,

    s.site_key as destination_site_key,
    p.product_key,

    d.route_id,
    d.origin_terminal_id,
    d.destination_site_id,
    d.vehicle_id,
    d.driver_id,
    d.carrier_id,
    d.product_id,
    s.province,
    s.city,
    s.urban_class,
    p.product_name,

    d.planned_litres,
    d.delivered_litres,
    d.fill_rate_pct,
    d.distance_km,
    d.drop_count,
    d.delay_minutes,
    d.delivery_status,
    d.reason_code,

    -- The single conformed OTIF definition.
    d.delay_minutes <= {{ var('otif_delay_threshold_minutes') }} as is_on_time,
    d.delivered_litres >= d.planned_litres * 0.98 as is_in_full,
    (d.delay_minutes <= {{ var('otif_delay_threshold_minutes') }}
        and d.delivered_litres >= d.planned_litres * 0.98) as is_otif,

    case
        when d.delay_minutes <= 0 then 'Early'
        when d.delay_minutes <= {{ var('otif_delay_threshold_minutes') }} then 'On Time'
        when d.delay_minutes <= 180 then 'Late'
        else 'Severely Late'
    end as punctuality_band,

    {{ safe_divide('d.distance_km', 'd.drop_count') }} as km_per_drop,
    {{ safe_divide('d.delivered_litres', 'd.distance_km') }} as litres_per_km,

    d.source_system_code,
    d.ingested_at,
    d._cleansed_at

from deliveries d
left join site s on d.destination_site_id = s.site_id
left join product p on d.product_id = p.product_id
