{{
    config(
        materialized='table',
        unique_key='product_key',
        tags=['conformed', 'daily']
    )
}}

/*
    Conformed product dimension across every energy line: road fuels, aviation,
    marine, LPG, lubricants, convenience retail and EV/solar energy.
*/

with source as (

    select * from {{ ref('stg_dim_product') }}

),

enriched as (

    select
        product_key,
        product_id,
        product_name,
        category,
        subcategory,
        brand,
        uom,
        base_price_zar,
        base_cost_zar,
        regulated,
        hazard_class,
        shelf_life_days,

        {{ zar('base_price_zar - base_cost_zar') }} as base_unit_margin_zar,

        {{ safe_divide('base_price_zar - base_cost_zar', 'base_price_zar') }} * 100
            as base_margin_pct,

        -- Regulated fuels are thin-margin volume; the growth story sits in the
        -- unregulated lines, so this split drives most executive reporting.
        case
            when regulated then 'Regulated'
            else 'Unregulated'
        end as price_regime,

        case
            when category = 'Fuel' and subcategory in ('Petrol', 'Diesel') then 'Road Fuel'
            when category = 'Fuel' and subcategory = 'Aviation' then 'Aviation'
            when category = 'Fuel' and subcategory = 'Marine' then 'Marine'
            when category = 'Fuel' then 'Other Fuel'
            else category
        end as reporting_line,

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
        The unknown member -- see the equivalent block in `dim_site` for the
        reasoning. A product code the dimension has not received is referential
        drift, and the fact row that carries it still represents real revenue.
    */
    select
        -1 as product_key,
        'UNKNOWN' as product_id,
        'Unknown product' as product_name,
        'Unknown' as category,
        'Unknown' as subcategory,
        'Unknown' as brand,
        'Unknown' as uom,
        cast(null as double) as base_price_zar,
        cast(null as double) as base_cost_zar,
        false as regulated,
        'Unknown' as hazard_class,
        cast(null as bigint) as shelf_life_days,
        cast(null as {{ dbt.type_numeric() }}) as base_unit_margin_zar,
        cast(null as double) as base_margin_pct,
        'Unknown' as price_regime,
        'Unknown' as reporting_line,
        cast('1900-01-01' as timestamp) as effective_from_date,
        cast('9999-12-31' as timestamp) as effective_to_date,
        true as is_current,
        1 as scd_version,
        'unknown-member' as dw_hash_diff,
        'system' as record_source

)

select * from enriched
union all
select * from unknown_member
