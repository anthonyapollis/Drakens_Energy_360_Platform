{{
    config(
        materialized='incremental',
        unique_key='journal_line_id',
        incremental_strategy='merge' if target.type == 'databricks' else 'delete+insert',
        tags=['finance', 'daily']
    )
}}

/*
    Grain: one row per posted general-ledger journal line.

    `signed_amount_zar` is the only measure that should be summed. Summing
    debits and credits separately and subtracting is a common source of
    sign errors, so the signed column is computed once, upstream.
*/

with gl as (

    select * from {{ ref('stg_fact_general_ledger') }}
    {{ incremental_window('posting_date') }}

),

account as (

    select
        gl_account_code,
        gl_account_name,
        account_class,
        normal_balance,
        is_pnl
    from {{ ref('stg_dim_gl_account') }}

)

select
    g.journal_line_id,
    g.journal_id,
    g.posting_date,
    g.date_key,
    g.fiscal_period,

    g.gl_account_code,
    a.gl_account_name,
    a.account_class,
    a.normal_balance,
    a.is_pnl,

    g.cost_centre_code,
    g.profit_centre_code,
    g.legal_entity_code,
    g.document_type,
    g.currency_code,

    {{ zar('g.debit_amount_zar') }} as debit_amount_zar,
    {{ zar('g.credit_amount_zar') }} as credit_amount_zar,
    {{ zar('g.signed_amount_zar') }} as signed_amount_zar,

    g.is_reversal,

    case a.account_class
        when 'Revenue' then 'Income Statement'
        when 'COGS' then 'Income Statement'
        when 'Opex' then 'Income Statement'
        when 'Capex' then 'Balance Sheet'
        else 'Balance Sheet'
    end as statement,

    g.source_system_code,
    g.ingested_at,
    g._dbt_loaded_at

from gl g
left join account a on g.gl_account_code = a.gl_account_code
