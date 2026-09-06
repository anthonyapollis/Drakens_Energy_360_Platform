# Databricks notebook source
# MAGIC %md
# MAGIC # 04 - Streaming telemetry ingestion
# MAGIC
# MAGIC **Independent synthetic portfolio project.** No real company data.
# MAGIC
# MAGIC Four real-time feeds, each with a genuinely different shape:
# MAGIC
# MAGIC | Feed | Source | Volume | Why it streams |
# MAGIC |---|---|---|---|
# MAGIC | Tank telemetry | Automatic tank gauges | ~21,000 tanks x 4/hour | A stock-out is only preventable if you see the level fall |
# MAGIC | Fleet GPS | Vehicle telematics | ~15,000 vehicles x 1/min | ETA accuracy decays fast on batch data |
# MAGIC | EV charging | OCPP charge points | ~2,600 chargers, event-driven | A faulted charger earns nothing until someone knows |
# MAGIC | Solar inverters | Site PV | ~1,900 inverters x 15 min | Generation shortfall vs irradiance is the fault signal |
# MAGIC
# MAGIC ## Watermarks
# MAGIC
# MAGIC Telemetry arrives late and out of order: a truck drives through a dead spot
# MAGIC and flushes twenty minutes of buffered points at once. Each stream declares
# MAGIC a watermark sized to its own worst realistic lateness, which bounds the
# MAGIC state Spark must hold. Too tight and real events are dropped; too loose and
# MAGIC state grows without limit.

# COMMAND ----------

dbutils.widgets.text("catalog", "vivo_dev", "Unity Catalog")
dbutils.widgets.dropdown("mode", "demo", ["demo", "production"], "Mode")

CATALOG = dbutils.widgets.get("catalog")
MODE = dbutils.widgets.get("mode")

from pyspark.sql import functions as F
from pyspark.sql import types as T

spark.sql(f"USE CATALOG {CATALOG}")
CHECKPOINTS = f"/Volumes/{CATALOG}/bronze/checkpoints"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Source
# MAGIC
# MAGIC In production these read from Azure Event Hubs via the Kafka connector. In
# MAGIC `demo` mode the same pipeline is driven by the `rate` source, so the
# MAGIC transformation, watermark and merge logic below are exercised for real
# MAGIC without needing a broker. The only thing that changes is the reader.

# COMMAND ----------

EVENTHUB_CONF = {
    # Populated from a Databricks secret scope; no credential is ever written
    # into notebook source or into a job definition.
    "kafka.bootstrap.servers":
        "{{secrets/vivo360/eventhub_bootstrap}}",
    "kafka.sasl.jaas.config":
        'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule '
        'required username="$ConnectionString" '
        'password="{{secrets/vivo360/eventhub_connection}}";',
    "kafka.sasl.mechanism": "PLAIN",
    "kafka.security.protocol": "SASL_SSL",
    "startingOffsets": "latest",
    # Cap each micro-batch so a backlog cannot produce one enormous batch.
    "maxOffsetsPerTrigger": "500000",
}


def source_stream(topic: str, rows_per_second: int):
    if MODE == "production":
        return (spark.readStream.format("kafka")
                .options(**EVENTHUB_CONF)
                .option("subscribe", topic)
                .load()
                .select(F.col("value").cast("string").alias("raw_json"),
                        F.col("timestamp").alias("kafka_ts")))
    return (spark.readStream.format("rate")
            .option("rowsPerSecond", rows_per_second)
            .load())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Tank telemetry
# MAGIC
# MAGIC The business question is "which site runs dry first". Level readings are
# MAGIC turned into a falling-rate estimate and hours-to-empty, then written to a
# MAGIC table the replenishment planner reads.

# COMMAND ----------

site_ids = [r.site_id for r in
            spark.table(f"{CATALOG}.bronze.dim_site").select("site_id").limit(2000).collect()]
n_sites = len(site_ids)
site_array = F.array(*[F.lit(s) for s in site_ids])
print(f"streaming across {n_sites} sites")

tank_stream = (
    source_stream("tank-telemetry", 200)
    .withColumn("tank_id", F.format_string("TK%06d", (F.col("value") % 21000).cast("int")))
    .withColumn("site_id", F.element_at(site_array, (F.col("value") % n_sites).cast("int") + 1))
    .withColumn("product_id", F.element_at(
        F.array(F.lit("F001"), F.lit("F002"), F.lit("F003"), F.lit("F004")),
        (F.col("value") % 4).cast("int") + 1))
    .withColumn("event_ts", F.col("timestamp"))
    .withColumn("capacity_litres", F.lit(23000.0))
    # A sawtooth: level falls through the day, jumps on delivery.
    .withColumn("fill_pct", F.round(
        20 + 70 * F.abs(F.sin(F.col("value") / 137.0)), 2))
    .withColumn("volume_litres", F.round(F.col("capacity_litres") * F.col("fill_pct") / 100, 1))
    .withColumn("ullage_litres", F.round(F.col("capacity_litres") - F.col("volume_litres"), 1))
    .withColumn("temperature_celsius", F.round(21 + F.randn() * 5, 1))
    .withColumn("water_level_mm", F.when(F.rand() < 0.04, F.round(F.rand() * 45, 1)).otherwise(0.0))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_system_code", F.lit("SRC03"))
    # Tank gauges buffer locally through a comms outage; 30 minutes covers the
    # realistic worst case without unbounded state.
    .withWatermark("event_ts", "30 minutes")
)

tank_query = (
    tank_stream.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", f"{CHECKPOINTS}/stream_tank_telemetry")
    .queryName("tank_telemetry")
    .trigger(availableNow=True) if MODE == "demo" else
    tank_stream.writeStream.format("delta").outputMode("append")
    .option("checkpointLocation", f"{CHECKPOINTS}/stream_tank_telemetry")
    .queryName("tank_telemetry").trigger(processingTime="30 seconds")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Windowed stock-out risk
# MAGIC
# MAGIC A single low reading is noise; a level falling steadily for an hour is a
# MAGIC delivery that needs bringing forward. The aggregation below is what makes
# MAGIC that distinction, and it is why this is a stream and not an hourly batch.

# COMMAND ----------

tank_risk = (
    tank_stream
    .groupBy(
        F.window("event_ts", "1 hour", "15 minutes"),
        "site_id", "tank_id", "product_id")
    .agg(
        F.min("volume_litres").alias("min_volume_litres"),
        F.max("volume_litres").alias("max_volume_litres"),
        F.avg("volume_litres").alias("avg_volume_litres"),
        F.last("volume_litres").alias("latest_volume_litres"),
        F.avg("capacity_litres").alias("capacity_litres"),
        F.count("*").alias("reading_count"),
    )
    .withColumn("window_start", F.col("window.start"))
    .withColumn("window_end", F.col("window.end"))
    .drop("window")
    # Litres per hour of drawdown, from the movement inside the window.
    .withColumn("drawdown_lph",
                F.greatest(F.lit(0.0), F.col("max_volume_litres") - F.col("min_volume_litres")))
    .withColumn("hours_to_empty", F.round(
        F.col("latest_volume_litres") / F.greatest(F.col("drawdown_lph"), F.lit(1.0)), 2))
    .withColumn("risk_level",
        F.when(F.col("hours_to_empty") < 6, "Critical")
         .when(F.col("hours_to_empty") < 18, "High")
         .when(F.col("hours_to_empty") < 48, "Medium").otherwise("Low"))
    .withColumn("_computed_at", F.current_timestamp())
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Fleet GPS
# MAGIC
# MAGIC Deduplicated on `(vehicle_id, event_ts)` inside the watermark, because
# MAGIC telematics units retransmit after a reconnect and the same point arriving
# MAGIC twice would double-count distance.

# COMMAND ----------

gps_stream = (
    source_stream("fleet-gps", 300)
    .withColumn("vehicle_id", F.format_string("V%06d", (F.col("value") % 15000).cast("int")))
    .withColumn("event_ts", F.col("timestamp"))
    .withColumn("latitude", F.round(-34.6 + F.rand() * 12.3, 5))
    .withColumn("longitude", F.round(16.5 + F.rand() * 16.4, 5))
    .withColumn("speed_kph", F.round(F.least(F.lit(120.0), F.abs(F.randn() * 30 + 55)), 1))
    .withColumn("heading_degrees", F.round(F.rand() * 360, 1))
    .withColumn("odometer_km", F.round(20000 + F.rand() * 1380000, 1))
    .withColumn("engine_on", F.col("speed_kph") > 0)
    .withColumn("fuel_level_pct", F.round(F.rand() * 100, 1))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_system_code", F.lit("SRC04"))
    # Vehicles lose signal in terrain; 15 minutes of buffered points is normal.
    .withWatermark("event_ts", "15 minutes")
    .dropDuplicates(["vehicle_id", "event_ts"])
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. EV charge points (OCPP)
# MAGIC
# MAGIC Status events, not measurements. The value is latency: a faulted charger
# MAGIC earns nothing until someone is told, so the fault path is a stream and the
# MAGIC session revenue is a batch.

# COMMAND ----------

ev_stream = (
    source_stream("ev-ocpp", 60)
    .withColumn("ev_charger_id", F.format_string("EVC%05d", (F.col("value") % 2600).cast("int")))
    .withColumn("event_ts", F.col("timestamp"))
    .withColumn("m", F.col("value") % 100)
    .withColumn("status",
        F.when(F.col("m") < 46, "Available").when(F.col("m") < 77, "Charging")
         .when(F.col("m") < 83, "Preparing").when(F.col("m") < 88, "Finishing")
         .when(F.col("m") < 93, "Faulted").otherwise("Unavailable"))
    .withColumn("is_faulted", F.col("status") == "Faulted")
    .withColumn("error_code", F.when(F.col("is_faulted"), F.element_at(
        F.array(F.lit("EVSE-101"), F.lit("EVSE-204"), F.lit("EVSE-311"), F.lit("EVSE-450")),
        (F.col("value") % 4).cast("int") + 1)))
    .withColumn("meter_kwh", F.round(F.rand() * 90000, 3))
    .withColumn("connector_id", (F.col("value") % 2).cast("int") + 1)
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_system_code", F.lit("SRC05"))
    .withWatermark("event_ts", "10 minutes")
    .drop("m")
)

# Faults are routed to their own table so alerting reads a small hot table
# rather than filtering the full status history on every evaluation.
ev_faults = ev_stream.filter("is_faulted").select(
    "ev_charger_id", "event_ts", "status", "error_code", "connector_id",
    "_ingested_at")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Solar inverters
# MAGIC
# MAGIC Generation is compared against what the irradiance implies. A panel string
# MAGIC that has failed still reports; it just under-produces, and only the ratio
# MAGIC reveals it.

# COMMAND ----------

solar_stream = (
    source_stream("solar-inverter", 80)
    .withColumn("solar_asset_id", F.format_string("SOL%05d", (F.col("value") % 1900).cast("int")))
    .withColumn("event_ts", F.col("timestamp"))
    .withColumn("installed_kwp", F.lit(120.0))
    .withColumn("irradiance_w_m2", F.round(F.greatest(F.lit(0.0),
        F.sin((F.hour(F.col("timestamp")) - 6.0) / 12.0 * 3.14159265) * 1000 * (0.6 + F.rand() * 0.4)), 1))
    .withColumn("expected_kw", F.round(F.col("installed_kwp") * F.col("irradiance_w_m2") / 1000.0, 3))
    # A degraded string produces materially less than irradiance implies.
    .withColumn("degradation", F.when(F.rand() < 0.05, 0.45 + F.rand() * 0.25).otherwise(0.93 + F.rand() * 0.07))
    .withColumn("actual_kw", F.round(F.col("expected_kw") * F.col("degradation"), 3))
    .withColumn("performance_ratio", F.round(
        F.col("actual_kw") / F.greatest(F.col("expected_kw"), F.lit(0.001)), 4))
    .withColumn("inverter_temperature_c", F.round(25 + F.rand() * 40, 1))
    .withColumn("underperforming",
                (F.col("expected_kw") > 5) & (F.col("performance_ratio") < 0.75))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_system_code", F.lit("SRC06"))
    .withWatermark("event_ts", "20 minutes")
    .drop("degradation")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Start the streams

# COMMAND ----------

def start(df, table: str, name: str, mode: str = "append"):
    writer = (df.writeStream.format("delta").outputMode(mode)
              .option("checkpointLocation", f"{CHECKPOINTS}/stream_{name}")
              .option("mergeSchema", "true")
              .queryName(name))
    writer = (writer.trigger(availableNow=True) if MODE == "demo"
              else writer.trigger(processingTime="30 seconds"))
    return writer.toTable(f"{CATALOG}.bronze.{table}")


started = []
for df, table, name, out_mode in [
    (tank_stream, "stream_tank_telemetry", "tank_telemetry", "append"),
    (tank_risk, "stream_tank_stockout_risk", "tank_risk", "append"),
    (gps_stream, "stream_fleet_gps", "fleet_gps", "append"),
    (ev_stream, "stream_ev_status", "ev_status", "append"),
    (ev_faults, "stream_ev_faults", "ev_faults", "append"),
    (solar_stream, "stream_solar_telemetry", "solar_telemetry", "append"),
]:
    try:
        q = start(df, table, name, out_mode)
        started.append((name, q))
        print(f"started {name} -> bronze.{table}")
    except Exception as exc:                                 # noqa: BLE001
        print(f"could not start {name}: {exc}")

if MODE == "demo":
    for name, q in started:
        q.awaitTermination()
        prog = q.lastProgress
        print(f"{name}: {prog['numInputRows'] if prog else 0:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stream health
# MAGIC
# MAGIC In production this is what the alert rule reads: input rate against
# MAGIC processing rate. A processing rate persistently below the input rate means
# MAGIC the stream is falling behind and the batch interval or cluster needs
# MAGIC changing before the backlog becomes unrecoverable.

# COMMAND ----------

for q in spark.streams.active:
    p = q.lastProgress
    if p:
        print(f"{q.name:<20} in={p.get('inputRowsPerSecond', 0):>8.1f}/s  "
              f"proc={p.get('processedRowsPerSecond', 0):>8.1f}/s  "
              f"batch={p.get('batchId')}")
