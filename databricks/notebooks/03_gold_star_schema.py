# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Gold star schema
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC Builds the dimensional marts Power BI and the ML feature sets read from.
# MAGIC
# MAGIC Two decisions drive everything here:
# MAGIC
# MAGIC * **Business definitions live in gold, not in the BI tool.** OTIF, stock-out
# MAGIC   risk and margin percentage are each computed once. When a definition lives
# MAGIC   in DAX it gets reimplemented per report and two dashboards eventually
# MAGIC   disagree in front of an executive.
# MAGIC * **Aggregates are physical tables, not views.** The executive page must
# MAGIC   render from thousands of rows, not scan millions.
# MAGIC
# MAGIC In the production repo these same models are also expressed as dbt
# MAGIC (`dbt/models/marts/`); this notebook is the Spark-native path used when the
# MAGIC job runs without the dbt task.

# COMMAND ----------

dbutils.widgets.text("catalog", "vivo_dev", "Unity Catalog")
CATALOG = dbutils.widgets.get("catalog")

from pyspark.sql import functions as F

spark.sql(f"USE CATALOG {CATALOG}")

def silver(name):
    return spark.table(f"{CATALOG}.silver.{name}")

def save_gold(df, name, partition=None, comment=None):
    writer = (df.write.format("delta").mode("overwrite")
              .option("overwriteSchema", "true"))
    if partition:
        writer = writer.partitionBy(partition)
    writer.saveAsTable(f"{CATALOG}.gold.{name}")
    if comment:
        spark.sql(f"COMMENT ON TABLE {CATALOG}.gold.{name} IS '{comment}'")
    print(f"  {name:<34} {spark.table(f'{CATALOG}.gold.{name}').count():>12,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_date
# MAGIC
# MAGIC Generated rather than sourced. The fiscal year runs April to March.

# COMMAND ----------

dim_date = (
    spark.sql("SELECT explode(sequence(DATE'2024-01-01', DATE'2026-12-31', INTERVAL 1 DAY)) AS full_date")
    .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
    .withColumn("day_of_month", F.dayofmonth("full_date"))
    .withColumn("day_of_week", F.dayofweek("full_date"))
    .withColumn("day_name", F.date_format("full_date", "EEEE"))
    .withColumn("week_of_year", F.weekofyear("full_date"))
    .withColumn("month_number", F.month("full_date"))
    .withColumn("month_name", F.date_format("full_date", "MMMM"))
    .withColumn("quarter_number", F.quarter("full_date"))
    .withColumn("calendar_year", F.year("full_date"))
    .withColumn("fiscal_year", F.when(F.month("full_date") >= 4,
                                      F.year("full_date") + 1).otherwise(F.year("full_date")))
    .withColumn("fiscal_quarter", F.floor(F.pmod(F.month("full_date") - 4, F.lit(12)) / 3) + 1)
    .withColumn("fiscal_period", F.pmod(F.month("full_date") - 4, F.lit(12)) + 1)
    .withColumn("is_weekend", F.dayofweek("full_date").isin(1, 7))
    .withColumn("season_southern",
        F.when(F.month("full_date").isin(12, 1, 2), "Summer")
         .when(F.month("full_date").isin(3, 4, 5), "Autumn")
         .when(F.month("full_date").isin(6, 7, 8), "Winter").otherwise("Spring"))
    .withColumn("year_month", F.date_format("full_date", "yyyy-MM"))
)
save_gold(dim_date, "dim_date", comment="Conformed date dimension, SA fiscal calendar (April-March).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Conformed dimensions

# COMMAND ----------

dim_site = (
    silver("dim_site").filter("is_current")
    .withColumn("demand_band",
        F.when(F.col("demand_index") >= 2.0, "Very High")
         .when(F.col("demand_index") >= 1.4, "High")
         .when(F.col("demand_index") >= 0.9, "Medium")
         .when(F.col("demand_index") >= 0.5, "Low").otherwise("Very Low"))
    .withColumn("offer_tier",
        F.when(F.col("has_convenience") & F.col("has_qsr"), "Shop and QSR")
         .when(F.col("has_convenience"), "Shop Only").otherwise("Fuel Only"))
    .withColumn("new_energy_profile",
        F.when(F.col("has_ev_charging") & F.col("has_solar"), "EV and Solar")
         .when(F.col("has_ev_charging"), "EV Only")
         .when(F.col("has_solar"), "Solar Only").otherwise("None"))
    .withColumn("site_key", F.col("site_id"))
)
save_gold(dim_site, "dim_site",
          comment="Conformed site dimension. Synthetic; coordinates are jittered town centroids.")

dim_customer = (
    silver("dim_customer").filter("is_current")
    .withColumn("credit_risk_tier",
        F.when(F.col("credit_band").isin("A", "B"), "Low")
         .when(F.col("credit_band") == "C", "Medium").otherwise("High"))
    .withColumn("service_model",
        F.when(F.col("segment").isin("Strategic", "Key Account"), "Managed")
         .when(F.col("segment") == "Mid Market", "Inside Sales").otherwise("Self Serve"))
    .withColumn("customer_key", F.col("customer_id"))
)
save_gold(dim_customer, "dim_customer",
          comment="Conformed customer dimension. All names synthetic; masked by UC policy.")

dim_product = (
    silver("dim_product") if spark.catalog.tableExists(f"{CATALOG}.silver.dim_product")
    else spark.table(f"{CATALOG}.bronze.dim_product")
)
dim_product = (
    dim_product
    .withColumn("base_unit_margin_zar",
                F.round(F.col("base_price_zar") - F.col("base_cost_zar"), 4))
    .withColumn("base_margin_pct", F.round(
        (F.col("base_price_zar") - F.col("base_cost_zar")) / F.col("base_price_zar") * 100, 3))
    .withColumn("price_regime", F.when(F.col("regulated"), "Regulated").otherwise("Unregulated"))
    .withColumn("reporting_line",
        F.when(F.col("subcategory").isin("Petrol", "Diesel"), "Road Fuel")
         .when(F.col("subcategory") == "Aviation", "Aviation")
         .when(F.col("subcategory") == "Marine", "Marine")
         .otherwise(F.col("category")))
    .withColumn("product_key", F.col("product_id"))
)
save_gold(dim_product, "dim_product", comment="Conformed product dimension across all energy lines.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## fct_retail_fuel_sales
# MAGIC
# MAGIC Partitioned by `date_key` and liquid-clustered on `site_id`, because
# MAGIC virtually every query filters on a date range and groups by site.

# COMMAND ----------

fct_retail = (
    silver("fact_retail_fuel_sales").alias("f")
    .join(dim_site.select("site_id", "site_key", "province", "city", "urban_class",
                          "site_type", "ownership_model", "demand_band").alias("s"),
          "site_id", "left")
    .join(dim_product.select("product_id", "product_key", "product_name",
                             F.col("subcategory").alias("fuel_grade"),
                             "reporting_line", F.col("regulated").alias("is_regulated_price")).alias("p"),
          "product_id", "left")
    .withColumn("line_margin_pct", F.round(
        F.col("gross_margin_zar") / F.nullif(F.col("gross_sales_zar"), F.lit(0)) * 100, 4))
    .withColumn("margin_cents_per_litre", F.round(
        F.col("gross_margin_zar") / F.nullif(F.col("litres"), F.lit(0)) * 100, 3))
)
save_gold(fct_retail, "fct_retail_fuel_sales", partition="date_key",
          comment="One row per retail fuel sales transaction line.")

try:
    spark.sql(f"ALTER TABLE {CATALOG}.gold.fct_retail_fuel_sales CLUSTER BY (site_id, product_id)")
    print("  liquid clustering applied on (site_id, product_id)")
except Exception as exc:                                     # noqa: BLE001
    print(f"  clustering not applied: {exc}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## agg_site_daily_fuel
# MAGIC
# MAGIC The ~1000:1 reduction that keeps trend reporting off the transaction fact.

# COMMAND ----------

agg_site_daily = (
    spark.table(f"{CATALOG}.gold.fct_retail_fuel_sales")
    .groupBy("date_key", "site_id", "site_key", "province", "urban_class",
             "site_type", "demand_band")
    .agg(
        F.count("*").alias("transaction_count"),
        F.sum("litres").alias("litres"),
        F.round(F.sum("gross_sales_zar"), 2).alias("gross_sales_zar"),
        F.round(F.sum("cogs_zar"), 2).alias("cogs_zar"),
        F.round(F.sum("gross_margin_zar"), 2).alias("gross_margin_zar"),
        F.sum(F.when(F.col("fuel_grade") == "Diesel", F.col("litres")).otherwise(0)).alias("diesel_litres"),
        F.sum(F.when(F.col("fuel_grade") == "Petrol", F.col("litres")).otherwise(0)).alias("petrol_litres"),
        F.sum(F.when(F.col("loyalty_flag"), 1).otherwise(0)).alias("loyalty_transactions"),
        F.sum(F.when(F.col("is_fleet_sale"), 1).otherwise(0)).alias("fleet_transactions"),
    )
    .withColumn("gross_margin_pct", F.round(
        F.col("gross_margin_zar") / F.nullif(F.col("gross_sales_zar"), F.lit(0)) * 100, 3))
    .withColumn("litres_per_transaction", F.round(
        F.col("litres") / F.nullif(F.col("transaction_count"), F.lit(0)), 2))
    .withColumn("average_transaction_zar", F.round(
        F.col("gross_sales_zar") / F.nullif(F.col("transaction_count"), F.lit(0)), 2))
    .withColumn("loyalty_penetration_pct", F.round(
        F.col("loyalty_transactions") / F.nullif(F.col("transaction_count"), F.lit(0)) * 100, 2))
    .join(dim_date.select("date_key", "full_date", "day_name", "month_name",
                          "calendar_year", "fiscal_year", "is_weekend",
                          "season_southern"), "date_key", "left")
)
save_gold(agg_site_daily, "agg_site_daily_fuel",
          comment="One row per site per day. Serves retail trend reporting and the demand forecast.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## fct_inventory_position
# MAGIC
# MAGIC Semi-additive: sum across locations, never across time.

# COMMAND ----------

if spark.catalog.tableExists(f"{CATALOG}.silver.fact_inventory_snapshot"):
    fct_inventory = (
        silver("fact_inventory_snapshot")
        .join(dim_site.select("site_id", "site_key", "province", "demand_band"),
              "site_id", "left")
        .withColumn("cover_band",
            F.when(F.col("days_of_cover") < 0.5, "Critical")
             .when(F.col("days_of_cover") < 1.5, "At Risk")
             .when(F.col("days_of_cover") < 4, "Healthy")
             .when(F.col("days_of_cover") < 10, "Long").otherwise("Overstocked"))
        .withColumn("below_reorder_point",
                    F.col("stock_on_hand_litres") <= F.col("reorder_point_litres"))
    )
    save_gold(fct_inventory, "fct_inventory_position",
              comment="Semi-additive stock position. Sum across locations, not across time.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## New energy

# COMMAND ----------

if spark.catalog.tableExists(f"{CATALOG}.silver.fact_ev_charging_sessions"):
    fct_ev = (
        silver("fact_ev_charging_sessions")
        .join(dim_site.select("site_id", "site_key", "province", "city",
                              "urban_class", "on_national_route"), "site_id", "left")
        .withColumn("power_utilisation_pct", F.round(
            F.col("average_power_kw") / F.nullif(F.col("rated_power_kw"), F.lit(0)) * 100, 2))
        .withColumn("margin_zar_per_kwh", F.round(
            F.col("gross_margin_zar") / F.nullif(F.col("energy_kwh"), F.lit(0)), 4))
        .withColumn("session_profile",
            F.when(F.col("duration_minutes") < 20, "Top Up")
             .when(F.col("duration_minutes") < 60, "Standard")
             .when(F.col("duration_minutes") < 180, "Long Dwell").otherwise("Overnight"))
    )
    save_gold(fct_ev, "fct_ev_charging_sessions", comment="One row per EV charging session.")

if spark.catalog.tableExists(f"{CATALOG}.silver.fact_solar_generation"):
    fct_solar = (
        silver("fact_solar_generation")
        .join(dim_site.select("site_id", "site_key", "province"), "site_id", "left")
    )
    save_gold(fct_solar, "fct_solar_generation",
              comment="One row per solar asset per 15-minute interval.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## agg_executive_daily_kpi
# MAGIC
# MAGIC One row per province per day: the entire executive dashboard.

# COMMAND ----------

fuel_by_prov = (
    spark.table(f"{CATALOG}.gold.agg_site_daily_fuel")
    .groupBy("date_key", "province")
    .agg(
        F.countDistinct("site_id").alias("trading_sites"),
        F.sum("litres").alias("fuel_litres"),
        F.round(F.sum("gross_sales_zar"), 2).alias("fuel_revenue_zar"),
        F.round(F.sum("gross_margin_zar"), 2).alias("fuel_margin_zar"),
        F.sum("transaction_count").alias("fuel_transactions"),
    )
)

shop_by_prov = (
    silver("fact_shop_sales")
    .join(dim_site.select("site_id", "province"), "site_id", "left")
    .groupBy("date_key", "province")
    .agg(F.round(F.sum("gross_sales_zar"), 2).alias("shop_revenue_zar"),
         F.round(F.sum("gross_margin_zar"), 2).alias("shop_margin_zar"))
) if spark.catalog.tableExists(f"{CATALOG}.silver.fact_shop_sales") else None

agg_exec = fuel_by_prov
if shop_by_prov is not None:
    agg_exec = agg_exec.join(shop_by_prov, ["date_key", "province"], "left")
else:
    agg_exec = (agg_exec.withColumn("shop_revenue_zar", F.lit(0.0))
                        .withColumn("shop_margin_zar", F.lit(0.0)))

agg_exec = (
    agg_exec
    .fillna({"shop_revenue_zar": 0.0, "shop_margin_zar": 0.0})
    .withColumn("total_revenue_zar",
                F.round(F.col("fuel_revenue_zar") + F.col("shop_revenue_zar"), 2))
    .withColumn("total_margin_zar",
                F.round(F.col("fuel_margin_zar") + F.col("shop_margin_zar"), 2))
    .withColumn("gross_margin_pct", F.round(
        F.col("total_margin_zar") / F.nullif(F.col("total_revenue_zar"), F.lit(0)) * 100, 3))
    .withColumn("non_fuel_margin_share_pct", F.round(
        F.col("shop_margin_zar") / F.nullif(F.col("total_margin_zar"), F.lit(0)) * 100, 3))
    .withColumn("litres_per_site", F.round(
        F.col("fuel_litres") / F.nullif(F.col("trading_sites"), F.lit(0)), 1))
    .join(dim_date.select("date_key", "full_date", "day_name", "month_name",
                          "calendar_year", "fiscal_year", "fiscal_quarter",
                          "is_weekend"), "date_key", "left")
)
save_gold(agg_exec, "agg_executive_daily_kpi",
          comment="One row per province per day. Backs the executive dashboard.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## network_investment_scorecard
# MAGIC
# MAGIC The decision-support layer: every site scored on comparable terms so
# MAGIC capital can be ranked rather than argued. Percentile ranks put rand
# MAGIC figures and incident counts on the same 0-1 scale; the weights are an
# MAGIC explicit management judgement and are stated in the code so they can be
# MAGIC challenged directly.

# COMMAND ----------

from pyspark.sql import Window

trading = (
    spark.table(f"{CATALOG}.gold.agg_site_daily_fuel")
    .groupBy("site_id")
    .agg(
        F.countDistinct("date_key").alias("trading_days"),
        F.sum("litres").alias("litres_total"),
        F.avg("litres").alias("avg_daily_litres"),
        F.stddev_samp("litres").alias("stddev_daily_litres"),
        F.sum("gross_sales_zar").alias("fuel_revenue_zar"),
        F.sum("gross_margin_zar").alias("fuel_margin_zar"),
        F.sum("transaction_count").alias("transaction_count"),
    )
)

shop_site = (
    silver("fact_shop_sales").groupBy("site_id")
    .agg(F.sum("gross_sales_zar").alias("shop_revenue_zar"),
         F.sum("gross_margin_zar").alias("shop_margin_zar"))
) if spark.catalog.tableExists(f"{CATALOG}.silver.fact_shop_sales") else None

ev_site = (
    silver("fact_ev_charging_sessions").groupBy("site_id")
    .agg(F.count("*").alias("ev_session_count"),
         F.sum("gross_margin_zar").alias("ev_margin_zar"))
) if spark.catalog.tableExists(f"{CATALOG}.silver.fact_ev_charging_sessions") else None

scorecard = dim_site.select(
    "site_id", "site_key", "site_name", "province", "city", "urban_class",
    "site_type", "ownership_model", "site_status", "on_national_route",
    "offer_tier", "new_energy_profile", "has_convenience", "has_ev_charging",
    "has_solar", "latitude", "longitude", "demand_band", "demand_index"
).join(trading, "site_id", "left")

for extra in (shop_site, ev_site):
    if extra is not None:
        scorecard = scorecard.join(extra, "site_id", "left")

for col, default in [("shop_revenue_zar", 0.0), ("shop_margin_zar", 0.0),
                     ("ev_session_count", 0), ("ev_margin_zar", 0.0),
                     ("fuel_revenue_zar", 0.0), ("fuel_margin_zar", 0.0),
                     ("litres_total", 0.0), ("avg_daily_litres", 0.0),
                     ("transaction_count", 0)]:
    if col not in scorecard.columns:
        scorecard = scorecard.withColumn(col, F.lit(default))
    scorecard = scorecard.withColumn(col, F.coalesce(F.col(col), F.lit(default)))

scorecard = (
    scorecard
    .withColumn("total_revenue_zar", F.col("fuel_revenue_zar") + F.col("shop_revenue_zar"))
    .withColumn("total_margin_zar",
                F.col("fuel_margin_zar") + F.col("shop_margin_zar") + F.col("ev_margin_zar"))
    .withColumn("non_fuel_margin_share_pct", F.round(
        F.col("shop_margin_zar") / F.nullif(
            F.col("fuel_margin_zar") + F.col("shop_margin_zar"), F.lit(0)) * 100, 3))
    .withColumn("demand_volatility", F.round(
        F.col("stddev_daily_litres") / F.nullif(F.col("avg_daily_litres"), F.lit(0)), 4))
)

w_all = Window.orderBy(F.col("total_margin_zar"))
scorecard = (
    scorecard
    .withColumn("r_contribution", F.percent_rank().over(Window.orderBy("total_margin_zar")))
    .withColumn("r_throughput", F.percent_rank().over(Window.orderBy("avg_daily_litres")))
    .withColumn("r_non_fuel", F.percent_rank().over(
        Window.orderBy(F.coalesce(F.col("non_fuel_margin_share_pct"), F.lit(0.0)))))
    .withColumn("r_stability", F.lit(1.0) - F.percent_rank().over(
        Window.orderBy(F.coalesce(F.col("demand_volatility"), F.lit(0.0)))))
    .withColumn("r_new_energy", F.percent_rank().over(
        Window.orderBy(F.coalesce(F.col("ev_margin_zar"), F.lit(0.0)))))
    .withColumn("investment_score", F.round(100 * (
          0.40 * F.col("r_contribution")
        + 0.25 * F.col("r_throughput")
        + 0.15 * F.col("r_non_fuel")
        + 0.10 * F.col("r_stability")
        + 0.10 * F.col("r_new_energy")), 2))
    .withColumn("investment_quartile", F.ntile(4).over(
        Window.orderBy(F.desc("investment_score"))))
    .withColumn("investment_recommendation",
        F.when(F.col("investment_score") >= 75, "Invest")
         .when(F.col("investment_score") >= 50, "Hold")
         .when((F.col("investment_score") >= 25) & F.col("on_national_route"),
               "Hold - Strategic Coverage")
         .when(F.col("investment_score") >= 25, "Review")
         .otherwise("Divest Candidate"))
)

save_gold(scorecard, "network_investment_scorecard",
          comment="One row per site. Ranked investment score with every input visible.")

# COMMAND ----------

display(spark.sql(f"""
    SELECT investment_recommendation,
           count(*) AS sites,
           round(avg(investment_score), 1) AS avg_score,
           round(sum(total_margin_zar)) AS total_margin_zar
    FROM {CATALOG}.gold.network_investment_scorecard
    GROUP BY 1 ORDER BY avg_score DESC
"""))

# COMMAND ----------

print("gold tables:")
display(spark.sql(f"SHOW TABLES IN {CATALOG}.gold"))
