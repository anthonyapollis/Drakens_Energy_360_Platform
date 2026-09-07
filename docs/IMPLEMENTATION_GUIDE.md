# Implementation guide

> **Independent synthetic portfolio project.** This repository contains no
> internal Vivo Energy, Engen, Shell or Vitol data. Every site, customer,
> employee, asset, coordinate, price, volume, margin and incident is randomly
> generated. See [public_reference_notes.md](public_reference_notes.md).

This guide takes the platform from an empty machine to a working warehouse,
then to a Databricks deployment, then to a demo. Each stage stands alone: you
can stop after stage 2 and have a complete, queryable 37-million-row
warehouse without a cloud account.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Build the warehouse locally](#2-build-the-warehouse-locally)
3. [Deploy to Databricks](#3-deploy-to-databricks)
4. [Provision the Azure platform](#4-provision-the-azure-platform)
5. [Train the models](#5-train-the-models)
6. [Run the investment engine](#6-run-the-investment-engine)
7. [Connect Power BI](#7-connect-power-bi)
8. [Demo script](#8-demo-script)
9. [Operating the platform](#9-operating-the-platform)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. What you need

**For the local build (stages 2, 5, 6):**

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.11 or 3.12 |
| Disk | 6 GB free | 1.5 GB lake, ~3 GB DuckDB warehouse |
| RAM | 8 GB | The generator is memory-bounded by design |
| Time | ~40 minutes | 20 min generate, 20 min dbt |

**Additionally for Databricks (stage 3):** a Databricks workspace. The free
edition is enough — the whole medallion has been run on one.

**Additionally for Azure (stage 4):** a subscription, plus Terraform 1.6+ or
the Azure CLI with the Bicep extension.

```bash
git clone <this-repo> && cd Vivo_Energy_360_Platform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. Build the warehouse locally

### 2.1 Generate the landing zone

```bash
PYTHONPATH=src python -m vivo360.build \
  --profile portfolio \
  --output data/lake \
  --defects realistic
```

Four scale profiles are available:

| Profile | Fact rows | Time | Use |
|---|---:|---:|---|
| `dev` | 489,190 | ~20 s | Fast iteration |
| `test` | 1,928,620 | ~1 min | What CI runs |
| `portfolio` | **37,202,000** | ~20 min | The default deliverable |
| `enterprise` | 263,449,000 | ~2.5 h | Stress profile |

Three defect profiles control how damaged the landing zone is:

| Profile | Purpose |
|---|---|
| `clean` | No defects. Useful as a baseline when testing the cleansing layer. |
| `realistic` | The default. ~63 million defects across the portfolio build. |
| `severe` | Deliberately hostile, for testing that cleansing holds up. |

The build prints a defect inventory and writes it to
`data/lake/_manifest.json`. That inventory is what makes the cleansing layer
measurable rather than merely asserted.

### 2.2 Regenerate the cleansing layer

The cleansing layer is generated from the manifest so it always matches what
the generator actually wrote: 167 repair-and-assess models, 167 staging models
and 128 quarantine models.

```bash
python scripts/generate_dbt_staging.py --manifest data/lake/_manifest.json
```

The layer is split in three because the repair work is expensive and must be
done once: `cln_` repairs every column and assesses every row, `stg_` takes
the valid rows and deduplicates, and `qtn_` keeps the rejected ones with their
failing rules.

Only necessary after changing the data model. CI fails if the committed models
have drifted from what this produces.

### 2.3 Run dbt

```bash
cd dbt
export DBT_PROFILES_DIR=$PWD
export VIVO_LAKE=$(cd .. && pwd)/data/lake
export VIVO_DUCKDB_PATH=$(cd .. && pwd)/data/vivo360.duckdb

dbt deps
dbt build
```

`dbt build` runs models, tests, snapshots and seeds in dependency order and
stops at the first failure with `--fail-fast`. Expect roughly 800 nodes.

### 2.4 Verify

```bash
pytest tests/ -v
```

`tests/test_generator.py` runs without a warehouse; `tests/test_warehouse.py`
skips itself unless one exists.

The single most important check is that every landed row is accounted for:

```sql
SELECT table_name, raw_rows, cleansed_rows, quarantined_rows, duplicates_removed
FROM main_platform.obs_cleansing_summary
WHERE raw_rows <> cleansed_rows + quarantined_rows + duplicates_removed;
-- must return zero rows
```

---

## 3. Deploy to Databricks

### 3.1 Authenticate

```bash
databricks auth login --profile my-workspace
```

OAuth, through the browser. No token is written into the repository, and none
of the scripts here ever read one.

### 3.2 Deploy

```bash
python scripts/deploy_databricks.py \
  --profile my-workspace \
  --env dev \
  --scale portfolio \
  --run
```

This creates the `vivo_dev` catalog and its seven schemas, uploads the
notebooks, creates the `vivo360_medallion_dev` job and triggers it. Add
`--wait` to block until it finishes.

### 3.3 What runs

| Task | Notebook | What it does |
|---|---|---|
| `generate_bronze` | `00_generate_bronze_at_scale` | Generates 5m retail rows natively in Spark |
| `build_silver` | `02_silver_conformance` | Contract, quarantine, dedup, SCD2 merge |
| `build_gold` | `03_gold_star_schema` | Dimensional marts and aggregates |
| `data_quality` | `05_data_quality_checks` | Controls and freshness |
| `optimize_tables` | `06_optimize_and_vacuum` | OPTIMIZE, VACUUM, clustering |

Bronze is generated *in-platform* rather than uploaded. Pushing 37 million rows
over a domestic connection takes hours; Spark produces the same distributions
on the cluster in minutes. `01_bronze_autoloader` demonstrates the incremental
file-ingestion path for the same tables, and `04_streaming_telemetry` the
real-time feeds.

### 3.4 Apply governance

```bash
databricks sql -f databricks/sql/02_governance.sql --var env=dev
```

Grants, column masks and row filters. Requires Unity Catalog and, for masks
and filters, a Premium workspace.

### 3.5 Point dbt at Databricks

```bash
export DATABRICKS_HOST=https://adb-xxxx.azuredatabricks.net
export DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/xxxx
cd dbt && dbt build --target dev
```

The models are unchanged. Cross-adapter differences — `current_timestamp` vs
`current_timestamp()`, merge strategy, liquid clustering — are handled in
`macros/vivo_helpers.sql`.

---

## 4. Provision the Azure platform

### Terraform (reference implementation)

```bash
cd infra/terraform
terraform init
terraform workspace new dev && terraform workspace select dev
terraform plan  -var-file=env/dev.tfvars
terraform apply -var-file=env/dev.tfvars
```

### Bicep (ARM-native alternative)

```bash
az deployment sub create \
  --location southafricanorth \
  --template-file infra/bicep/main.bicep \
  --parameters infra/bicep/env/dev.bicepparam
```

Terraform is the reference because it also manages the Databricks workspace
objects — Unity Catalog, cluster policies, jobs — which Bicep cannot reach.

### What differs between environments

| | dev | test | prod |
|---|---|---|---|
| Storage replication | LRS | LRS | ZRS |
| Databricks SKU | standard | standard | premium |
| Compute | spot | spot | on-demand |
| Max workers | 4 | 8 | 16 |
| Streaming job | off | on | on |
| Bronze retention | 90 days | 1 year | 7 years |
| Monthly budget | R8,000 | R30,000 | R180,000 |

Streaming is off in dev deliberately: an always-on stream in a development
workspace is the most reliable way to produce a surprising invoice.

---

## 5. Train the models

```bash
export VIVO_DUCKDB_PATH=$PWD/data/vivo360.duckdb

python ml/experiments/demand_forecast.py
python ml/experiments/predictive_maintenance.py
python ml/experiments/customer_churn.py
python ml/experiments/stock_out_risk.py
python ml/experiments/late_delivery.py
python ml/experiments/fraud_anomaly.py

mlflow ui --backend-store-uri file://$PWD/mlruns
```

Every experiment splits chronologically rather than randomly, excludes any
feature unknown at prediction time, and reports a baseline it must beat. The
demand forecast prints a warning if it fails to beat a seasonal-naive
baseline, because a model that cannot do that should not be promoted.

To run on Databricks, change `mlflow.set_tracking_uri` in `ml/common.py` to
`"databricks"` and point `load()` at the SQL warehouse. The experiment code
itself does not change.

---

## 6. Run the investment engine

```bash
python ml/network_investment_engine.py --budget-zar 1500000000
```

Allocates a fixed capital budget across the network as an exact bounded
knapsack, subject to a minimum number of funded projects per province.
Writes a per-site plan to `data/network_investment_plan.csv` with the reason
for every decision.

Useful arguments:

```bash
--budget-zar 800000000       # a tighter budget
--min-per-province 5         # a stronger coverage floor
```

Running it at several budgets and plotting return against spend is the most
useful single output for a capital committee: it shows where the marginal
rand stops earning.

---

## 7. Connect Power BI

1. **Get data → Azure Databricks**, server hostname and HTTP path from the SQL
   warehouse.
2. Catalog `vivo_prod`, schema `gold`.
3. Set storage mode per table as in
   [powerbi/semantic_model.md](../powerbi/semantic_model.md) — Import for the
   aggregates, DirectQuery for the transaction fact.
4. Mark `dim_date` as the date table on `full_date`. Time intelligence returns
   wrong answers at period boundaries without this.
5. Create the measures from [powerbi/dax_measures.md](../powerbi/dax_measures.md).
6. Configure the `Regional Analyst` and `Executive` roles.
7. Register `agg_site_daily_fuel` as a user-defined aggregation over
   `fct_retail_fuel_sales`.

Step 7 is what makes a 5-million-row model feel small: a query grouped by
month and province is answered from the aggregate, and only a query that
slices by something not in the aggregate falls through to DirectQuery.

---

## 8. Demo script

Fifteen minutes, in the order that makes the argument.

**1. The problem (1 min).** Open `data/lake/_manifest.json`. 37 million fact
rows landed, 63 million defects in them. Numbers arriving as `"1 234,56"`,
codes as `" s000123 "`, sentinels standing in for NULL, replayed batches.

**2. The cleansing (3 min).**

```sql
SELECT * FROM main_platform.obs_cleansing_summary ORDER BY raw_rows DESC;
SELECT * FROM main_platform.obs_quarantine_reasons ORDER BY failure_count DESC LIMIT 10;
```

Every row is accounted for. Nothing was dropped; rejected rows are in
`main_quarantine` with the rule that rejected them.

**3. The model (2 min).** `docs/erd/`. 70 conformed dimensions, 85
facts, one bus matrix. Conformed dimensions are the point: `dim_site` joins
retail, supply, maintenance and safety, so the same site means the same thing
in every domain.

**4. Databricks (3 min).** Show the job run: bronze → silver → gold at 5
million rows. Show the Unity Catalog lineage graph. Run the row filter as two
different users and show a regional analyst seeing only their provinces.

**5. The decision engine (4 min).** This is the part a CEO cares about.

```sql
SELECT investment_recommendation, count(*), round(avg(investment_score),1),
       round(sum(total_margin_zar)/1e6,1) AS margin_m
FROM main_gold.network_investment_scorecard GROUP BY 1 ORDER BY 3 DESC;
```

Then `python ml/network_investment_engine.py --budget-zar 1500000000`. Every
score component is a visible column, so a challenge to any recommendation can
be answered with the inputs rather than with "the model said so".

**6. Trust (2 min).**

```sql
SELECT * FROM main_platform.obs_reconciliation_controls;
SELECT * FROM main_platform.obs_table_freshness WHERE is_sla_breached;
```

Then `pytest tests/ -v` and the dbt run summary. The controls are data, not
just tests, because a failing control needs to be trended on a dashboard, not
only to fail a pipeline run.

---

## 9. Operating the platform

### Daily

The `vivo360_medallion_prod` job runs at 03:00 SAST, ahead of the 06:00
dashboard refresh. On failure it emails the on-call address. There is no
success notification: an alert that fires every day is an alert nobody reads
by the second week.

### Table maintenance

`06_optimize_and_vacuum` runs after the quality checks, not before —
OPTIMIZE on a table that failed its checks just rewrites bad data more
efficiently.

| Table | Action | Frequency |
|---|---|---|
| `fct_retail_fuel_sales` | OPTIMIZE + liquid clustering on `(site_id, product_id)` | Daily |
| `bronze.*` | OPTIMIZE only | Weekly |
| All Delta tables | VACUUM, 7-day retention | Weekly |

Do not shorten VACUUM retention below 7 days: it breaks time travel and any
concurrent reader still holding an older snapshot.

### Cost control

The cluster policy caps node type and worker count and forces autotermination
between 10 and 60 minutes. Spot instances everywhere except prod, where an
eviction mid-job costs more in delay than the discount saves. Budget alerts
fire at 50%, 80% and 100% of actual spend and at 100% of forecast.

The largest single saving is bronze lifecycle management: cool after 90 days,
archive after a year. Bronze is the biggest thing on the platform and is
almost never re-read once silver is built.

### When something breaks

1. `obs_table_freshness` — which feed is late?
2. `obs_cleansing_summary` — did the rejection rate move?
3. `obs_quarantine_reasons` — which rule started failing?
4. `main_quarantine.qtn_<table>` — the actual rejected rows.

A rejection rate that suddenly moves is the earliest signal that an upstream
system changed, and it usually shows up days before anyone notices a number
looks wrong in a report.

---

## 10. Troubleshooting

**`Catalog "vivo_dev" does not exist`** on a local dbt run — a model or
snapshot is hard-coding a Databricks catalog. The catalog must come from the
profile target. Check for a stray `database:` in a source or snapshot config.

**dbt tests take minutes each** — the `cleansed` layer has reverted to views,
or `stg_`/`qtn_` are reading the raw source rather than `cln_`. The repair
expressions are expensive and must be materialised once, with everything
downstream reading the materialised result.

**`CONFIG_NOT_AVAILABLE` on Databricks** — serverless manages Spark configs
and rejects setting them. The notebooks wrap `spark.conf.set` in try/except
for exactly this.

**`COLUMN_ALREADY_EXISTS` in the gold notebook** — the bronze generator
denormalises some site attributes onto the fact. Use the `join_dim` helper,
which drops the fact's copies before joining the dimension.

**Ratios are wrong but individually plausible** — check macro argument
parenthesisation. `safe_divide('a - b', 'c')` without parentheses compiles to
`a - (b / c)`, which produces a wrong answer rather than an error. This
actually happened here and was caught by a range test on
`dim_product.base_margin_pct`.

**The general ledger does not balance** — journal lines must be emitted as
double-entry pairs. `obs_reconciliation_controls` catches this; it caught it
here.

**Out of disk** — the portfolio lake is 1.5 GB and the DuckDB warehouse
roughly 3 GB. Use `--profile test` for a build about twenty times smaller.
