{{
    config(
        materialized='table',
        tags=['commercial', 'aggregate', 'monthly', 'ml_feature_source']
    )
}}

/*
    Grain: one row per customer per month.

    Doubles as the feature table for the customer-churn model in
    ml/experiments/customer_churn.py, which is why recency, frequency and
    monetary measures are all carried explicitly rather than derived at
    training time. Keeping them here means the dashboard and the model agree
    on what "active" means.
*/

with orders as (

    select
        customer_key,
        customer_id,
        sector,
        segment,
        credit_band,
        credit_risk_tier,
        date_key,
        order_ts,
        volume_litres,
        revenue_zar,
        gross_margin_zar,
        discount_value_zar,
        is_cancelled
    from {{ ref('fct_commercial_orders') }}

),

with_month as (

    select
        o.*,
        dd.calendar_year,
        dd.month_number,
        cast(dd.calendar_year as varchar) || '-'
            || lpad(cast(dd.month_number as varchar), 2, '0') as year_month
    from orders o
    join {{ ref('dim_date') }} dd on o.date_key = dd.date_key

),

monthly as (

    select
        year_month,
        calendar_year,
        month_number,
        customer_key,
        -- The grain is month x customer_key. Every order whose customer code
        -- did not match resolves to the same unknown member, so this
        -- aggregate carries the member's identity rather than the unmatched
        -- code -- otherwise the drifting codes break the grain. The codes stay
        -- on the fact, where they can be diagnosed.
        case when customer_key = -1 then 'UNKNOWN' else customer_id end
            as customer_id,
        sector,
        segment,
        credit_band,
        credit_risk_tier,

        count(*) as order_count,
        sum(case when is_cancelled then 1 else 0 end) as cancelled_orders,
        sum(volume_litres) as volume_litres,
        {{ zar('sum(revenue_zar)') }} as revenue_zar,
        {{ zar('sum(gross_margin_zar)') }} as gross_margin_zar,
        {{ zar('sum(discount_value_zar)') }} as discount_value_zar,
        max(order_ts) as last_order_ts,
        min(order_ts) as first_order_ts

    from with_month
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9

),

with_rfm as (

    select
        m.*,
        {{ safe_divide('gross_margin_zar', 'revenue_zar') }} * 100 as margin_pct,
        {{ safe_divide('revenue_zar', 'order_count') }} as avg_order_value_zar,
        {{ safe_divide('discount_value_zar', 'revenue_zar') }} * 100
            as discount_intensity_pct,

        -- Month-on-month movement, the strongest single churn predictor.
        lag(volume_litres) over (
            partition by customer_key order by year_month
        ) as prior_month_volume_litres,
        lag(revenue_zar) over (
            partition by customer_key order by year_month
        ) as prior_month_revenue_zar,

        row_number() over (
            partition by customer_key order by year_month desc
        ) as recency_rank

    from monthly m

)

select
    *,
    {{ safe_divide('volume_litres - prior_month_volume_litres',
                   'prior_month_volume_litres') }} * 100 as volume_mom_pct,
    {{ safe_divide('revenue_zar - prior_month_revenue_zar',
                   'prior_month_revenue_zar') }} * 100 as revenue_mom_pct,
    coalesce(prior_month_volume_litres, 0) > 0
        and volume_litres < prior_month_volume_litres * 0.5 as is_sharp_decline
from with_rfm
