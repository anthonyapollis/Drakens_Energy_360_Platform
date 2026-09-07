{{
    config(
        materialized='table',
        tags=['retail', 'aggregate', 'daily']
    )
}}

/*
    Grain: one row per site per day.

    The aggregate that most retail reporting and the demand-forecast feature
    set read from, so Power BI never scans the 5-million-row transaction fact
    for a trend line. Roughly a 1000:1 reduction.
*/

with sales as (

    select
        site_key,
        site_id,
        date_key,
        province,
        urban_class,
        site_type,
        demand_band,
        fuel_grade,
        litres,
        gross_sales_zar,
        cogs_zar,
        gross_margin_zar,
        loyalty_flag,
        is_fleet_sale,
        payment_method,
        transaction_id
    from {{ ref('fct_retail_fuel_sales') }}

),

daily as (

    select
        date_key,
        site_key,
        -- The grain is date x site_key. Every fact whose site code did not
        -- match resolves to the same unknown member, so this aggregate must
        -- carry the *member's* identity rather than the unmatched code that
        -- produced it -- otherwise several hundred drifting codes explode one
        -- unknown member into several hundred rows a day and break the grain.
        -- The individual codes stay on the fact, where they can be diagnosed.
        case when site_key = -1 then 'UNKNOWN' else site_id end as site_id,
        province,
        urban_class,
        site_type,
        demand_band,

        count(*) as transaction_count,
        count(distinct fuel_grade) as grades_sold,

        sum(litres) as litres,
        {{ zar('sum(gross_sales_zar)') }} as gross_sales_zar,
        {{ zar('sum(cogs_zar)') }} as cogs_zar,
        {{ zar('sum(gross_margin_zar)') }} as gross_margin_zar,

        sum(case when fuel_grade = 'Diesel' then litres else 0 end) as diesel_litres,
        sum(case when fuel_grade = 'Petrol' then litres else 0 end) as petrol_litres,

        sum(case when loyalty_flag then 1 else 0 end) as loyalty_transactions,
        sum(case when is_fleet_sale then 1 else 0 end) as fleet_transactions,
        sum(case when payment_method = 'Cash' then gross_sales_zar else 0 end)
            as cash_sales_zar

    from sales
    group by 1, 2, 3, 4, 5, 6, 7

),

with_ratios as (

    select
        d.*,
        {{ safe_divide('gross_margin_zar', 'gross_sales_zar') }} * 100
            as gross_margin_pct,
        {{ safe_divide('litres', 'transaction_count') }} as litres_per_transaction,
        {{ safe_divide('gross_sales_zar', 'transaction_count') }}
            as average_transaction_zar,
        {{ safe_divide('loyalty_transactions', 'transaction_count') }} * 100
            as loyalty_penetration_pct,
        {{ safe_divide('diesel_litres', 'litres') }} * 100 as diesel_share_pct
    from daily d

)

select
    w.*,
    dd.full_date,
    dd.day_name,
    dd.month_name,
    dd.calendar_year,
    dd.fiscal_year,
    dd.is_weekend,
    dd.is_public_holiday_za,
    dd.season_southern
from with_ratios w
left join {{ ref('dim_date') }} dd using (date_key)
