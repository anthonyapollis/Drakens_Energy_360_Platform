# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Silver conformance
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC Bronze is whatever the source system sent. Silver is what the business
# MAGIC agreed a record means. This notebook does four things and nothing else:
# MAGIC
# MAGIC 1. **Type and constrain** - explicit casts and Delta CHECK constraints, so a
# MAGIC    bad value fails at write time rather than surfacing in a board pack.
# MAGIC 2. **Deduplicate** - source systems replay. Dedup is on the business key,
# MAGIC    keeping the latest `ingested_at`.
# MAGIC 3. **Quarantine** - records failing the contract are written aside, not
# MAGIC    dropped. A silently dropped row is an unexplainable variance later.
# MAGIC 4. **SCD2 merge** - dimension history via `MERGE`, so a historical fact
# MAGIC    still joins to the attributes that were true at the time.

# COMMAND ----------

dbutils.widgets.text("catalog", "drakens_dev", "Unity Catalog")
CATALOG = dbutils.widgets.get("catalog")

from pyspark.sql import functions as F
from pyspark.sql import Window
from delta.tables import DeltaTable

spark.sql(f"USE CATALOG {CATALOG}")

# Serverless manages these and reports them read-only; classic compute needs
# them set. Best-effort either way.
for key, value in [
    ("spark.databricks.delta.optimizeWrite.enabled", "true"),
    ("spark.databricks.delta.autoCompact.enabled", "true"),
]:
    try:
        spark.conf.set(key, value)
    except Exception:                                        # noqa: BLE001
        print(f"note: {key} is managed by the runtime, leaving as-is")

# COMMAND ----------

# MAGIC %md
# MAGIC ## The bronze contract
# MAGIC
# MAGIC Expressed as data rather than scattered through the code, so adding a rule
# MAGIC is a one-line change and the same rules can be reported on a dashboard.

# COMMAND ----------

CONTRACTS = {
    "fact_retail_fuel_sales": {
        "key": "transaction_id",
        "watermark": "transaction_ts",
        "rules": {
            "transaction_id_present": "transaction_id IS NOT NULL",
            "site_id_present": "site_id IS NOT NULL",
            "product_id_present": "product_id IS NOT NULL",
            # A single vehicle fill. Above 900 L means a unit error upstream.
            "litres_plausible": "litres > 0 AND litres <= 900",
            # Regulated pump price; outside this band is a data fault.
            "price_plausible": "unit_price_zar BETWEEN 8 AND 45",
            "sales_non_negative": "gross_sales_zar >= 0",
            "margin_reconciles":
                "abs(gross_margin_zar - (gross_sales_zar - cogs_zar)) < 0.02",
        },
    },
    "fact_shop_sales": {
        "key": "shop_line_id",
        "watermark": "transaction_ts",
        "rules": {
            "shop_line_id_present": "shop_line_id IS NOT NULL",
            "site_id_present": "site_id IS NOT NULL",
            "quantity_plausible": "quantity BETWEEN 1 AND 50",
            "sales_non_negative": "gross_sales_zar >= 0",
        },
    },
    "fact_inventory_snapshot": {
        "key": "snapshot_id",
        "watermark": "snapshot_ts",
        "rules": {
            "snapshot_id_present": "snapshot_id IS NOT NULL",
            "stock_within_capacity":
                "stock_on_hand_litres >= 0 AND stock_on_hand_litres <= capacity_litres * 1.02",
            "cover_non_negative": "days_of_cover >= 0",
        },
    },
    "fact_ev_charging_sessions": {
        "key": "ev_session_id",
        "watermark": "session_start_ts",
        "rules": {
            "session_id_present": "ev_session_id IS NOT NULL",
            "energy_plausible": "energy_kwh >= 0 AND energy_kwh <= 400",
            "power_within_rating": "average_power_kw <= rated_power_kw * 1.05",
        },
    },
    "fact_solar_generation": {
        "key": "solar_reading_id",
        "watermark": "reading_ts",
        "rules": {
            "reading_id_present": "solar_reading_id IS NOT NULL",
            "energy_non_negative": "energy_kwh >= 0",
            # Physical impossibility check: a panel cannot generate at night.
            "no_generation_at_night": "is_daylight OR energy_kwh = 0",
        },
    },
}

# COMMAND ----------

def conform_fact(table: str, spec: dict) -> dict:
    """Apply the contract, quarantine failures, dedup, and write silver."""
    src = spark.table(f"{CATALOG}.bronze.{table}")
    total = src.count()

    # One boolean column per rule, so a quarantined row records *why*.
    checked = src
    for rule_name, expr in spec["rules"].items():
        checked = checked.withColumn(f"_dq_{rule_name}", F.expr(expr))
    rule_cols = [f"_dq_{r}" for r in spec["rules"]]

    checked = checked.withColumn(
        "_dq_failed_rules",
        F.concat_ws(",", *[
            F.when(~F.col(c), F.lit(c.replace("_dq_", ""))) for c in rule_cols
        ]),
    ).withColumn("_dq_passed", F.col("_dq_failed_rules") == "")

    passed = checked.filter("_dq_passed")
    failed = checked.filter("NOT _dq_passed")
    n_failed = failed.count()

    if n_failed:
        (failed
         .withColumn("_quarantined_at", F.current_timestamp())
         .withColumn("_source_table", F.lit(table))
         .write.format("delta").mode("append")
         .option("mergeSchema", "true")
         .saveAsTable(f"{CATALOG}.platform.quarantine"))

    # Source systems replay; keep the latest version of each business key.
    key, wm = spec["key"], spec["watermark"]
    window = Window.partitionBy(key).orderBy(
        F.col("ingested_at").desc(), F.col(wm).desc())
    deduped = (passed
               .withColumn("_rn", F.row_number().over(window))
               .filter("_rn = 1")
               .drop("_rn", "_dq_passed", "_dq_failed_rules", *rule_cols))

    n_out = deduped.count()
    (deduped
     .withColumn("_silver_loaded_at", F.current_timestamp())
     .write.format("delta").mode("overwrite")
     .option("overwriteSchema", "true")
     .saveAsTable(f"{CATALOG}.silver.{table}"))

    return {"table": table, "bronze_rows": total, "quarantined": n_failed,
            "duplicates_removed": total - n_failed - n_out, "silver_rows": n_out}


results = []
for table, spec in CONTRACTS.items():
    if not spark.catalog.tableExists(f"{CATALOG}.bronze.{table}"):
        print(f"skip {table}: not present in bronze")
        continue
    r = conform_fact(table, spec)
    results.append(r)
    print(f"{r['table']:<32} bronze={r['bronze_rows']:>10,}  "
          f"quarantined={r['quarantined']:>6,}  "
          f"dupes={r['duplicates_removed']:>6,}  silver={r['silver_rows']:>10,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Delta CHECK constraints
# MAGIC
# MAGIC The contract above filters on read. These constraints enforce the same
# MAGIC invariants at the table level, so any *future* writer -- a notebook, a
# MAGIC streaming job, someone running an ad-hoc `INSERT` -- is held to them too.

# COMMAND ----------

CONSTRAINTS = [
    ("silver.fact_retail_fuel_sales", "chk_litres_positive", "litres > 0"),
    ("silver.fact_retail_fuel_sales", "chk_litres_plausible", "litres <= 900"),
    ("silver.fact_retail_fuel_sales", "chk_price_band",
     "unit_price_zar BETWEEN 8 AND 45"),
    ("silver.fact_retail_fuel_sales", "chk_sales_non_negative",
     "gross_sales_zar >= 0"),
    ("silver.fact_shop_sales", "chk_quantity_positive", "quantity > 0"),
    ("silver.fact_ev_charging_sessions", "chk_energy_non_negative",
     "energy_kwh >= 0"),
    ("silver.fact_solar_generation", "chk_solar_non_negative", "energy_kwh >= 0"),
]

for table, name, expr in CONSTRAINTS:
    if not spark.catalog.tableExists(f"{CATALOG}.{table}"):
        continue
    try:
        spark.sql(f"ALTER TABLE {CATALOG}.{table} "
                  f"ADD CONSTRAINT {name} CHECK ({expr})")
        print(f"  added  {table}.{name}")
    except Exception as exc:                                   # noqa: BLE001
        # Already present is the normal case on a re-run.
        if "already exists" in str(exc).lower():
            print(f"  exists {table}.{name}")
        else:
            raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## SCD2 dimension merge
# MAGIC
# MAGIC The pattern is two-pass: close the version that changed, then insert the
# MAGIC new one. A single `MERGE` cannot both update an existing row and insert a
# MAGIC replacement for the same key, which is the usual trap here.

# COMMAND ----------

SCD2_DIMENSIONS = {
    "dim_site": {
        "key": "site_id",
        "tracked": ["site_name", "site_type", "ownership_model", "site_status",
                    "has_convenience", "has_qsr", "has_ev_charging",
                    "has_solar", "has_lpg", "forecourt_lanes"],
    },
    "dim_customer": {
        "key": "customer_id",
        "tracked": ["customer_name", "sector", "segment", "credit_band",
                    "credit_limit_zar", "payment_terms_days", "is_active"],
    },
    "dim_product": {
        "key": "product_id",
        "tracked": ["product_name", "category", "subcategory",
                    "base_price_zar", "base_cost_zar", "regulated"],
    },
}


def scd2_merge(dim: str, spec: dict) -> None:
    key, tracked = spec["key"], spec["tracked"]
    target_name = f"{CATALOG}.silver.{dim}"

    incoming = (
        spark.table(f"{CATALOG}.bronze.{dim}")
        # The hash is what decides "did anything we care about change".
        .withColumn("hash_diff", F.sha2(F.concat_ws("||", *[
            F.coalesce(F.col(c).cast("string"), F.lit("~")) for c in tracked]), 256))
        .withColumn("effective_from", F.current_timestamp())
        .withColumn("effective_to", F.lit("9999-12-31").cast("timestamp"))
        .withColumn("is_current", F.lit(True))
    )

    if not spark.catalog.tableExists(target_name):
        incoming.write.format("delta").saveAsTable(target_name)
        print(f"{dim}: initial load, {incoming.count():,} rows")
        return

    target = DeltaTable.forName(spark, target_name)
    current = target.toDF().filter("is_current")

    changed = (incoming.alias("n")
               .join(current.alias("c"), key)
               .filter("n.hash_diff <> c.hash_diff")
               .select(F.col(f"n.{key}").alias(key)))
    n_changed = changed.count()

    # Pass 1: close the superseded version.
    if n_changed:
        (target.alias("t").merge(
            changed.alias("s"), f"t.{key} = s.{key} AND t.is_current")
         .whenMatchedUpdate(set={
             "is_current": "false",
             "effective_to": "current_timestamp()"})
         .execute())

    # Pass 2: insert brand-new keys and new versions of changed keys.
    to_insert = incoming.join(
        current.select(key, "hash_diff"), [key, "hash_diff"], "left_anti")
    n_insert = to_insert.count()
    if n_insert:
        to_insert.write.format("delta").mode("append") \
            .option("mergeSchema", "true").saveAsTable(target_name)

    print(f"{dim}: {n_changed:,} versions closed, {n_insert:,} rows inserted, "
          f"{target.toDF().filter('is_current').count():,} current")


for dim, spec in SCD2_DIMENSIONS.items():
    if spark.catalog.tableExists(f"{CATALOG}.bronze.{dim}"):
        scd2_merge(dim, spec)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Conformance summary

# COMMAND ----------

if results:
    display(spark.createDataFrame(results))

print("\nsilver tables:")
display(spark.sql(f"SHOW TABLES IN {CATALOG}.silver"))
