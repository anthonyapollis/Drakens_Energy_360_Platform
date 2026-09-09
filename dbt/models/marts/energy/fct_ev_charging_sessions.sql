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
),

/*
    Resolve each session to a product.

    The fact carried no product key, so EV revenue could not be reported
    alongside any other line -- R1.67m and 232,029 kWh invisible to every
    product analysis in the platform.

    The mapping is derived from `connector_type`, the physical connector on
    the cable.

    It could not come from `is_dc_fast`, because that column was not a source
    field at all: it was derived here as `rated_power_kw >= 60`, on power
    alone, with no reference to the connector. That labelled 1,326 sessions on
    a Type 2 AC cable as DC fast charging, which is not a thing that can
    happen -- an AC connector does not deliver DC no matter how it is rated.
    The derivation now requires a DC connector as well as the power, and the
    sessions where the power rating alone would have said otherwise are
    published as a measurable rather than quietly reclassified.

    Solar Generation is a third Energy product with no fact anywhere. It is
    left unmapped rather than given an invented share of EV sessions: an
    allocation nobody can defend is worse than an honest gap.
*/
ev_product as (
    select product_key, product_name
    from {{ ref('dim_product') }}
    where is_current and product_name in ('EV DC Fast Charge', 'EV AC Charge')
),

classified as (
    select
        e.*,
        case
            when upper(trim(coalesce(e.connector_type, ''))) in
                 ('CCS2', 'CHADEMO')              then 'EV DC Fast Charge'
            when upper(trim(coalesce(e.connector_type, ''))) = 'TYPE 2 AC'
                                                  then 'EV AC Charge'
        end as resolved_product_name
    from sessions e
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

    coalesce(p.product_key, -1)              as product_key,
    coalesce(e.resolved_product_name,
             'Unmapped connector')          as product_name,
    -- Sessions the old power-only rule would have misclassified. Published
    -- rather than silently corrected: how often a derivation contradicts the
    -- hardware is worth a number.
    (upper(trim(coalesce(e.connector_type, ''))) = 'TYPE 2 AC'
     and e.rated_power_kw >= 60)            as power_rating_contradicts_connector,

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

    -- DC fast charging needs a DC connector, not merely a high power
    -- rating. The previous definition was the rating alone.
    (upper(trim(coalesce(e.connector_type, ''))) in ('CCS2', 'CHADEMO')
     and e.rated_power_kw >= 60)            as is_dc_fast,

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

from classified e
left join ev_product p on p.product_name = e.resolved_product_name
left join site s on e.site_id = s.site_id
