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

),

unknown_member as (

    /*
        The unknown member -- see `dim_site` for the full reasoning. A
        commercial order carrying a customer code the dimension never received
        is still a real order for real volume. Resolving it to -1 keeps it in
        every total and makes the drift countable; a null key would drop it
        from revenue by sector without anyone noticing.
    */
    select
        -1 as customer_key,
        'UNKNOWN' as customer_id,
        'Unknown customer' as customer_name,
        'Unknown' as sector,
        'Unknown' as segment,
        'ZZ' as country_code,
        'Unknown' as credit_band,
        cast(null as double) as credit_limit_zar,
        cast(null as bigint) as payment_terms_days,
        cast(null as timestamp) as onboarded_date,
        false as is_active,
        cast(null as double) as revenue_index,
        'Unknown' as service_model,
        'Unknown' as credit_risk_tier,
        false as is_industrial,
        cast(null as bigint) as customer_tenure_days,
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
