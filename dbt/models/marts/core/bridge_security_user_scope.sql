{{
    config(
        materialized='table',
        unique_key=['user_principal', 'scope_type', 'scope_value'],
        tags=['conformed', 'security', 'daily']
    )
}}

/*
    Which provinces each user is allowed to see.

    Grain: one row per user per granted scope. A user with two provinces has
    two rows; a user granted everything has one row with `scope_type = 'all'`.

    This lives in gold rather than silver, and the reason is a governance
    constraint rather than a modelling preference. Analysts have no silver
    access at all -- raw and conformed-but-unpublished data has no agreed
    definitions, and any number taken from it will disagree with the
    dashboard. But the Power BI row-level security role has to read this table
    to resolve the current user's scope, and a role cannot read a table its
    reader is forbidden. Leaving it in silver made the security model
    unenforceable for exactly the group it exists to constrain.

    The scope comes from a table, not from group names, so adding a province
    to someone's remit is a data change rather than a deployment. Hard-coding
    regions into group membership turns every reorganisation into an
    engineering ticket.

    Row-level security is deliberately *not* applied to this table. A user
    must be able to read their own scope for the filter to evaluate, and the
    rows are not sensitive: they record who may see which province, not any
    business figure.
*/

with scope as (

    select
        user_principal,
        scope_type,
        scope_value
    from {{ ref('stg_bridge_security_user_scope') }}
    where user_principal is not null
      and scope_type is not null

),

deduplicated as (

    -- The same grant arriving twice is not two grants. A duplicate here would
    -- multiply rows in any fact joined through the scope, which is the
    -- quietest way for a security table to corrupt a total.
    select distinct
        user_principal,
        scope_type,
        scope_value
    from scope

)

select
    user_principal,
    scope_type,
    scope_value,
    scope_type = 'all' as grants_everything,
    {{ dbt.current_timestamp() }} as dw_loaded_at

from deduplicated
