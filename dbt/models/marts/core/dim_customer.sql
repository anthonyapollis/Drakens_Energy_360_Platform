{{
    config(
        materialized='table',
        unique_key='customer_key',
        tags=['conformed', 'daily', 'contains_pii']
    )
}}

/*
    Conformed customer dimension.

    Tagged `contains_pii` so the Unity Catalog masking policy in
    databricks/sql/03_governance.sql applies to customer_name for anyone
    outside the commercial-analyst group. All names here are synthetic, but the
    governance pattern is modelled as it would be in production.
*/

with source as (

    select * from {{ ref('stg_dim_customer') }}

),

enriched as (

    select
        customer_key,
        customer_id,
        customer_name,
        sector,
        segment,
        country_code,
        credit_band,
        credit_limit_zar,
        payment_terms_days,
        onboarded_date,
        is_active,
        revenue_index,

        case
            when segment in ('Strategic', 'Key Account') then 'Managed'
            when segment = 'Mid Market' then 'Inside Sales'
            else 'Self Serve'
        end as service_model,

        case
            when credit_band in ('A', 'B') then 'Low'
            when credit_band = 'C' then 'Medium'
            else 'High'
        end as credit_risk_tier,

        sector in ('Mining', 'Construction', 'Power Generation', 'Manufacturing')
            as is_industrial,

        {{ dbt.datediff('onboarded_date', dbt.current_timestamp(), 'day') }}
            as customer_tenure_days,

        effective_from_date,
        effective_to_date,
        is_current,
        scd_version,
        dw_hash_diff,
        record_source

    from source

)

select * from enriched
