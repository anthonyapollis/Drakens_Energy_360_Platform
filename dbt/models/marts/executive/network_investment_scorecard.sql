{{
    config(
        materialized='table',
        tags=['executive', 'decision_support', 'daily']
    )
}}

/*
    Grain: one row per site.

    The decision-support layer for network investment: for every site in the
    network it assembles trading performance, asset condition, new-energy
    readiness and safety record into a single comparable view, then scores each
    site so capital can be ranked rather than argued.

    This model deliberately produces a *recommendation with its inputs visible*
    rather than an opaque score. Every component is a named column so a
    reviewer can see exactly why a site was ranked where it was, which is what
    makes it defensible in an executive forum.

    The optimisation that allocates a constrained capital budget across these
    scores lives in ml/network_investment_engine.py; this model is its input.
*/

with trading as (

    select
        site_key,
        site_id,
        count(distinct date_key) as trading_days,
        sum(litres) as litres_total,
        sum(gross_sales_zar) as fuel_revenue_zar,
        sum(gross_margin_zar) as fuel_margin_zar,
        sum(transaction_count) as transaction_count,
        avg(litres) as avg_daily_litres,
        stddev_samp(litres) as stddev_daily_litres
    from {{ ref('agg_site_daily_fuel') }}
    group by 1, 2

),

-- Recent versus prior period, to separate a big site from a growing one.
trend as (

    select
        site_key,
        sum(case when full_date >= date_trunc('month', current_date) - interval '3' month
                 then litres else 0 end) as litres_last_3m,
        sum(case when full_date >= date_trunc('month', current_date) - interval '6' month
                 and full_date < date_trunc('month', current_date) - interval '3' month
                 then litres else 0 end) as litres_prior_3m
    from {{ ref('agg_site_daily_fuel') }}
    group by 1

),

shop as (

    select
        site_id,
        sum(gross_sales_zar) as shop_revenue_zar,
        sum(gross_margin_zar) as shop_margin_zar
    from {{ ref('stg_fact_shop_sales') }}
    group by 1

),

assets as (

    select
        site_id,
        count(*) as work_order_count,
        sum(case when is_breakdown then 1 else 0 end) as breakdown_count,
        sum(total_cost_zar) as maintenance_cost_zar,
        avg(asset_age_years) as avg_asset_age_years
    from {{ ref('stg_fact_maintenance_work_orders') }}
    group by 1

),

downtime as (

    select
        site_id,
        sum(downtime_hours) as downtime_hours,
        sum(lost_revenue_zar) as downtime_lost_revenue_zar
    from {{ ref('stg_fact_asset_downtime') }}
    group by 1

),

safety as (

    select
        site_id,
        count(*) as incident_count,
        sum(case when is_reportable then 1 else 0 end) as reportable_incident_count,
        sum(estimated_cost_zar) as incident_cost_zar
    from {{ ref('stg_fact_hsseq_incidents') }}
    group by 1

),

ev as (

    select
        site_id,
        count(*) as ev_session_count,
        sum(revenue_zar) as ev_revenue_zar,
        sum(gross_margin_zar) as ev_margin_zar
    from {{ ref('stg_fact_ev_charging_sessions') }}
    group by 1

),

solar as (

    select
        site_id,
        sum(energy_kwh) as solar_kwh,
        sum(co2_avoided_kg) as co2_avoided_kg
    from {{ ref('stg_fact_solar_generation') }}
    group by 1

),

combined as (

    select
        s.site_key,
        s.site_id,
        s.site_name,
        s.country_code,
        s.province,
        s.city,
        s.urban_class,
        s.site_type,
        s.ownership_model,
        s.site_status,
        s.on_national_route,
        s.offer_tier,
        s.new_energy_profile,
        s.has_convenience,
        s.has_ev_charging,
        s.has_solar,
        s.site_age_years,
        s.latitude,
        s.longitude,
        s.demand_band,

        coalesce(t.trading_days, 0) as trading_days,
        coalesce(t.litres_total, 0) as litres_total,
        coalesce(t.avg_daily_litres, 0) as avg_daily_litres,
        coalesce(t.fuel_revenue_zar, 0) as fuel_revenue_zar,
        coalesce(t.fuel_margin_zar, 0) as fuel_margin_zar,
        coalesce(t.transaction_count, 0) as transaction_count,

        coalesce(sh.shop_revenue_zar, 0) as shop_revenue_zar,
        coalesce(sh.shop_margin_zar, 0) as shop_margin_zar,

        coalesce(e.ev_session_count, 0) as ev_session_count,
        coalesce(e.ev_margin_zar, 0) as ev_margin_zar,
        coalesce(so.solar_kwh, 0) as solar_kwh,
        coalesce(so.co2_avoided_kg, 0) as co2_avoided_kg,

        coalesce(a.work_order_count, 0) as work_order_count,
        coalesce(a.breakdown_count, 0) as breakdown_count,
        coalesce(a.maintenance_cost_zar, 0) as maintenance_cost_zar,
        a.avg_asset_age_years,
        coalesce(d.downtime_hours, 0) as downtime_hours,
        coalesce(d.downtime_lost_revenue_zar, 0) as downtime_lost_revenue_zar,

        coalesce(sf.incident_count, 0) as incident_count,
        coalesce(sf.reportable_incident_count, 0) as reportable_incident_count,
        coalesce(sf.incident_cost_zar, 0) as incident_cost_zar,

        -- Growth: last three months against the three before them.
        {{ safe_divide('tr.litres_last_3m - tr.litres_prior_3m', 'tr.litres_prior_3m') }} * 100
            as volume_growth_pct,

        -- Volatility of daily throughput; a proxy for demand reliability.
        {{ safe_divide('t.stddev_daily_litres', 't.avg_daily_litres') }}
            as demand_volatility

    from {{ ref('dim_site') }} s
    left join trading t on s.site_key = t.site_key
    left join trend tr on s.site_key = tr.site_key
    left join shop sh on s.site_id = sh.site_id
    left join assets a on s.site_id = a.site_id
    left join downtime d on s.site_id = d.site_id
    left join safety sf on s.site_id = sf.site_id
    left join ev e on s.site_id = e.site_id
    left join solar so on s.site_id = so.site_id
    where s.is_current

),

economics as (

    select
        *,
        fuel_margin_zar + shop_margin_zar + ev_margin_zar as total_margin_zar,
        fuel_revenue_zar + shop_revenue_zar as total_revenue_zar,
        maintenance_cost_zar + incident_cost_zar + downtime_lost_revenue_zar
            as total_site_cost_zar,
        fuel_margin_zar + shop_margin_zar + ev_margin_zar
            - (maintenance_cost_zar + incident_cost_zar + downtime_lost_revenue_zar)
            as contribution_zar,

        {{ safe_divide('shop_margin_zar', 'fuel_margin_zar + shop_margin_zar') }} * 100
            as non_fuel_margin_share_pct,

        {{ safe_divide('breakdown_count', 'work_order_count') }} * 100
            as breakdown_rate_pct

    from combined

),

/*
    Percentile ranks put every site on a comparable 0-1 scale regardless of
    units, so a rand figure and an incident count can be combined without one
    swamping the other.
*/
ranked as (

    select
        *,
        percent_rank() over (order by contribution_zar) as r_contribution,
        percent_rank() over (order by avg_daily_litres) as r_throughput,
        percent_rank() over (order by coalesce(volume_growth_pct, 0)) as r_growth,
        percent_rank() over (order by non_fuel_margin_share_pct) as r_non_fuel,
        -- Inverted: high cost, downtime, breakdowns and incidents are bad.
        1 - percent_rank() over (order by coalesce(breakdown_rate_pct, 0)) as r_reliability,
        1 - percent_rank() over (order by downtime_hours) as r_uptime,
        1 - percent_rank() over (order by reportable_incident_count) as r_safety,
        1 - percent_rank() over (order by coalesce(avg_asset_age_years, 0)) as r_asset_condition
    from economics

),

scored as (

    select
        *,
        /*
            Weights are an explicit management judgement, not a fitted model.
            They are stated here so an executive can challenge them directly:
            current profitability and throughput carry half the weight, growth
            and non-fuel mix a quarter, and operational risk the remainder.
        */
        round(100 * (
              0.30 * r_contribution
            + 0.20 * r_throughput
            + 0.15 * r_growth
            + 0.10 * r_non_fuel
            + 0.10 * r_reliability
            + 0.05 * r_uptime
            + 0.05 * r_safety
            + 0.05 * r_asset_condition
        ), 2) as investment_score

    from ranked

)

select
    *,
    ntile(4) over (order by investment_score desc) as investment_quartile,

    /*
        The recommendation is intentionally coarse. It is a starting position
        for a capital conversation, not an instruction: a site can score badly
        and still be strategically necessary (sole coverage of a corridor),
        which is why `on_national_route` stays visible next to the verdict.
    */
    case
        when investment_score >= 75 and coalesce(volume_growth_pct, 0) > 0
            then 'Invest - Expand'
        when investment_score >= 75
            then 'Invest - Maintain Leadership'
        when investment_score >= 50 and coalesce(avg_asset_age_years, 0) > 12
            then 'Invest - Refurbish'
        when investment_score >= 50
            then 'Hold'
        when investment_score >= 25 and on_national_route
            then 'Hold - Strategic Coverage'
        when investment_score >= 25
            then 'Review'
        else 'Divest Candidate'
    end as investment_recommendation

from scored
