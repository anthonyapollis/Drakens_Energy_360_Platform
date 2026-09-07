{{
    config(
        materialized='table',
        tags=['new_energy', 'ev', 'hourly']
    )
}}

/*
    Grain: one row per EV charging session.
*/

with sessions as (

    select * from {{ ref('stg_fact_ev_charging_sessions') }}

),

site as (
    select site_key, site_id, province, city, urban_class, on_national_route
    from {{ ref('dim_site') }} where is_current
)

select
    e.ev_session_id,
    e.session_start_ts,
    e.session_end_ts,
    e.date_key,
    e.time_key,

    s.site_key,
    e.ev_charger_id,
    e.site_id,
    s.province,
    s.city,
    s.urban_class,
    s.on_national_route,

    e.connector_type,
    e.rated_power_kw,
    e.payment_method,
    e.session_ended_by,

    e.duration_minutes,
    e.energy_kwh,
    e.average_power_kw,
    e.tariff_zar_per_kwh,
    {{ zar('e.revenue_zar') }} as revenue_zar,
    {{ zar('e.grid_cost_zar') }} as grid_cost_zar,
    {{ zar('e.gross_margin_zar') }} as gross_margin_zar,
    e.start_soc_pct,
    e.end_soc_pct,

    e.rated_power_kw >= 60 as is_dc_fast,

    -- Utilisation is the number that decides whether more chargers are worth
    -- installing, so it is defined once here rather than in the BI layer.
    {{ safe_divide('e.average_power_kw', 'e.rated_power_kw') }} * 100
        as power_utilisation_pct,
    {{ safe_divide('e.gross_margin_zar', 'e.energy_kwh') }}
        as margin_zar_per_kwh,
    e.end_soc_pct - e.start_soc_pct as soc_delta_pct,

    case
        when e.duration_minutes < 20 then 'Top Up'
        when e.duration_minutes < 60 then 'Standard'
        when e.duration_minutes < 180 then 'Long Dwell'
        else 'Overnight'
    end as session_profile,

    e.source_system_code,
    e.ingested_at,
    e._cleansed_at

from sessions e
left join site s on e.site_id = s.site_id
