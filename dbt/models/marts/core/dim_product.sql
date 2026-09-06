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

)

select * from enriched
