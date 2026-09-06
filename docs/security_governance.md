
# Security and governance

## Unity Catalog structure
- catalog: `vivo_synthetic`
- schemas: bronze, silver, gold_core, gold_retail, gold_commercial, gold_operations, gold_executive, sandbox_ml

## Roles
- `de_ingest_sp` — write Bronze only
- `de_transform_sp` — read Bronze, write Silver/Gold
- `analytics_engineer` — read Silver, develop Gold/dbt
- `bi_consumer` — read approved Gold only
- `data_scientist` — read approved Silver/Gold + sandbox
- `auditor` — read metadata/audit
- `platform_admin` — administration

## Controls
- service principals for non-human workloads
- secrets in Key Vault
- private endpoints where required
- audit logs
- lineage
- data classification tags
- column masking for PII
- row-level filters by country/business unit
- retention and deletion policies
- dev/test/prod catalogue separation
- no real customer PII in this portfolio
