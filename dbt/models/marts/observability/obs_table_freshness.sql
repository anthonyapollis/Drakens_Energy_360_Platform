{{
    config(
        materialized='table',
        tags=['observability', 'sla']
    )
}}

/*
    Grain: one row per monitored source table.

    Answers the question a platform owner is actually asked at 08:00: "is
    today's data in, and if not, which feed is late?" The SLA per source comes
    from dim_data_source rather than being hard-coded, so changing an SLA is a
    reference-data change and not a code deployment.
*/

{% set monitored = [
    ('fact_retail_fuel_sales',      'transaction_ts', 'SRC01'),
    ('fact_shop_sales',             'transaction_ts', 'SRC02'),
    ('fact_tank_dips',              'dip_ts',         'SRC03'),
    ('fact_deliveries',             'planned_arrival_ts', 'SRC04'),
    ('fact_ev_charging_sessions',   'session_start_ts',  'SRC05'),
    ('fact_solar_generation',       'reading_ts',     'SRC06'),
    ('fact_commercial_orders',      'order_ts',       'SRC07'),
    ('fact_general_ledger',         'posting_date',   'SRC08'),
    ('fact_customer_service_cases', 'opened_ts',      'SRC09'),
    ('fact_loyalty_transactions',   'transaction_ts', 'SRC10'),
    ('fact_digital_events',         'event_ts',       'SRC11'),
    ('fact_maintenance_work_orders','raised_ts',      'SRC12'),
    ('fact_hsseq_incidents',        'incident_ts',    'SRC13'),
    ('fact_terminal_receipts',      'receipt_ts',     'SRC14')
] %}

with measured as (

{% for table, ts_col, src in monitored %}
    select
        '{{ table }}' as table_name,
        '{{ src }}' as data_source_code,
        '{{ ts_col }}' as watermark_column,
        count(*) as row_count,
        cast(max({{ ts_col }}) as timestamp) as max_event_ts,
        cast(min({{ ts_col }}) as timestamp) as min_event_ts,
        cast(max(ingested_at) as timestamp) as max_ingested_at
    from {{ ref('stg_' ~ table) }}
    {% if not loop.last %}union all{% endif %}
{% endfor %}

),

with_sla as (

    select
        m.table_name,
        m.data_source_code,
        s.data_source_name,
        s.ingestion_pattern,
        s.owning_domain,
        s.sla_minutes,
        s.is_pii_bearing,
        m.watermark_column,
        m.row_count,
        m.min_event_ts,
        m.max_event_ts,
        m.max_ingested_at,
        {{ dbt.datediff('m.max_event_ts', 'm.max_ingested_at', 'minute') }}
            as ingestion_lag_minutes
    from measured m
    left join {{ ref('stg_dim_data_source') }} s
        on m.data_source_code = s.data_source_code

)

select
    *,
    ingestion_lag_minutes > sla_minutes as is_sla_breached,
    case
        when ingestion_lag_minutes is null then 'Unknown'
        when ingestion_lag_minutes <= sla_minutes then 'Within SLA'
        when ingestion_lag_minutes <= sla_minutes * 2 then 'Degraded'
        else 'Breached'
    end as sla_status,
    {{ safe_divide('ingestion_lag_minutes', 'sla_minutes') }} * 100
        as sla_consumption_pct
from with_sla
