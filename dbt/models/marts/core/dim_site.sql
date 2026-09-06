{{
    config(
        materialized='table',
        unique_key='site_key',
        tags=['conformed', 'daily']
    )
}}

/*
    Conformed site dimension.

    Grain: one row per site per SCD2 version. `is_current` selects the current
    view; the surrogate `site_key` is what facts join on so historical rows keep
    pointing at the site attributes that were true at the time.
*/

with source as (

    select * from {{ ref('stg_dim_site') }}

),

banded as (

    select
        site_key,
        site_id,
        site_name,
        country_code,
        province,
        city,
        urban_class,
        site_type,
        ownership_model,
        site_status,
        latitude,
        longitude,
        on_national_route,
        forecourt_lanes,
        has_convenience,
        has_qsr,
        has_car_wash,
        has_ev_charging,
        has_solar,
        has_lpg,
        is_24_hour,
        opened_date,
        demand_index,

        -- Derived groupings the BI layer would otherwise re-implement in DAX.
        case
            when demand_index >= 2.0 then 'Very High'
            when demand_index >= 1.4 then 'High'
            when demand_index >= 0.9 then 'Medium'
            when demand_index >= 0.5 then 'Low'
            else 'Very Low'
        end as demand_band,

        case
            when has_convenience and has_qsr and has_car_wash then 'Full Offer'
            when has_convenience and has_qsr then 'Shop and QSR'
            when has_convenience then 'Shop Only'
            else 'Fuel Only'
        end as offer_tier,

        case
            when has_ev_charging and has_solar then 'EV and Solar'
            when has_ev_charging then 'EV Only'
            when has_solar then 'Solar Only'
            else 'None'
        end as new_energy_profile,

        {{ dbt.datediff('opened_date', dbt.current_timestamp(), 'day') }} / 365.25
            as site_age_years,

        country_code = 'ZA' as is_south_africa,

        -- SCD2 control columns
        effective_from_date,
        effective_to_date,
        is_current,
        scd_version,
        dw_hash_diff,
        record_source

    from source

)

select * from banded
