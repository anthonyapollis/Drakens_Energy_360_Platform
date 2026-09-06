{{
    config(
        materialized='table',
        tags=['assets', 'maintenance', 'daily', 'ml_feature_source']
    )
}}

/*
    Grain: one row per maintenance work order.

    Feature source for ml/experiments/predictive_maintenance.py. Asset age and
    criticality are carried on the fact deliberately: they are the state at the
    time the work order was raised, and re-deriving them from the current
    dimension at training time would leak future information into the model.
*/

with work_orders as (

    select * from {{ ref('stg_fact_maintenance_work_orders') }}

),

site as (
    select site_key, site_id, province, urban_class, demand_band
    from {{ ref('dim_site') }} where is_current
)

select
    w.work_order_id,
    w.raised_ts,
    w.completed_ts,
    w.date_key,

    s.site_key,
    w.asset_id,
    w.site_id,
    s.province,
    s.urban_class,
    s.demand_band,

    w.asset_type,
    w.criticality,
    w.asset_age_years,
    w.maintenance_type,
    w.failure_mode,
    w.priority,
    w.technician_employee_id,

    w.response_hours,
    w.labour_hours,
    {{ zar('w.labour_cost_zar') }} as labour_cost_zar,
    {{ zar('w.parts_cost_zar') }} as parts_cost_zar,
    {{ zar('w.total_cost_zar') }} as total_cost_zar,

    w.is_completed,
    w.is_breakdown,
    w.sla_breached,

    w.maintenance_type in ('Preventive', 'Predictive', 'Statutory Inspection')
        as is_planned,

    case
        when w.asset_age_years < 5 then '0-5'
        when w.asset_age_years < 10 then '5-10'
        when w.asset_age_years < 15 then '10-15'
        else '15+'
    end as asset_age_band,

    -- Total downtime attributable to this order, the measure the reliability
    -- KPI is built on.
    w.response_hours + w.labour_hours as total_hours_out_of_service,

    w.source_system_code,
    w.ingested_at,
    w._dbt_loaded_at

from work_orders w
left join site s on w.site_id = s.site_id
