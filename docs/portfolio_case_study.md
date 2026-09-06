
# Portfolio case study

## Business problem
A geographically distributed downstream-energy operator needs a single governed platform across fuel sourcing, terminals, transport, forecourts, convenience, commercial accounts, specialist products and emerging-energy services.

## Solution
I designed a Databricks Lakehouse with a medallion architecture, domain-oriented Gold marts and a Kimball conformed-dimension layer.

## Key engineering decisions
1. Bronze preserves source fidelity.
2. Silver standardises units, timestamps, master keys and data quality.
3. Gold is modelled by business process, not source application.
4. High-volume telemetry is streamed; ERP/master data is CDC/batch.
5. dbt provides modular transformations, tests, documentation and lineage.
6. Unity Catalog provides central governance.
7. Power BI consumes semantic-ready facts and dimensions.
8. ML use cases consume governed Silver/Gold features.

## Scale
The portfolio profile generates more than 15 million fact records across 16 business processes, including approximately 1,050 synthetic South African sites across all provinces.

## Demonstrable interview talking points
- Why a bus matrix matters
- How to handle late-arriving dimensions
- SCD2 site/customer/product changes
- Delta MERGE and idempotency
- Small-file mitigation
- Liquid clustering / optimisation strategy
- CDC vs event streaming
- PII masking
- country-level RLS
- dbt tests and CI gates
- operational vs finance refresh SLAs
- how ML features avoid leakage
