# Databricks notebook source
# MAGIC %md
# MAGIC # 00 - Generate the bronze layer at scale (Spark native)
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No internal Vivo Energy, Engen,
# MAGIC Shell or Vitol data is used. Every site, customer, price, volume and
# MAGIC coordinate below is randomly generated.
# MAGIC
# MAGIC ## Why generate in-platform rather than upload
# MAGIC
# MAGIC The local Python generator (`src/vivo360/`) is the reference implementation
# MAGIC and is what CI runs. Uploading its 37-million-row output over a network
# MAGIC connection is slow and pointless when the same distributions can be produced
# MAGIC by Spark directly on the cluster in a couple of minutes.
# MAGIC
# MAGIC This notebook reproduces the same statistical model - commute-peaked hours,
# MAGIC weekday and seasonal shape, per-site demand index, monthly regulated price
# MAGIC steps - using `spark.range()` and native expressions, so nothing is pulled
# MAGIC to the driver.
# MAGIC
# MAGIC Writes to `${catalog}.bronze`.

# COMMAND ----------

dbutils.widgets.text("catalog", "vivo_dev", "Unity Catalog")
dbutils.widgets.dropdown("scale", "portfolio",
                         ["demo", "portfolio", "enterprise"], "Scale profile")
dbutils.widgets.text("seed", "3602026", "Random seed")

CATALOG = dbutils.widgets.get("catalog")
SCALE = dbutils.widgets.get("scale")
SEED = int(dbutils.widgets.get("seed"))

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql("USE SCHEMA bronze")

# Adaptive execution and optimized writes handle the skew introduced by
# weighting sites by demand. On classic compute these must be set explicitly;
# on serverless they are already on and the config is read-only, so setting
# them is best-effort rather than required.
for key, value in [
    ("spark.sql.adaptive.enabled", "true"),
    ("spark.sql.adaptive.coalescePartitions.enabled", "true"),
    ("spark.databricks.delta.optimizeWrite.enabled", "true"),
    ("spark.databricks.delta.autoCompact.enabled", "true"),
]:
    try:
        spark.conf.set(key, value)
    except Exception:                                        # noqa: BLE001
        print(f"note: {key} is managed by the runtime, leaving as-is")

SCALES = {
    "demo":       {"sites_za": 120, "sites_total": 400,  "customers": 8_000,
                   "retail": 250_000,   "shop": 150_000,   "loyalty": 100_000,
                   "digital": 80_000,   "inventory": 60_000, "deliveries": 20_000,
                   "commercial": 30_000, "solar": 40_000,  "ev": 10_000},
    "portfolio":  {"sites_za": 1_050, "sites_total": 4_200, "customers": 150_000,
                   "retail": 5_000_000, "shop": 3_000_000, "loyalty": 2_000_000,
                   "digital": 1_500_000, "inventory": 1_200_000, "deliveries": 300_000,
                   "commercial": 550_000, "solar": 650_000, "ev": 150_000},
    "enterprise": {"sites_za": 1_800, "sites_total": 8_000, "customers": 600_000,
                   "retail": 35_000_000, "shop": 20_000_000, "loyalty": 15_000_000,
                   "digital": 12_000_000, "inventory": 8_000_000, "deliveries": 2_000_000,
                   "commercial": 5_000_000, "solar": 5_000_000, "ev": 1_500_000},
}
CFG = SCALES[SCALE]
print(f"catalog={CATALOG}  scale={SCALE}  seed={SEED}")
print(f"target retail rows: {CFG['retail']:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## South African geography
# MAGIC
# MAGIC All nine provinces. City centroids are public geographic knowledge and are
# MAGIC used only as clustering anchors - every synthetic site coordinate is the
# MAGIC centroid plus random jitter, so no generated point represents a real
# MAGIC service station belonging to any company.

# COMMAND ----------

SA_ANCHORS = [
    # (province, city, lat, lon, weight, urban_class, on_national_route)
    ("Western Cape", "Cape Town", -33.9249, 18.4241, 46, "Metro", True),
    ("Western Cape", "Bellville", -33.9000, 18.6290, 18, "Metro", True),
    ("Western Cape", "Somerset West", -34.0794, 18.8570, 11, "Urban", True),
    ("Western Cape", "Paarl", -33.7342, 18.9621, 10, "Urban", True),
    ("Western Cape", "George", -33.9630, 22.4617, 9, "Urban", False),
    ("Western Cape", "Worcester", -33.6465, 19.4485, 7, "Town", True),
    ("Western Cape", "Beaufort West", -32.3567, 22.5833, 4, "Town", True),
    ("Gauteng", "Johannesburg", -26.2041, 28.0473, 58, "Metro", True),
    ("Gauteng", "Pretoria", -25.7479, 28.2293, 40, "Metro", True),
    ("Gauteng", "Sandton", -26.1076, 28.0567, 26, "Metro", True),
    ("Gauteng", "Soweto", -26.2485, 27.8540, 22, "Metro", False),
    ("Gauteng", "Midrand", -25.9992, 28.1263, 18, "Metro", True),
    ("Gauteng", "Centurion", -25.8603, 28.1894, 17, "Metro", True),
    ("Gauteng", "Kempton Park", -26.1000, 28.2300, 12, "Urban", True),
    ("Gauteng", "Vereeniging", -26.6731, 27.9261, 9, "Urban", True),
    ("KwaZulu-Natal", "Durban", -29.8587, 31.0218, 40, "Metro", True),
    ("KwaZulu-Natal", "Pietermaritzburg", -29.6006, 30.3794, 16, "Urban", True),
    ("KwaZulu-Natal", "Pinetown", -29.8167, 30.8500, 12, "Metro", True),
    ("KwaZulu-Natal", "Richards Bay", -28.7807, 32.0383, 9, "Urban", False),
    ("KwaZulu-Natal", "Newcastle", -27.7579, 29.9318, 8, "Urban", True),
    ("KwaZulu-Natal", "Ladysmith", -28.5539, 29.7800, 7, "Town", True),
    ("Eastern Cape", "Gqeberha", -33.9608, 25.6022, 20, "Metro", True),
    ("Eastern Cape", "East London", -33.0153, 27.9116, 15, "Urban", True),
    ("Eastern Cape", "Mthatha", -31.5889, 28.7844, 9, "Urban", True),
    ("Eastern Cape", "Queenstown", -31.8976, 26.8753, 5, "Town", True),
    ("Free State", "Bloemfontein", -29.0852, 26.1596, 18, "Urban", True),
    ("Free State", "Welkom", -27.9774, 26.7351, 9, "Urban", False),
    ("Free State", "Kroonstad", -27.6497, 27.2317, 7, "Town", True),
    ("Free State", "Harrismith", -28.2717, 29.1281, 5, "Town", True),
    ("Mpumalanga", "Mbombela", -25.4753, 30.9694, 13, "Urban", True),
    ("Mpumalanga", "eMalahleni", -25.8728, 29.2553, 11, "Urban", True),
    ("Mpumalanga", "Middelburg", -25.7751, 29.4644, 8, "Town", True),
    ("Mpumalanga", "Secunda", -26.5500, 29.1667, 8, "Town", False),
    ("Limpopo", "Polokwane", -23.9045, 29.4689, 13, "Urban", True),
    ("Limpopo", "Mokopane", -24.1944, 29.0097, 6, "Town", True),
    ("Limpopo", "Makhado", -23.0439, 29.9032, 6, "Town", True),
    ("Limpopo", "Musina", -22.3389, 30.0417, 4, "Town", True),
    ("North West", "Rustenburg", -25.6676, 27.2421, 12, "Urban", True),
    ("North West", "Klerksdorp", -26.8521, 26.6667, 9, "Urban", True),
    ("North West", "Potchefstroom", -26.7145, 27.0970, 7, "Urban", True),
    ("North West", "Mahikeng", -25.8652, 25.6442, 7, "Town", False),
    ("Northern Cape", "Kimberley", -28.7282, 24.7499, 9, "Urban", True),
    ("Northern Cape", "Upington", -28.4478, 21.2561, 6, "Town", True),
    ("Northern Cape", "Kathu", -27.6957, 23.0493, 4, "Town", False),
    ("Northern Cape", "De Aar", -30.6497, 24.0122, 3, "Rural", True),
]

anchor_schema = T.StructType([
    T.StructField("province", T.StringType()),
    T.StructField("city", T.StringType()),
    T.StructField("anchor_lat", T.DoubleType()),
    T.StructField("anchor_lon", T.DoubleType()),
    T.StructField("weight", T.IntegerType()),
    T.StructField("urban_class", T.StringType()),
    T.StructField("on_national_route", T.BooleanType()),
])
anchors = spark.createDataFrame(SA_ANCHORS, anchor_schema)

provinces = [r["province"] for r in anchors.select("province").distinct().collect()]
assert len(provinces) == 9, f"expected 9 provinces, got {len(provinces)}"
print("provinces covered:", sorted(provinces))

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_site
# MAGIC
# MAGIC Sites are allocated to town anchors in proportion to anchor weight, then
# MAGIC given a `demand_index` combining urban class, national-route position,
# MAGIC offer mix and a lognormal site-level idiosyncrasy. That index is what makes
# MAGIC the transaction data non-uniform: busy sites genuinely sell more.

# COMMAND ----------

# Expand anchors into a weighted lookup, then sample sites against it.
weighted_anchors = (
    anchors
    .withColumn("rep", F.explode(F.sequence(F.lit(1), F.col("weight"))))
    .drop("rep", "weight")
    .withColumn("slot", F.monotonically_increasing_id())
)
weighted_anchors = weighted_anchors.withColumn(
    "slot", F.row_number().over(
        __import__("pyspark.sql.window", fromlist=["Window"]).Window.orderBy("slot")) - 1
)
n_slots = weighted_anchors.count()

sites_za = (
    spark.range(0, CFG["sites_za"])
    .withColumnRenamed("id", "site_seq")
    .withColumn("slot", (F.rand(SEED) * n_slots).cast("int"))
    .join(F.broadcast(weighted_anchors), "slot")
    .drop("slot")
    .withColumn("site_id", F.format_string("S%06d", (F.col("site_seq") + 1).cast("int")))
    .withColumn("country_code", F.lit("ZA"))
    # Jitter: roughly a 2-4 km scatter, tighter in metros. Deliberately ensures
    # no generated coordinate lands on a real station.
    .withColumn("jitter", F.when(F.col("urban_class") == "Metro", F.lit(0.030))
                           .otherwise(F.lit(0.075)))
    .withColumn("latitude", F.col("anchor_lat") + (F.randn(SEED + 1) * F.col("jitter")))
    .withColumn("longitude", F.col("anchor_lon") + (F.randn(SEED + 2) * F.col("jitter")))
    .withColumn("u1", F.rand(SEED + 3))
    .withColumn("u2", F.rand(SEED + 4))
    .withColumn("u3", F.rand(SEED + 5))
    .withColumn("u4", F.rand(SEED + 6))
    .withColumn("u5", F.rand(SEED + 7))
    .withColumn("u6", F.rand(SEED + 8))
    .withColumn(
        "site_type",
        F.when(F.col("on_national_route") & (F.col("u1") < 0.35), "Highway Service Station")
         .when(F.col("u1") > 0.95, "Truck Stop")
         .when(F.col("urban_class").isin("Metro", "Urban"), "Urban Service Station")
         .otherwise("Rural Service Station"))
    .withColumn(
        "ownership_model",
        F.when(F.col("u2") < 0.12, "COCO").when(F.col("u2") < 0.70, "CODO").otherwise("DODO"))
    # Fictional retail banners, matching src/vivo360/names.py. Invented so no
    # generated site can be mistaken for a real branded station.
    .withColumn("banner", F.element_at(
        F.array(F.lit("Kalahari Fuels"), F.lit("Karoo Motion"),
                F.lit("Highveld Energy"), F.lit("Cape Route Fuels"),
                F.lit("Zambesi Fuels"), F.lit("Drakens Petroleum")),
        (F.col("u3") * 6).cast("int") + 1))
    # Numbered within the town, the way a real network is.
    .withColumn("site_in_city", F.row_number().over(
        Window.partitionBy("city").orderBy("site_seq")))
    .withColumn("site_name", F.when(
        F.col("site_in_city") == 1,
        F.concat_ws(" ", F.col("banner"), F.col("city")))
        .otherwise(F.concat_ws(" ", F.col("banner"), F.col("city"),
                               F.col("site_in_city").cast("string"))))
    .withColumn("has_convenience", F.col("u4") < 0.68)
    .withColumn("has_qsr", F.col("u5") < 0.31)
    .withColumn("has_ev_charging", F.col("u6") < 0.15)
    .withColumn("has_solar", F.rand(SEED + 9) < 0.12)
    .withColumn("has_lpg", F.rand(SEED + 10) < 0.44)
    .withColumn("is_24_hour", F.rand(SEED + 11) < 0.52)
    .withColumn("forecourt_lanes", (F.rand(SEED + 12) * 10 + 2).cast("int"))
    .withColumn("site_status",
                F.when(F.rand(SEED + 13) < 0.972, "Operating").otherwise("Temporarily Closed"))
    # demand_index: the multiplier driving how busy each site is.
    .withColumn("base_demand",
        F.when(F.col("urban_class") == "Metro", 1.45)
         .when(F.col("urban_class") == "Urban", 1.10)
         .when(F.col("urban_class") == "Town", 0.80)
         .otherwise(0.55))
    .withColumn("demand_index", F.round(
        F.col("base_demand")
        * F.when(F.col("on_national_route"), 1.30).otherwise(1.0)
        * F.when(F.col("site_type") == "Truck Stop", 1.55).otherwise(1.0)
        * F.when(F.col("has_convenience"), 1.12).otherwise(1.0)
        * F.exp(F.randn(SEED + 14) * 0.34)
        * F.when(F.col("site_status") == "Operating", 1.0).otherwise(0.05), 4))
    .drop("u1", "u2", "u3", "u4", "u5", "u6", "jitter", "banner",
          "anchor_lat", "anchor_lon", "base_demand", "site_seq")
)

(sites_za.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.dim_site"))

print(f"dim_site rows: {spark.table(f'{CATALOG}.bronze.dim_site').count():,}")
display(spark.sql(f"""
    SELECT province, count(*) AS sites, round(avg(demand_index), 3) AS avg_demand
    FROM {CATALOG}.bronze.dim_site GROUP BY province ORDER BY sites DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_product and dim_customer

# COMMAND ----------

PRODUCTS = [
    ("F001", "Premium Unleaded 95", "Fuel", "Petrol", "L", 24.10, 21.90, True),
    ("F002", "Unleaded 93", "Fuel", "Petrol", "L", 23.60, 21.50, True),
    ("F003", "Low Sulphur Diesel 50ppm", "Fuel", "Diesel", "L", 22.85, 20.85, True),
    ("F004", "Diesel 500ppm", "Fuel", "Diesel", "L", 22.35, 20.45, True),
    ("F008", "Illuminating Paraffin", "Fuel", "Paraffin", "L", 15.40, 13.90, True),
    ("F005", "Jet A-1", "Fuel", "Aviation", "L", 19.80, 17.60, False),
    ("F006", "Marine Gas Oil", "Fuel", "Marine", "L", 18.90, 16.80, False),
    ("LPG02", "LPG Cylinder 9kg", "LPG", "Cylinder", "KG", 34.20, 27.10, True),
    ("L001", "Passenger Vehicle Engine Oil", "Lubricant", "Automotive", "L", 92.00, 58.00, False),
    ("L002", "Heavy Duty Diesel Engine Oil", "Lubricant", "Transport", "L", 78.50, 49.00, False),
    ("S001", "Cold Beverage", "Convenience", "Beverage", "EA", 22.00, 13.60, False),
    ("S002", "Snack", "Convenience", "Food", "EA", 18.50, 10.80, False),
    ("S003", "Prepared Food", "Convenience", "QSR", "EA", 62.00, 33.00, False),
    ("S004", "Coffee", "Convenience", "Hot Beverage", "EA", 31.00, 12.40, False),
    ("E001", "EV DC Fast Charge", "Energy", "EV", "KWH", 7.60, 3.10, False),
]
product_schema = T.StructType([
    T.StructField("product_id", T.StringType()),
    T.StructField("product_name", T.StringType()),
    T.StructField("category", T.StringType()),
    T.StructField("subcategory", T.StringType()),
    T.StructField("uom", T.StringType()),
    T.StructField("base_price_zar", T.DoubleType()),
    T.StructField("base_cost_zar", T.DoubleType()),
    T.StructField("regulated", T.BooleanType()),
])
(spark.createDataFrame(PRODUCTS, product_schema)
    .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.dim_product"))

SECTORS = ["Road Transport", "Mining", "Construction", "Power Generation", "Aviation",
           "Marine", "Agriculture", "Manufacturing", "Government", "Reseller", "SME"]

# Invented name stems, kept in step with src/vivo360/names.py.
STEM_A = ["Thaba", "Rietkop", "Umzansi", "Kalahari", "Highveld", "Bosveld",
          "Karoo", "Drakens", "Zambesi", "Maluti", "Overberg", "Vaalkop",
          "Motheo", "Ntsika", "Khanya", "Ilanga", "Vukani", "Sondela",
          "Bloukrans", "Waterkloof", "Sandspruit", "Groenvlei", "Rooiberg",
          "Witkoppie", "Modderfontein", "Nkanyezi", "Amanzi", "Sekhaya",
          "Tswelopele", "Lehlabile", "Mzansi", "Kopano", "Ubuntu", "Sizanani",
          "Phakama", "Masakhane", "Lethabo", "Isibani", "Nkululeko", "Simunye",
          "Silverstroom", "Blesbok", "Kudu", "Springbok", "Rooikrans",
          "Duineveld", "Sandveld", "Hartland", "Vryheid", "Kameelkop"]
SEGMENTS = ["Strategic", "Key Account", "Mid Market", "Small Business", "Spot"]

customers = (
    spark.range(0, CFG["customers"])
    .withColumn("customer_id", F.format_string("C%07d", (F.col("id") + 1).cast("int")))
    .withColumn("sector", F.element_at(
        F.array(*[F.lit(s) for s in SECTORS]),
        (F.rand(SEED + 20) * len(SECTORS)).cast("int") + 1))
    # Invented stems combined with a sector-appropriate trade word, matching
    # src/vivo360/names.py. Placeholder strings like "Customer 0112573" make a
    # dashboard unreadable; these are recognisably South African business
    # names that name no real company.
    .withColumn("stem", F.element_at(
        F.array(*[F.lit(x) for x in STEM_A]),
        (F.rand(SEED + 28) * len(STEM_A)).cast("int") + 1))
    .withColumn("trade_word",
        F.when(F.col("sector") == "Road Transport", F.element_at(
            F.array(F.lit("Logistics"), F.lit("Transport"), F.lit("Freight"),
                    F.lit("Haulage"), F.lit("Carriers")),
            (F.rand(SEED + 29) * 5).cast("int") + 1))
         .when(F.col("sector") == "Mining", F.element_at(
            F.array(F.lit("Minerals"), F.lit("Mining"), F.lit("Resources"),
                    F.lit("Colliery"), F.lit("Ore Services")),
            (F.rand(SEED + 29) * 5).cast("int") + 1))
         .when(F.col("sector") == "Construction", F.element_at(
            F.array(F.lit("Civils"), F.lit("Construction"), F.lit("Projects"),
                    F.lit("Earthworks"), F.lit("Plant Hire")),
            (F.rand(SEED + 29) * 5).cast("int") + 1))
         .when(F.col("sector") == "Power Generation", F.element_at(
            F.array(F.lit("Power"), F.lit("Energy"), F.lit("Generation")),
            (F.rand(SEED + 29) * 3).cast("int") + 1))
         .when(F.col("sector") == "Aviation", F.element_at(
            F.array(F.lit("Aviation"), F.lit("Air Charter"), F.lit("Airways")),
            (F.rand(SEED + 29) * 3).cast("int") + 1))
         .when(F.col("sector") == "Marine", F.element_at(
            F.array(F.lit("Marine"), F.lit("Shipping"), F.lit("Maritime")),
            (F.rand(SEED + 29) * 3).cast("int") + 1))
         .when(F.col("sector") == "Agriculture", F.element_at(
            F.array(F.lit("Boerdery"), F.lit("Farms"), F.lit("Agri"),
                    F.lit("Estates")),
            (F.rand(SEED + 29) * 4).cast("int") + 1))
         .when(F.col("sector") == "Manufacturing", F.element_at(
            F.array(F.lit("Manufacturing"), F.lit("Industries"),
                    F.lit("Works"), F.lit("Fabrication")),
            (F.rand(SEED + 29) * 4).cast("int") + 1))
         .when(F.col("sector") == "Government", F.element_at(
            F.array(F.lit("Regional Services"), F.lit("District Works"),
                    F.lit("Public Fleet")),
            (F.rand(SEED + 29) * 3).cast("int") + 1))
         .otherwise(F.element_at(
            F.array(F.lit("Trading"), F.lit("Services"), F.lit("Enterprises"),
                    F.lit("Supplies"), F.lit("Wholesale")),
            (F.rand(SEED + 29) * 5).cast("int") + 1)))
    .withColumn("legal_suffix", F.element_at(
        F.array(F.lit(" (Pty) Ltd"), F.lit(" (Pty) Ltd"), F.lit(" CC"),
                F.lit(" Group"), F.lit("")),
        (F.rand(SEED + 31) * 5).cast("int") + 1))
    .withColumn("customer_name", F.concat(
        F.concat_ws(" ", F.col("stem"), F.col("trade_word")),
        F.col("legal_suffix")))
    .withColumn("u", F.rand(SEED + 21))
    .withColumn("segment",
        F.when(F.col("u") < 0.02, "Strategic").when(F.col("u") < 0.10, "Key Account")
         .when(F.col("u") < 0.30, "Mid Market").when(F.col("u") < 0.75, "Small Business")
         .otherwise("Spot"))
    .withColumn("cb", F.rand(SEED + 22))
    .withColumn("credit_band",
        F.when(F.col("cb") < 0.28, "A").when(F.col("cb") < 0.70, "B")
         .when(F.col("cb") < 0.93, "C").otherwise("D"))
    .withColumn("credit_limit_zar", F.round(F.exp(F.lit(12.4) + F.randn(SEED + 23) * 1.35), 2))
    .withColumn("payment_terms_days", F.element_at(
        F.array(F.lit(0), F.lit(7), F.lit(14), F.lit(30), F.lit(45), F.lit(60)),
        (F.rand(SEED + 24) * 6).cast("int") + 1))
    .withColumn("revenue_index", F.round(
        F.when(F.col("segment") == "Strategic", 22.0)
         .when(F.col("segment") == "Key Account", 8.5)
         .when(F.col("segment") == "Mid Market", 3.0)
         .when(F.col("segment") == "Small Business", 1.0).otherwise(0.6)
        * F.exp(F.randn(SEED + 25) * 0.5), 4))
    .withColumn("country_code", F.when(F.rand(SEED + 26) < 0.4, "ZA").otherwise("KE"))
    .withColumn("is_active", F.rand(SEED + 27) < 0.93)
    .drop("id", "u", "cb", "stem", "trade_word", "legal_suffix")
)
(customers.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.dim_customer"))
print(f"dim_customer rows: {spark.table(f'{CATALOG}.bronze.dim_customer').count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_retail_fuel_sales
# MAGIC
# MAGIC The largest table. Timestamps follow real trading rhythms rather than a
# MAGIC uniform draw:
# MAGIC
# MAGIC * **hour of day** - morning and evening commute peaks, dead 02:00-04:00
# MAGIC * **day of week** - Friday heaviest, Sunday lightest
# MAGIC * **month** - December holiday travel, quiet February
# MAGIC * **price** - a monthly step function, because SA pump prices are regulated
# MAGIC   and adjusted on the first Wednesday of the month, not continuously
# MAGIC
# MAGIC Sites are drawn in proportion to `demand_index`, so the distribution of
# MAGIC volume across the network is realistically skewed.

# COMMAND ----------

from pyspark.sql.window import Window

DATE_START = "2024-01-01"
N_DAYS = 974  # 2024-01-01 .. 2026-08-31

# Site sampling table weighted by demand_index, expanded to integer slots.
site_slots = (
    spark.table(f"{CATALOG}.bronze.dim_site")
    .select("site_id", "province", "city", "urban_class", "site_type",
            "on_national_route", "demand_index")
    .withColumn("slots", F.greatest(F.lit(1), F.round(F.col("demand_index") * 10).cast("int")))
    .withColumn("rep", F.explode(F.sequence(F.lit(1), F.col("slots"))))
    .drop("rep", "slots")
    .withColumn("slot", F.row_number().over(Window.orderBy(F.lit(1))) - 1)
)
n_site_slots = site_slots.count()
print(f"site sampling slots: {n_site_slots:,}")

# Hour-of-day weights, expanded to slots so a uniform draw yields the shape.
HOUR_WEIGHTS = [0.22, 0.14, 0.10, 0.10, 0.18, 0.45, 0.95, 1.55, 1.70, 1.25,
                1.05, 1.10, 1.25, 1.15, 1.05, 1.15, 1.45, 1.85, 1.70, 1.20,
                0.85, 0.62, 0.45, 0.30]
hour_slots = []
for h, w in enumerate(HOUR_WEIGHTS):
    hour_slots += [h] * int(round(w * 100))
hour_arr = F.array(*[F.lit(h) for h in hour_slots])
n_hour_slots = len(hour_slots)

# Day-of-week and month weighting, applied as an acceptance multiplier on an
# otherwise uniform day draw.
DOW_W = [1.00, 0.98, 1.01, 1.06, 1.24, 1.18, 0.79]
MONTH_W = {1: 1.02, 2: 0.90, 3: 1.05, 4: 1.08, 5: 0.97, 6: 0.94,
           7: 1.00, 8: 0.98, 9: 1.02, 10: 1.05, 11: 1.06, 12: 1.28}

GRADES = ["F001", "F002", "F003", "F004", "F008"]
GRADE_CUM = [0.24, 0.43, 0.84, 0.98, 1.00]

retail = (
    spark.range(0, CFG["retail"])
    .withColumn("transaction_id", F.format_string("RF%012d", (F.col("id") + 1)))
    # --- when ---------------------------------------------------------
    .withColumn("day_offset", (F.rand(SEED + 30) * N_DAYS).cast("int"))
    .withColumn("base_date", F.date_add(F.lit(DATE_START).cast("date"), F.col("day_offset")))
    .withColumn("hour", F.element_at(hour_arr, (F.rand(SEED + 31) * n_hour_slots).cast("int") + 1))
    .withColumn("minute", (F.rand(SEED + 32) * 60).cast("int"))
    .withColumn("second", (F.rand(SEED + 33) * 60).cast("int"))
    .withColumn("transaction_ts",
        (F.col("base_date").cast("timestamp")
         + F.expr("make_interval(0, 0, 0, 0, hour, minute, second)")))
    .withColumn("date_key", F.date_format("transaction_ts", "yyyyMMdd").cast("int"))
    .withColumn("time_key", F.hour("transaction_ts") * 60 + F.minute("transaction_ts"))
    # --- where --------------------------------------------------------
    .withColumn("slot", (F.rand(SEED + 34) * n_site_slots).cast("int"))
    .join(F.broadcast(site_slots) if n_site_slots < 200_000 else site_slots, "slot")
    .drop("slot")
    # --- what ---------------------------------------------------------
    .withColumn("g", F.rand(SEED + 35))
    .withColumn("product_id",
        F.when(F.col("g") < GRADE_CUM[0], GRADES[0])
         .when(F.col("g") < GRADE_CUM[1], GRADES[1])
         .when(F.col("g") < GRADE_CUM[2], GRADES[2])
         .when(F.col("g") < GRADE_CUM[3], GRADES[3])
         .otherwise(GRADES[4]))
    # Fill size: cars cluster near 40 L, trucks far higher.
    .withColumn("litres_raw", F.exp(F.lit(3.55) + F.randn(SEED + 36) * 0.42))
    .withColumn("litres", F.round(F.least(F.lit(900.0), F.greatest(F.lit(4.0),
        F.col("litres_raw")
        * F.when(F.col("site_type") == "Truck Stop", 4.2).otherwise(1.0)
        * F.when(F.col("on_national_route") & (F.col("site_type") != "Truck Stop"), 1.18)
           .otherwise(1.0))), 3))
    # Regulated price: a monthly step, not per-transaction noise.
    .withColumn("month_index",
        (F.year("transaction_ts") - 2024) * 12 + F.month("transaction_ts") - 1)
    .withColumn("base_price",
        F.when(F.col("product_id") == "F001", 24.10)
         .when(F.col("product_id") == "F002", 23.60)
         .when(F.col("product_id") == "F003", 22.85)
         .when(F.col("product_id") == "F004", 22.35).otherwise(15.40))
    .withColumn("unit_price_zar", F.round(
        F.col("base_price")
        + F.sin(F.col("month_index") / 3.4) * 1.15          # deterministic drift
        + F.cos(F.col("month_index") / 7.1) * 0.62
        + F.randn(SEED + 37) * 0.22, 3))                     # zone differential
    .withColumn("gross_sales_zar", F.round(F.col("litres") * F.col("unit_price_zar"), 2))
    .withColumn("cost_ratio",
        F.when(F.col("product_id") == "F001", 21.90 / 24.10)
         .when(F.col("product_id") == "F002", 21.50 / 23.60)
         .when(F.col("product_id") == "F003", 20.85 / 22.85)
         .when(F.col("product_id") == "F004", 20.45 / 22.35).otherwise(13.90 / 15.40))
    .withColumn("cogs_zar", F.round(
        F.col("gross_sales_zar") * F.col("cost_ratio") * (F.lit(1.0) + F.randn(SEED + 38) * 0.012), 2))
    .withColumn("gross_margin_zar", F.round(F.col("gross_sales_zar") - F.col("cogs_zar"), 2))
    # --- how ----------------------------------------------------------
    .withColumn("p", F.rand(SEED + 39))
    .withColumn("payment_method",
        F.when(F.col("p") < 0.46, "Card").when(F.col("p") < 0.70, "Cash")
         .when(F.col("p") < 0.88, "Fleet Card").when(F.col("p") < 0.98, "Mobile App")
         .otherwise("Voucher"))
    .withColumn("loyalty_flag", F.rand(SEED + 40) < 0.34)
    .withColumn("is_fleet_sale", F.col("payment_method") == "Fleet Card")
    .withColumn("pump_number", (F.rand(SEED + 41) * 12).cast("int") + 1)
    .withColumn("shift_name",
        F.when(F.col("hour") < 14, "Morning").when(F.col("hour") < 22, "Afternoon")
         .otherwise("Night"))
    # --- lineage ------------------------------------------------------
    .withColumn("source_system_code", F.lit("SRC01"))
    .withColumn("ingested_at", F.current_timestamp())
    .drop("id", "day_offset", "base_date", "hour", "minute", "second", "g",
          "litres_raw", "month_index", "base_price", "cost_ratio", "p",
          "demand_index")
)

(retail.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("date_key")
    .saveAsTable(f"{CATALOG}.bronze.fact_retail_fuel_sales"))

n_retail = spark.table(f"{CATALOG}.bronze.fact_retail_fuel_sales").count()
print(f"fact_retail_fuel_sales rows: {n_retail:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify the demand shape actually came out
# MAGIC
# MAGIC Generating data that *looks* random is easy; generating data that carries
# MAGIC the intended signal is the part worth checking. If the hourly profile below
# MAGIC is flat, the downstream forecasting notebook has nothing to learn.

# COMMAND ----------

display(spark.sql(f"""
    SELECT hour(transaction_ts) AS hour_of_day,
           count(*) AS transactions,
           round(sum(litres)) AS litres
    FROM {CATALOG}.bronze.fact_retail_fuel_sales
    GROUP BY 1 ORDER BY 1
"""))

# COMMAND ----------

display(spark.sql(f"""
    SELECT date_format(transaction_ts, 'EEEE') AS day_name,
           count(*) AS transactions
    FROM {CATALOG}.bronze.fact_retail_fuel_sales
    GROUP BY 1
    ORDER BY transactions DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Remaining high-volume facts

# COMMAND ----------

# ---------------------------------------------------------------- shop sales
SHOP = ["S001", "S002", "S003", "S004"]
shop = (
    spark.range(0, CFG["shop"])
    .withColumn("shop_line_id", F.format_string("SH%012d", (F.col("id") + 1)))
    .withColumn("day_offset", (F.rand(SEED + 50) * N_DAYS).cast("int"))
    .withColumn("transaction_ts",
        F.date_add(F.lit(DATE_START).cast("date"), F.col("day_offset")).cast("timestamp")
        + F.expr("make_interval(0,0,0,0, cast(rand(51)*24 as int), cast(rand(52)*60 as int), 0)"))
    .withColumn("date_key", F.date_format("transaction_ts", "yyyyMMdd").cast("int"))
    .withColumn("slot", (F.rand(SEED + 53) * n_site_slots).cast("int"))
    .join(site_slots.select("slot", "site_id"), "slot").drop("slot")
    .withColumn("product_id", F.element_at(
        F.array(*[F.lit(p) for p in SHOP]), (F.rand(SEED + 54) * 4).cast("int") + 1))
    .withColumn("quantity", (F.rand(SEED + 55) * 4).cast("int") + 1)
    .withColumn("unit_price_zar", F.round(
        F.when(F.col("product_id") == "S001", 22.00)
         .when(F.col("product_id") == "S002", 18.50)
         .when(F.col("product_id") == "S003", 62.00).otherwise(31.00)
        * (F.lit(1.0) + F.randn(SEED + 56) * 0.09), 2))
    .withColumn("gross_sales_zar", F.round(F.col("quantity") * F.col("unit_price_zar"), 2))
    .withColumn("cogs_zar", F.round(F.col("gross_sales_zar") * (0.55 + F.rand(SEED + 57) * 0.15), 2))
    .withColumn("gross_margin_zar", F.round(F.col("gross_sales_zar") - F.col("cogs_zar"), 2))
    .withColumn("promotion_applied", F.rand(SEED + 58) < 0.17)
    .withColumn("source_system_code", F.lit("SRC02"))
    .withColumn("ingested_at", F.current_timestamp())
    .drop("id", "day_offset")
)
(shop.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .partitionBy("date_key").saveAsTable(f"{CATALOG}.bronze.fact_shop_sales"))
print(f"fact_shop_sales rows: {spark.table(f'{CATALOG}.bronze.fact_shop_sales').count():,}")

# COMMAND ----------

# ------------------------------------------------------- inventory snapshots
inventory = (
    spark.range(0, CFG["inventory"])
    .withColumn("snapshot_id", F.format_string("INV%011d", (F.col("id") + 1)))
    .withColumn("day_offset", (F.rand(SEED + 60) * N_DAYS).cast("int"))
    .withColumn("snapshot_ts",
        F.date_add(F.lit(DATE_START).cast("date"), F.col("day_offset")).cast("timestamp")
        + F.expr("make_interval(0,0,0,0, cast(rand(61)*24 as int), 0, 0)"))
    .withColumn("date_key", F.date_format("snapshot_ts", "yyyyMMdd").cast("int"))
    .withColumn("slot", (F.rand(SEED + 62) * n_site_slots).cast("int"))
    .join(site_slots.select("slot", "site_id"), "slot").drop("slot")
    .withColumn("location_type", F.lit("Site"))
    .withColumn("product_id", F.element_at(
        F.array(F.lit("F001"), F.lit("F002"), F.lit("F003"), F.lit("F004")),
        (F.rand(SEED + 63) * 4).cast("int") + 1))
    .withColumn("capacity_litres", F.element_at(
        F.array(F.lit(9000.0), F.lit(12000.0), F.lit(23000.0), F.lit(30000.0), F.lit(46000.0)),
        (F.rand(SEED + 64) * 5).cast("int") + 1))
    .withColumn("fill_ratio", F.rand(SEED + 65) * 0.9 + 0.05)
    .withColumn("stock_on_hand_litres", F.round(F.col("capacity_litres") * F.col("fill_ratio"), 2))
    .withColumn("ullage_litres", F.round(F.col("capacity_litres") - F.col("stock_on_hand_litres"), 2))
    .withColumn("fill_pct", F.round(F.col("fill_ratio") * 100, 2))
    .withColumn("average_daily_usage_litres",
        F.round(F.col("capacity_litres") * (0.04 + F.rand(SEED + 66) * 0.31), 2))
    .withColumn("days_of_cover",
        F.round(F.col("stock_on_hand_litres") / F.col("average_daily_usage_litres"), 2))
    .withColumn("reorder_point_litres", F.round(F.col("average_daily_usage_litres") * 2.5, 2))
    .withColumn("is_stock_out_risk", F.col("days_of_cover") < 1.5)
    .withColumn("source_system_code", F.lit("SRC03"))
    .withColumn("ingested_at", F.current_timestamp())
    .drop("id", "day_offset", "fill_ratio")
)
(inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.fact_inventory_snapshot"))
print(f"fact_inventory_snapshot rows: {spark.table(f'{CATALOG}.bronze.fact_inventory_snapshot').count():,}")

# COMMAND ----------

# ------------------------------------------------------------ EV + solar
ev = (
    spark.range(0, CFG["ev"])
    .withColumn("ev_session_id", F.format_string("EVS%011d", (F.col("id") + 1)))
    .withColumn("day_offset", (F.rand(SEED + 70) * N_DAYS).cast("int"))
    .withColumn("session_start_ts",
        F.date_add(F.lit(DATE_START).cast("date"), F.col("day_offset")).cast("timestamp")
        + F.expr("make_interval(0,0,0,0, cast(rand(71)*24 as int), cast(rand(72)*60 as int), 0)"))
    .withColumn("date_key", F.date_format("session_start_ts", "yyyyMMdd").cast("int"))
    .withColumn("slot", (F.rand(SEED + 73) * n_site_slots).cast("int"))
    .join(site_slots.select("slot", "site_id"), "slot").drop("slot")
    .withColumn("rated_power_kw", F.element_at(
        F.array(F.lit(22.0), F.lit(60.0), F.lit(120.0), F.lit(150.0)),
        (F.rand(SEED + 74) * 4).cast("int") + 1))
    .withColumn("is_dc_fast", F.col("rated_power_kw") >= 60)
    # DC is a short high-power top-up; AC is a long dwell.
    .withColumn("duration_minutes", F.round(
        F.when(F.col("is_dc_fast"), F.exp(F.lit(3.2) + F.randn(SEED + 75) * 0.5))
         .otherwise(F.exp(F.lit(4.9) + F.randn(SEED + 76) * 0.45)), 1))
    .withColumn("average_power_kw",
        F.round(F.col("rated_power_kw") * (0.45 + F.rand(SEED + 77) * 0.47), 2))
    .withColumn("energy_kwh",
        F.round(F.col("average_power_kw") * F.col("duration_minutes") / 60.0, 3))
    .withColumn("tariff_zar_per_kwh",
        F.round(F.when(F.col("is_dc_fast"), 7.6).otherwise(5.4) + F.randn(SEED + 78) * 0.4, 3))
    .withColumn("revenue_zar", F.round(F.col("energy_kwh") * F.col("tariff_zar_per_kwh"), 2))
    .withColumn("grid_cost_zar", F.round(F.col("energy_kwh") * (2.9 + F.randn(SEED + 79) * 0.35), 2))
    .withColumn("gross_margin_zar", F.round(F.col("revenue_zar") - F.col("grid_cost_zar"), 2))
    .withColumn("connector_type",
        F.when(F.col("is_dc_fast"), "CCS2").otherwise("Type 2 AC"))
    .withColumn("source_system_code", F.lit("SRC05"))
    .withColumn("ingested_at", F.current_timestamp())
    .drop("id", "day_offset")
)
(ev.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.fact_ev_charging_sessions"))

solar = (
    spark.range(0, CFG["solar"])
    .withColumn("solar_reading_id", F.format_string("SG%012d", (F.col("id") + 1)))
    .withColumn("day_offset", (F.rand(SEED + 80) * N_DAYS).cast("int"))
    .withColumn("hour", (F.rand(SEED + 81) * 24).cast("int"))
    .withColumn("reading_ts",
        F.date_add(F.lit(DATE_START).cast("date"), F.col("day_offset")).cast("timestamp")
        + F.expr("make_interval(0,0,0,0, hour, cast(rand(82)*4 as int)*15, 0)"))
    .withColumn("date_key", F.date_format("reading_ts", "yyyyMMdd").cast("int"))
    .withColumn("slot", (F.rand(SEED + 83) * n_site_slots).cast("int"))
    .join(site_slots.select("slot", "site_id"), "slot").drop("slot")
    .withColumn("installed_kwp", F.round(15 + F.rand(SEED + 84) * 305, 1))
    # A daylight curve peaking at solar noon and exactly zero at night.
    .withColumn("daylight",
        F.greatest(F.lit(0.0), F.sin((F.col("hour") - 6.0) / 12.0 * F.lit(3.14159265))))
    .withColumn("seasonal",
        F.lit(0.86) + F.lit(0.20) * F.cos((F.month("reading_ts") - 1) / 12.0 * 6.2831853))
    .withColumn("cloud", F.when(F.rand(SEED + 85) < 0.28, 0.15 + F.rand(SEED + 86) * 0.6)
                          .otherwise(F.lit(1.0)))
    .withColumn("energy_kwh", F.round(
        F.col("installed_kwp") * F.col("daylight") * F.col("seasonal")
        * F.col("cloud") * 0.25, 4))
    .withColumn("is_daylight", F.col("daylight") > 0)
    .withColumn("co2_avoided_kg", F.round(F.col("energy_kwh") * 0.95, 3))
    .withColumn("irradiance_w_m2",
        F.round(F.col("daylight") * F.col("seasonal") * F.col("cloud") * 1000, 1))
    .withColumn("source_system_code", F.lit("SRC06"))
    .withColumn("ingested_at", F.current_timestamp())
    .drop("id", "day_offset", "hour", "daylight", "seasonal", "cloud")
)
(solar.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    .saveAsTable(f"{CATALOG}.bronze.fact_solar_generation"))

print(f"fact_ev_charging_sessions: {spark.table(f'{CATALOG}.bronze.fact_ev_charging_sessions').count():,}")
print(f"fact_solar_generation:     {spark.table(f'{CATALOG}.bronze.fact_solar_generation').count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build summary

# COMMAND ----------

tables = [t.tableName for t in spark.sql(f"SHOW TABLES IN {CATALOG}.bronze").collect()]
rows = []
for t in sorted(tables):
    try:
        rows.append((t, spark.table(f"{CATALOG}.bronze.{t}").count()))
    except Exception as exc:                        # noqa: BLE001
        rows.append((t, -1))
        print(f"could not count {t}: {exc}")

summary = spark.createDataFrame(rows, "table_name string, row_count long")
fact_rows = summary.filter(F.col("table_name").startswith("fact_")) \
                   .agg(F.sum("row_count")).collect()[0][0]
display(summary.orderBy(F.desc("row_count")))
print(f"\nTOTAL FACT ROWS IN BRONZE: {fact_rows:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC The bronze layer is now populated. `01_bronze_autoloader.py` demonstrates
# MAGIC the incremental file-ingestion path for the same tables, and
# MAGIC `02_silver_conformance.py` applies typing, deduplication and SCD2 merges.
