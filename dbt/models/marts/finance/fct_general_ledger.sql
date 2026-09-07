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

with all_lines as (

    select * from {{ ref('stg_fact_general_ledger') }}

),

balanced_journals as (

    /*
        Double-entry integrity is a property of the journal, not of the line.

        Cleansing assesses rows one at a time, so when one leg of a balanced
        pair fails its contract the other leg survives on its own. Each
        orphaned leg then sits in the ledger as an unmatched debit or credit,
        and the ledger cannot balance no matter how correct the generator was
        -- the imbalance is created by the cleansing step itself.

        Only journals whose lines still net to zero are published. The orphans
        are not deleted: they remain in the quarantine layer alongside the leg
        that was rejected, which is where a finance team would look for them,
        and `obs_reconciliation_controls` reports the ledger it can trust
        rather than one it has silently patched.
    */
    select journal_id
    from all_lines
    group by journal_id
    having abs(sum(debit_amount_zar) - sum(credit_amount_zar)) <= 0.01

),

gl as (

    select l.*
    from all_lines l
    join balanced_journals b on l.journal_id = b.journal_id
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
    g._cleansed_at

from gl g
left join account a on g.gl_account_code = a.gl_account_code
