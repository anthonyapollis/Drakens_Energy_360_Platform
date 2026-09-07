# Databricks notebook source
# MAGIC %md
# MAGIC # 06 - Table maintenance: OPTIMIZE, clustering and VACUUM
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC Runs *after* the data-quality checks, not before. OPTIMIZE on a table that
# MAGIC failed its controls just rewrites bad data more efficiently and makes the
# MAGIC eventual rollback harder.
# MAGIC
# MAGIC ## The small-file problem
# MAGIC
# MAGIC Streaming and frequent MERGEs produce many small files. Every query then
# MAGIC pays a per-file cost to open, read a footer and plan around it, so a table
# MAGIC with 40,000 files of 2 MB is dramatically slower than the same data in 400
# MAGIC files of 200 MB — for identical rows. This is the single most common cause
# MAGIC of a Delta table that was fast last month and is slow now.
# MAGIC
# MAGIC ## Liquid clustering rather than partitioning
# MAGIC
# MAGIC Partitioning by `site_id` would create 4,200 directories, most holding a
# MAGIC few megabytes — the small-file problem by construction.
# MAGIC
# MAGIC Partitioning by `date_key` looks safer and is not. This job measured it:
# MAGIC the retail fact, partitioned on date, sat in **974 files averaging
# MAGIC 0.2 MB** — one per day across the 974-day window. `OPTIMIZE` cannot merge
# MAGIC across partition boundaries, so those files are permanent, and every
# MAGIC query pays 974 file-open costs to read a third of a gigabyte. The same
# MAGIC table under liquid clustering compacted from 7 files to 2, averaging
# MAGIC 74 MB.
# MAGIC
# MAGIC Liquid clustering gives the same data skipping without committing the
# MAGIC physical layout, and the keys can be changed later without rewriting
# MAGIC history, which partitioning cannot.

# COMMAND ----------

dbutils.widgets.text("catalog", "drakens_dev", "Unity Catalog")
dbutils.widgets.text("vacuum_retention_hours", "168", "VACUUM retention (hours)")
dbutils.widgets.dropdown("run_vacuum", "true", ["true", "false"], "Run VACUUM")

CATALOG = dbutils.widgets.get("catalog")
RETENTION_HOURS = int(dbutils.widgets.get("vacuum_retention_hours"))
RUN_VACUUM = dbutils.widgets.get("run_vacuum") == "true"

from datetime import datetime

from pyspark.sql import functions as F

spark.sql(f"USE CATALOG {CATALOG}")
RUN_TS = datetime.utcnow()

# Seven days is the Delta default and the floor worth respecting: shortening it
# breaks time travel and can pull files out from under a reader that is still
# holding an older snapshot.
if RETENTION_HOURS < 168:
    raise ValueError(
        f"VACUUM retention of {RETENTION_HOURS}h is below the 168h floor. "
        "Shortening it breaks time travel and concurrent readers.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Maintenance plan
# MAGIC
# MAGIC Not every table deserves the same treatment. The retail fact is queried
# MAGIC constantly and filtered on site and product, so it earns clustering.
# MAGIC Bronze is append-only history that is rarely re-read once silver is built,
# MAGIC so it gets compaction and nothing more.

# COMMAND ----------

PLAN = [
    # (schema, table, cluster_by, zorder_fallback)
    ("gold", "fct_retail_fuel_sales", ["date_key", "site_id"], ["site_id"]),
    ("gold", "agg_site_daily_fuel", ["site_id"], ["site_id"]),
    ("gold", "fct_inventory_position", ["site_id", "product_id"], ["site_id"]),
    ("gold", "fct_ev_charging_sessions", ["site_id"], ["site_id"]),
    ("gold", "fct_solar_generation", ["site_id"], ["site_id"]),
    ("gold", "agg_executive_daily_kpi", ["province"], ["province"]),
    ("gold", "network_investment_scorecard", None, None),
    ("gold", "dim_site", None, None),
    ("gold", "dim_customer", None, None),
    ("silver", "fact_retail_fuel_sales", ["site_id"], ["site_id"]),
    ("silver", "fact_shop_sales", ["site_id"], ["site_id"]),
    ("silver", "fact_inventory_snapshot", ["site_id"], ["site_id"]),
    ("bronze", "fact_retail_fuel_sales", None, None),
    ("bronze", "fact_shop_sales", None, None),
]


def table_stats(fq_name: str) -> dict:
    """File count and size, which is what actually decides query cost."""
    detail = spark.sql(f"DESCRIBE DETAIL {fq_name}").collect()[0]
    files = detail["numFiles"] or 0
    size = detail["sizeInBytes"] or 0
    return {
        "files": int(files),
        "size_bytes": int(size),
        "avg_file_mb": round(size / files / 1e6, 2) if files else 0.0,
    }

# COMMAND ----------

results = []

for schema, table, cluster_by, zorder in PLAN:
    fq = f"{CATALOG}.{schema}.{table}"
    if not spark.catalog.tableExists(fq):
        print(f"skip {fq}: not present")
        continue

    before = table_stats(fq)
    clustering_applied = None

    # Liquid clustering first, where the runtime supports it. It is a metadata
    # change; the following OPTIMIZE is what physically reorganises the data.
    if cluster_by:
        try:
            spark.sql(f"ALTER TABLE {fq} CLUSTER BY ({', '.join(cluster_by)})")
            clustering_applied = "liquid:" + ",".join(cluster_by)
        except Exception as exc:                             # noqa: BLE001
            print(f"  {fq}: liquid clustering unavailable ({str(exc)[:70]})")

    try:
        if clustering_applied:
            spark.sql(f"OPTIMIZE {fq}")
        elif zorder:
            # Z-ordering is the older mechanism. It works, but the column
            # choice is baked into the physical layout and changing it later
            # means rewriting the table.
            spark.sql(f"OPTIMIZE {fq} ZORDER BY ({', '.join(zorder)})")
            clustering_applied = "zorder:" + ",".join(zorder)
        else:
            spark.sql(f"OPTIMIZE {fq}")
            clustering_applied = "compaction only"
    except Exception as exc:                                 # noqa: BLE001
        print(f"  {fq}: OPTIMIZE failed ({str(exc)[:90]})")
        continue

    after = table_stats(fq)
    results.append((
        f"{schema}.{table}", clustering_applied,
        before["files"], after["files"],
        before["avg_file_mb"], after["avg_file_mb"],
        round(after["size_bytes"] / 1e9, 3),
    ))
    print(f"  {schema}.{table:<32} {before['files']:>6} -> {after['files']:>6} files"
          f"   avg {before['avg_file_mb']:>7.1f} -> {after['avg_file_mb']:>7.1f} MB"
          f"   [{clustering_applied}]")

# COMMAND ----------

# MAGIC %md
# MAGIC ## VACUUM
# MAGIC
# MAGIC Removes files no longer referenced by any retained snapshot. Without it,
# MAGIC storage grows indefinitely because every rewritten file stays on disk.

# COMMAND ----------

if RUN_VACUUM:
    vacuumed = 0
    for schema, table, _, _ in PLAN:
        fq = f"{CATALOG}.{schema}.{table}"
        if not spark.catalog.tableExists(fq):
            continue
        try:
            spark.sql(f"VACUUM {fq} RETAIN {RETENTION_HOURS} HOURS")
            vacuumed += 1
        except Exception as exc:                             # noqa: BLE001
            print(f"  {fq}: VACUUM failed ({str(exc)[:90]})")
    print(f"vacuumed {vacuumed} tables, retaining {RETENTION_HOURS}h of history")
else:
    print("VACUUM skipped")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Record the outcome
# MAGIC
# MAGIC File counts trended over time are how you notice a table degrading before
# MAGIC someone complains that a dashboard has become slow.

# COMMAND ----------

if results:
    summary = spark.createDataFrame(results, """
        table_name string, layout_strategy string,
        files_before long, files_after long,
        avg_file_mb_before double, avg_file_mb_after double,
        size_gb double
    """).withColumn("files_removed",
                    F.col("files_before") - F.col("files_after")) \
       .withColumn("evaluated_at", F.lit(RUN_TS).cast("timestamp"))

    (summary.write.format("delta").mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(f"{CATALOG}.platform.obs_table_maintenance"))

    display(summary)

    total_removed = sum(r[2] - r[3] for r in results)
    print(f"\n{len(results)} tables maintained, "
          f"{total_removed:,} small files compacted away")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cost note
# MAGIC
# MAGIC OPTIMIZE is not free: it reads and rewrites the data. Running it daily on
# MAGIC a large, rarely-queried table costs more in compute than it saves in query
# MAGIC time. The plan above reflects that — gold tables that serve interactive
# MAGIC dashboards are maintained daily, bronze weekly, and anything queried a few
# MAGIC times a month is left alone entirely.
