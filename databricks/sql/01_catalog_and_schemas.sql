-- =====================================================================
-- Drakens Energy 360 - Unity Catalog structure
--
-- Independent synthetic portfolio project. no data from any real company is present in any object created here.
--
-- One catalog per environment gives a hard isolation boundary: a dev job
-- physically cannot write to prod, because the grant does not exist. The
-- schema names are identical across environments so the same dbt models and
-- notebooks run unchanged, parameterised only by catalog.
--
-- Usage:  set the ${env} parameter to dev | test | prod
-- =====================================================================

CREATE CATALOG IF NOT EXISTS drakens_${env}
COMMENT 'Drakens Energy 360 synthetic downstream-energy platform - ${env}. Independent portfolio project; contains no real company data.';

USE CATALOG drakens_${env};

-- ---------------------------------------------------------------- bronze
CREATE SCHEMA IF NOT EXISTS bronze
COMMENT 'Raw landing zone. Append-only, schema-on-read, no business logic. Every record keeps its source file and ingestion timestamp so any downstream number can be traced back to the file it came from.';

-- ---------------------------------------------------------------- silver
CREATE SCHEMA IF NOT EXISTS silver
COMMENT 'Cleaned, typed, deduplicated and conformed. One row per business event. This is the layer analysts are granted by default.';

CREATE SCHEMA IF NOT EXISTS silver_snapshots
COMMENT 'dbt Type-2 snapshots of the slowly changing dimensions.';

-- ------------------------------------------------------------------ gold
CREATE SCHEMA IF NOT EXISTS gold
COMMENT 'Dimensional marts and aggregates serving Power BI and the ML feature sets.';

-- -------------------------------------------------------------- platform
CREATE SCHEMA IF NOT EXISTS platform
COMMENT 'Operational metadata: pipeline run log, data-quality results, freshness against SLA, reconciliation controls.';

CREATE SCHEMA IF NOT EXISTS ml
COMMENT 'Feature tables, model inputs and scored outputs.';

-- --------------------------------------------------------------- volumes
-- Managed volumes hold the raw landed files that Auto Loader watches.
CREATE VOLUME IF NOT EXISTS bronze.landing
COMMENT 'Auto Loader source. Batch extracts land here as Parquet/CSV under one directory per source system.';

CREATE VOLUME IF NOT EXISTS bronze.checkpoints
COMMENT 'Structured Streaming checkpoint location. Never delete while a stream is running: the offsets here are what make ingestion exactly-once.';

CREATE VOLUME IF NOT EXISTS bronze.quarantine
COMMENT 'Records rejected by the bronze contract. Quarantined rather than dropped, so a schema break is investigable instead of silently lost.';

CREATE VOLUME IF NOT EXISTS ml.artifacts
COMMENT 'Model artefacts and evaluation plots not held in MLflow.';
