
# Orchestration plan

```mermaid
flowchart LR
    A[00 Validate Landing] --> B[10 Ingest Batch]
    A --> C[11 Ingest Streaming]
    B --> D[20 Bronze DQ]
    C --> D
    D --> E[30 Silver Conformance]
    E --> F[40 dbt Build]
    F --> G[50 dbt Test]
    G --> H[60 Gold Optimise]
    H --> I[70 Refresh Semantic Models]
    H --> J[71 ML Feature Build]
    G --> K{Critical tests pass?}
    K -- No --> L[Quarantine + Alert]
    K -- Yes --> H
```

## Suggested jobs
- Intraday POS / digital: streaming or 5–15 minute micro-batch.
- Tank / EV / solar telemetry: Event Hubs + Structured Streaming.
- Commercial / ERP: hourly or daily CDC.
- Supplier files: event-triggered Auto Loader.
- dbt marts: hourly for operational marts; daily for finance/executive snapshots.
- Power BI: Direct Lake where appropriate, otherwise scheduled refresh after Gold success.
