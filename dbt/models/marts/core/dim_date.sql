{{
    config(
        materialized='table',
        unique_key='date_key',
        tags=['conformed', 'static']
    )
}}

/*
    Conformed date dimension, South African fiscal calendar (April to March).
    Marked as the date table in the Power BI semantic model.
*/

with source as (

    select * from {{ ref('stg_dim_date') }}

),

enriched as (

    select
        date_key,
        full_date,
        day_of_month,
        day_of_week,
        day_name,
        day_of_year,
        week_of_year,
        month_number,
        month_name,
        quarter_number,
        quarter_name,
        calendar_year,
        fiscal_year,
        fiscal_quarter,
        fiscal_period,
        is_weekend,
        is_public_holiday_za,
        is_trading_day,
        season_southern,
        school_holiday_za,

        cast(calendar_year as varchar) || '-' ||
            lpad(cast(month_number as varchar), 2, '0') as year_month,

        'FY' || cast(fiscal_year as varchar) as fiscal_year_label,

        -- Trading intensity flag used by the demand-forecast feature set: the
        -- day before a public holiday is the strongest fuel day of the year.
        is_weekend or is_public_holiday_za as is_non_working_day

    from source

)

select * from enriched
