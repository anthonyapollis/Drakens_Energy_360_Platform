{{
    config(
        materialized='table',
        tags=['executive', 'aggregate', 'daily']
    )
}}

/*
    Grain: one row per province per day.

    The single table behind the executive dashboard. Deliberately narrow and
    pre-aggregated so a C-level page renders from a few thousand rows instead
    of scanning tens of millions.
*/

with fuel as (

    select
        date_key,
        province,
        sum(litres) as fuel_litres,
        sum(gross_sales_zar) as fuel_revenue_zar,
        sum(gross_margin_zar) as fuel_margin_zar,
        sum(transaction_count) as fuel_transactions,
        count(distinct site_key) as trading_sites
    from {{ ref('agg_site_daily_fuel') }}
    group by 1, 2

),

shop as (

    select
        f.date_key,
        s.province,
        sum(f.gross_sales_zar) as shop_revenue_zar,
        sum(f.gross_margin_zar) as shop_margin_zar
    from {{ ref('stg_fact_shop_sales') }} f
    join {{ ref('dim_site') }} s on f.site_id = s.site_id and s.is_current
    group by 1, 2

),

deliveries as (

    select
        d.date_key,
        s.province,
        count(*) as delivery_count,
        sum(case when d.otif_flag then 1 else 0 end) as otif_deliveries,
        sum(d.delivered_litres) as delivered_litres
    from {{ ref('stg_fact_deliveries') }} d
    join {{ ref('dim_site') }} s
        on d.destination_site_id = s.site_id and s.is_current
    group by 1, 2

),

safety as (

    select
        i.date_key,
        s.province,
        count(*) as incident_count,
        sum(case when i.is_reportable then 1 else 0 end) as reportable_incidents,
        sum(case when i.is_lost_time_injury then 1 else 0 end) as lost_time_injuries
    from {{ ref('stg_fact_hsseq_incidents') }} i
    join {{ ref('dim_site') }} s on i.site_id = s.site_id and s.is_current
    group by 1, 2

),

new_energy as (

    select
        e.date_key,
        s.province,
        count(*) as ev_sessions,
        sum(e.energy_kwh) as ev_kwh,
        sum(e.gross_margin_zar) as ev_margin_zar
    from {{ ref('stg_fact_ev_charging_sessions') }} e
    join {{ ref('dim_site') }} s on e.site_id = s.site_id and s.is_current
    group by 1, 2

)

select
    f.date_key,
    dd.full_date,
    dd.day_name,
    dd.month_name,
    dd.calendar_year,
    dd.fiscal_year,
    dd.fiscal_quarter,
    dd.is_weekend,
    dd.is_public_holiday_za,
    f.province,

    f.trading_sites,
    f.fuel_litres,
    {{ zar('f.fuel_revenue_zar') }} as fuel_revenue_zar,
    {{ zar('f.fuel_margin_zar') }} as fuel_margin_zar,
    f.fuel_transactions,

    {{ zar('coalesce(sh.shop_revenue_zar, 0)') }} as shop_revenue_zar,
    {{ zar('coalesce(sh.shop_margin_zar, 0)') }} as shop_margin_zar,

    {{ zar('f.fuel_revenue_zar + coalesce(sh.shop_revenue_zar, 0)') }}
        as total_revenue_zar,
    {{ zar('f.fuel_margin_zar + coalesce(sh.shop_margin_zar, 0)
            + coalesce(ne.ev_margin_zar, 0)') }} as total_margin_zar,

    coalesce(d.delivery_count, 0) as delivery_count,
    coalesce(d.otif_deliveries, 0) as otif_deliveries,
    {{ safe_divide('d.otif_deliveries', 'd.delivery_count') }} * 100 as otif_pct,

    coalesce(sa.incident_count, 0) as incident_count,
    coalesce(sa.reportable_incidents, 0) as reportable_incidents,
    coalesce(sa.lost_time_injuries, 0) as lost_time_injuries,

    coalesce(ne.ev_sessions, 0) as ev_sessions,
    coalesce(ne.ev_kwh, 0) as ev_kwh,

    {{ safe_divide('f.fuel_margin_zar + coalesce(sh.shop_margin_zar, 0)',
                   'f.fuel_revenue_zar + coalesce(sh.shop_revenue_zar, 0)') }} * 100
        as gross_margin_pct,
    {{ safe_divide('coalesce(sh.shop_margin_zar, 0)',
                   'f.fuel_margin_zar + coalesce(sh.shop_margin_zar, 0)') }} * 100
        as non_fuel_margin_share_pct,
    {{ safe_divide('f.fuel_litres', 'f.trading_sites') }} as litres_per_site

from fuel f
left join {{ ref('dim_date') }} dd on f.date_key = dd.date_key
left join shop sh on f.date_key = sh.date_key and f.province = sh.province
left join deliveries d on f.date_key = d.date_key and f.province = d.province
left join safety sa on f.date_key = sa.date_key and f.province = sa.province
left join new_energy ne on f.date_key = ne.date_key and f.province = ne.province
