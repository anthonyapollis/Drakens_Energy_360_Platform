# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Bronze ingestion with Auto Loader
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC The batch feeds (forecourt POS, shop POS, ERP extracts, maintenance system)
# MAGIC arrive as files in a Unity Catalog volume. Auto Loader ingests them
# MAGIC incrementally.
# MAGIC
# MAGIC ## Why Auto Loader rather than a directory listing
# MAGIC
# MAGIC A nightly `spark.read.parquet(path)` re-reads everything and needs custom
# MAGIC bookkeeping to avoid double-counting. Auto Loader keeps its own file
# MAGIC notification state, so each file is processed exactly once even if the job
# MAGIC is restarted mid-run. At a few hundred files a day the difference is
# MAGIC convenience; at forecourt volumes it is the difference between a job that
# MAGIC finishes and one that does not.
# MAGIC
# MAGIC ## Schema evolution
# MAGIC
# MAGIC `addNewColumns` means a new upstream column lands in bronze rather than
# MAGIC failing the run, and `rescuedDataColumn` catches anything that does not fit
# MAGIC the inferred type instead of nulling it. Both are deliberate: bronze should
# MAGIC never lose data it was sent.

# COMMAND ----------

dbutils.widgets.text("catalog", "vivo_dev", "Unity Catalog")
dbutils.widgets.dropdown("mode", "batch", ["batch", "continuous"], "Trigger mode")

CATALOG = dbutils.widgets.get("catalog")
MODE = dbutils.widgets.get("mode")

from pyspark.sql import functions as F

LANDING = f"/Volumes/{CATALOG}/bronze/landing"
CHECKPOINTS = f"/Volumes/{CATALOG}/bronze/checkpoints"
SCHEMAS = f"/Volumes/{CATALOG}/bronze/schemas"

spark.sql(f"USE CATALOG {CATALOG}")


def current_run_id() -> str:
    """The job run id, or "interactive" outside a job.

    `spark.conf.get` raises on serverless for job-scoped keys even when a
    default is supplied, so this cannot be a one-liner with a fallback value.
    """
    try:
        return spark.conf.get("spark.databricks.job.runId")
    except Exception:                                        # noqa: BLE001
        return "interactive"


# COMMAND ----------

# MAGIC %md
# MAGIC ## Feed registry
# MAGIC
# MAGIC One entry per source feed. Keeping this as data means adding a feed is a
# MAGIC config change rather than a new copy-pasted notebook cell.

# COMMAND ----------

FEEDS = [
    {"name": "fact_retail_fuel_sales", "source": "SRC01", "format": "parquet",
     "path": "forecourt_pos", "partition": "date_key"},
    {"name": "fact_shop_sales", "source": "SRC02", "format": "parquet",
     "path": "shop_pos", "partition": "date_key"},
    {"name": "fact_commercial_orders", "source": "SRC07", "format": "parquet",
     "path": "erp_sales", "partition": None},
    {"name": "fact_general_ledger", "source": "SRC08", "format": "parquet",
     "path": "erp_finance", "partition": None},
    {"name": "fact_maintenance_work_orders", "source": "SRC12", "format": "parquet",
     "path": "maintenance", "partition": None},
]


def ingest(feed: dict):
    """Start (or run once) the Auto Loader stream for one feed."""
    name = feed["name"]
    src_path = f"{LANDING}/{feed['path']}"
    ckpt = f"{CHECKPOINTS}/{name}"
    schema_loc = f"{SCHEMAS}/{name}"

    reader = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", feed["format"])
        .option("cloudFiles.schemaLocation", schema_loc)
        # A new upstream column must land in bronze, not fail the run.
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        # Anything that does not fit the inferred type is preserved here
        # rather than silently nulled.
        .option("cloudFiles.rescuedDataColumn", "_rescued_data")
        # Bound each micro-batch so one enormous backfill cannot starve the
        # cluster or blow the driver.
        .option("cloudFiles.maxFilesPerTrigger", 200)
        .option("cloudFiles.inferColumnTypes", "true")
        .load(src_path)
    )

    enriched = (
        reader
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_source_file_modified", F.col("_metadata.file_modification_time"))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_system_code", F.lit(feed["source"]))
        .withColumn("_ingest_batch_id", F.lit(current_run_id()))
    )

    writer = (
        enriched.writeStream
        .format("delta")
        .outputMode("append")
        .option("checkpointLocation", ckpt)
        .option("mergeSchema", "true")
        .queryName(f"autoloader_{name}")
    )
    if feed["partition"]:
        writer = writer.partitionBy(feed["partition"])

    if MODE == "batch":
        # availableNow processes everything outstanding and stops. This is the
        # right trigger for a scheduled job: it gives streaming's exactly-once
        # bookkeeping without paying for an always-on cluster.
        writer = writer.trigger(availableNow=True)
    else:
        writer = writer.trigger(processingTime="1 minute")

    return writer.toTable(f"{CATALOG}.bronze.{name}")


# COMMAND ----------

# MAGIC %md
# MAGIC ## Run the feeds

# COMMAND ----------

import os

queries = []
for feed in FEEDS:
    src = f"{LANDING}/{feed['path']}"
    try:
        dbutils.fs.ls(src)
    except Exception:                                        # noqa: BLE001
        print(f"skip {feed['name']}: no files at {src}")
        continue
    q = ingest(feed)
    queries.append((feed["name"], q))
    print(f"started {feed['name']}")

if MODE == "batch":
    for name, q in queries:
        q.awaitTermination()
        prog = q.lastProgress
        rows = prog["numInputRows"] if prog else 0
        print(f"{name}: {rows:,} rows ingested")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ingestion audit
# MAGIC
# MAGIC Every bronze row carries the file it came from, so any figure in a board
# MAGIC pack can be traced back to a specific delivered file.

# COMMAND ----------

for feed in FEEDS:
    t = f"{CATALOG}.bronze.{feed['name']}"
    if not spark.catalog.tableExists(t):
        continue
    display(spark.sql(f"""
        SELECT '{feed['name']}' AS table_name,
               count(*) AS rows,
               count(DISTINCT _source_file) AS source_files,
               min(_ingested_at) AS first_ingested,
               max(_ingested_at) AS last_ingested,
               sum(CASE WHEN _rescued_data IS NOT NULL THEN 1 ELSE 0 END) AS rescued_rows
        FROM {t}
    """))
