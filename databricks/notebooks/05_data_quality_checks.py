# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - Data quality, freshness and reconciliation controls
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC Results are written to `${catalog}.platform` as tables rather than only
# MAGIC raised as job failures. That distinction matters: a control that only fails
# MAGIC a pipeline tells you today is broken. A control that is *stored* lets you
# MAGIC see that the rejection rate has been creeping up for three weeks, which is
# MAGIC the signal that actually prevents an incident.
# MAGIC
# MAGIC The notebook fails the task only on a **critical** breach, so a single
# MAGIC late feed does not block the whole warehouse from publishing.

# COMMAND ----------

dbutils.widgets.text("catalog", "drakens_dev", "Unity Catalog")
dbutils.widgets.dropdown("fail_on_critical", "true", ["true", "false"],
                         "Fail the task on a critical breach")

CATALOG = dbutils.widgets.get("catalog")
FAIL_ON_CRITICAL = dbutils.widgets.get("fail_on_critical") == "true"

from datetime import datetime

from pyspark.sql import functions as F

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


RUN_ID = current_run_id()
RUN_TS = datetime.utcnow()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Freshness against SLA
# MAGIC
# MAGIC The SLA per feed comes from reference data, not from a constant in this
# MAGIC notebook, so changing one is a data change rather than a deployment.

# COMMAND ----------

MONITORED = [
    # (table, event timestamp column, source code, SLA minutes)
    ("fact_retail_fuel_sales", "transaction_ts", "SRC01", 240),
    ("fact_shop_sales", "transaction_ts", "SRC02", 240),
    ("fact_inventory_snapshot", "snapshot_ts", "SRC03", 15),
    ("fact_ev_charging_sessions", "session_start_ts", "SRC05", 15),
    ("fact_solar_generation", "reading_ts", "SRC06", 15),
]

rows = []
for table, ts_col, source, sla in MONITORED:
    full = f"{CATALOG}.silver.{table}"
    if not spark.catalog.tableExists(full):
        continue
    agg = (spark.table(full)
           .agg(F.count("*").alias("row_count"),
                F.max(ts_col).alias("max_event_ts"),
                F.min(ts_col).alias("min_event_ts"),
                F.max("ingested_at").alias("max_ingested_at"))
           .collect()[0])
    lag = None
    if agg["max_event_ts"] and agg["max_ingested_at"]:
        lag = (agg["max_ingested_at"] - agg["max_event_ts"]).total_seconds() / 60
    rows.append((table, source, ts_col, int(agg["row_count"]),
                 agg["min_event_ts"], agg["max_event_ts"],
                 agg["max_ingested_at"], float(lag) if lag is not None else None,
                 sla))

freshness = spark.createDataFrame(rows, """
    table_name string, data_source_code string, watermark_column string,
    row_count long, min_event_ts timestamp, max_event_ts timestamp,
    max_ingested_at timestamp, ingestion_lag_minutes double, sla_minutes int
""")

# A backfill is not a late feed, and reporting it as one trains people to
# ignore the alert. If the newest event in a table is days old, the table was
# loaded historically: the lag measures how old the data is, not how slowly
# the pipeline ran. Only tables receiving recent events are held to an SLA.
BACKFILL_THRESHOLD_MINUTES = 24 * 60

freshness = (freshness
    .withColumn("is_backfill",
                F.col("ingestion_lag_minutes") > BACKFILL_THRESHOLD_MINUTES)
    .withColumn("is_sla_breached",
                (~F.col("is_backfill"))
                & (F.col("ingestion_lag_minutes") > F.col("sla_minutes")))
    .withColumn("sla_status",
        F.when(F.col("ingestion_lag_minutes").isNull(), "Unknown")
         .when(F.col("is_backfill"), "Backfill")
         .when(F.col("ingestion_lag_minutes") <= F.col("sla_minutes"), "Within SLA")
         .when(F.col("ingestion_lag_minutes") <= F.col("sla_minutes") * 2, "Degraded")
         .otherwise("Breached"))
    .withColumn("run_id", F.lit(RUN_ID))
    .withColumn("evaluated_at", F.lit(RUN_TS).cast("timestamp")))

(freshness.write.format("delta").mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(f"{CATALOG}.platform.obs_table_freshness"))

display(freshness.select("table_name", "row_count", "ingestion_lag_minutes",
                         "sla_minutes", "is_backfill", "sla_status"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Reconciliation controls
# MAGIC
# MAGIC Each control states its own tolerance, so tightening a threshold is a
# MAGIC reviewable change with a reason attached rather than a number someone
# MAGIC edited in passing.

# COMMAND ----------

CONTROLS = [
    ("RETAIL_MARGIN_RECONCILES", "Finance",
     "Retail fuel gross margin equals revenue less cost of sales", 0.01,
     f"""SELECT sum(gross_sales_zar) - sum(cogs_zar) AS expected,
                sum(gross_margin_zar) AS actual
         FROM {CATALOG}.gold.fct_retail_fuel_sales"""),

    ("RETAIL_VOLUME_TIES_TO_DAILY_AGG", "Supply",
     "Transaction-level litres tie to the site-day aggregate", 0.001,
     f"""SELECT (SELECT sum(litres) FROM {CATALOG}.gold.fct_retail_fuel_sales) AS expected,
                (SELECT sum(litres) FROM {CATALOG}.gold.agg_site_daily_fuel) AS actual"""),

    ("SILVER_TIES_TO_GOLD", "Data Platform",
     "No rows lost between the silver and gold retail fact", 0.0,
     f"""SELECT (SELECT count(*) FROM {CATALOG}.silver.fact_retail_fuel_sales) AS expected,
                (SELECT count(*) FROM {CATALOG}.gold.fct_retail_fuel_sales) AS actual"""),

    ("ALL_SITES_RESOLVE", "Data Platform",
     "Every fact row resolves to a site in the conformed dimension", 0.0,
     f"""SELECT count(*) AS expected,
                sum(CASE WHEN site_key IS NOT NULL THEN 1 ELSE 0 END) AS actual
         FROM {CATALOG}.gold.fct_retail_fuel_sales"""),

    ("NINE_PROVINCES_PRESENT", "Data Platform",
     "All nine South African provinces are represented", 0.0,
     f"""SELECT 9 AS expected,
                count(DISTINCT province) AS actual
         FROM {CATALOG}.gold.dim_site
         WHERE country_code = 'ZA' AND province IS NOT NULL"""),

    ("SOLAR_NOT_GENERATING_AT_NIGHT", "Data Platform",
     "No solar reading generates power outside daylight", 0.0,
     f"""SELECT 0 AS expected,
                sum(CASE WHEN NOT is_daylight AND energy_kwh > 0 THEN 1 ELSE 0 END) AS actual
         FROM {CATALOG}.silver.fact_solar_generation"""),
]

control_rows = []
for code, owner, description, tolerance, sql in CONTROLS:
    try:
        r = spark.sql(sql).collect()[0]
        expected = float(r["expected"] or 0)
        actual = float(r["actual"] or 0)
        variance_pct = (abs(actual - expected) / abs(expected) * 100
                        if expected else (0.0 if actual == 0 else 100.0))
        passing = variance_pct <= tolerance
        control_rows.append((code, owner, description, expected, actual,
                             actual - expected, variance_pct, tolerance,
                             passing, None))
    except Exception as exc:                                 # noqa: BLE001
        # A control that cannot be evaluated is not a passing control.
        control_rows.append((code, owner, description, None, None, None,
                             None, tolerance, False, str(exc)[:400]))

controls = spark.createDataFrame(control_rows, """
    control_code string, control_owner string, control_description string,
    expected_value double, actual_value double, variance_absolute double,
    variance_pct double, tolerance_pct double, is_passing boolean,
    error_message string
""").withColumn("run_id", F.lit(RUN_ID)) \
    .withColumn("evaluated_at", F.lit(RUN_TS).cast("timestamp"))

(controls.write.format("delta").mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(f"{CATALOG}.platform.obs_reconciliation_controls"))

display(controls.select("control_code", "control_owner", "expected_value",
                        "actual_value", "variance_pct", "tolerance_pct",
                        "is_passing"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Column-level profiling
# MAGIC
# MAGIC Null rates and cardinality on the columns that matter. Trended over time
# MAGIC this catches the silent kind of upstream change: a field that starts
# MAGIC arriving empty does not break anything, it just quietly hollows out a
# MAGIC dashboard.

# COMMAND ----------

PROFILE = {
    "gold.fct_retail_fuel_sales": ["site_key", "product_key", "litres",
                                   "gross_sales_zar", "payment_method",
                                   "loyalty_member_id"],
    "gold.dim_site": ["province", "site_type", "ownership_model", "demand_band"],
    "gold.dim_customer": ["sector", "segment", "credit_band"],
}

profile_rows = []
for table, columns in PROFILE.items():
    full = f"{CATALOG}.{table}"
    if not spark.catalog.tableExists(full):
        continue
    df = spark.table(full)
    total = df.count()
    for col in columns:
        if col not in df.columns:
            continue
        stats = df.agg(
            F.sum(F.when(F.col(col).isNull(), 1).otherwise(0)).alias("nulls"),
            F.approx_count_distinct(col).alias("distinct_values"),
        ).collect()[0]
        nulls = int(stats["nulls"] or 0)
        profile_rows.append((
            table, col, total, nulls,
            round(nulls / total * 100, 4) if total else 0.0,
            int(stats["distinct_values"] or 0),
        ))

if profile_rows:
    profile = spark.createDataFrame(profile_rows, """
        table_name string, column_name string, row_count long,
        null_count long, null_pct double, distinct_values long
    """).withColumn("run_id", F.lit(RUN_ID)) \
        .withColumn("evaluated_at", F.lit(RUN_TS).cast("timestamp"))

    (profile.write.format("delta").mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(f"{CATALOG}.platform.obs_column_profile"))
    display(profile)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verdict

# COMMAND ----------

failed_controls = [r for r in control_rows if not r[8]]
breached = freshness.filter("sla_status = 'Breached'").count()
degraded = freshness.filter("sla_status = 'Degraded'").count()
backfilled = freshness.filter("sla_status = 'Backfill'").count()

print(f"controls:  {len(control_rows) - len(failed_controls)}/"
      f"{len(control_rows)} passing")
print(f"freshness: {breached} breached, {degraded} degraded, "
      f"{backfilled} historical backfill (SLA not applied)")

if failed_controls:
    print("\nFAILING CONTROLS")
    for r in failed_controls:
        detail = r[9] or f"expected {r[3]:,.2f}, actual {r[4]:,.2f}"
        print(f"  {r[0]:<34} ({r[1]}) -- {detail}")

# A failing reconciliation control means a published number is wrong, which is
# worse than a late number. A breached freshness SLA on its own is not fatal:
# the warehouse still publishes, and the on-call engineer is told.
if FAIL_ON_CRITICAL and failed_controls:
    raise Exception(
        f"{len(failed_controls)} reconciliation control(s) failed: "
        f"{', '.join(r[0] for r in failed_controls)}")

print("\ndata quality checks complete")
