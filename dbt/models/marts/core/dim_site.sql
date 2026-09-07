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

),

unknown_member as (

    /*
        The unknown member.

        The landing zone contains referential drift by design -- a site code in
        a fact that the dimension has not received. Left joining those facts
        produces a null foreign key, and a null foreign key is the wrong answer
        twice over: it silently drops the row from every inner join, and it
        cannot be counted, filtered or explained.

        Kimball's answer is a real dimension row standing for "we do not know".
        The fact keeps its revenue, the unmatched-ness becomes queryable
        (`where site_key = -1`), and nothing disappears from a total.

        The key is -1 rather than 0 so it can never collide with a generated
        surrogate, and the descriptive attributes say 'Unknown' rather than
        being null, so a report grouped by province shows an Unknown bar
        instead of a blank one.
    */
    select
        -1 as site_key,
        'UNKNOWN' as site_id,
        'Unknown site' as site_name,
        'ZZ' as country_code,
        'Unknown' as province,
        'Unknown' as city,
        'Unknown' as urban_class,
        'Unknown' as site_type,
        'Unknown' as ownership_model,
        'Unknown' as site_status,
        cast(null as double) as latitude,
        cast(null as double) as longitude,
        false as on_national_route,
        cast(null as integer) as forecourt_lanes,
        false as has_convenience,
        false as has_qsr,
        false as has_car_wash,
        false as has_ev_charging,
        false as has_solar,
        false as has_lpg,
        false as is_24_hour,
        cast(null as date) as opened_date,
        cast(null as double) as demand_index,
        'Unknown' as demand_band,
        'Unknown' as offer_tier,
        'Unknown' as new_energy_profile,
        cast(null as double) as site_age_years,
        false as is_south_africa,
        cast('1900-01-01' as date) as effective_from_date,
        cast('9999-12-31' as date) as effective_to_date,
        true as is_current,
        1 as scd_version,
        'unknown-member' as dw_hash_diff,
        'system' as record_source

)

select * from banded
union all
select * from unknown_member
