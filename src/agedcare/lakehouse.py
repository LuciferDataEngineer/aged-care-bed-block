"""CDC to a Delta lakehouse: bronze envelopes, silver current state and SCD2, gold marts.

Spark runs local[2]. Structured Streaming uses trigger availableNow. MERGE maintains
the current service registry. A separate full-reload path overwrites that table
from each yearly snapshot so the two can be timed on the same machine.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from agedcare.lineage import emit_job
from agedcare.paths import DOCS, GOLD, LAKE

JAVA_HOME = os.environ.get("JAVA_HOME", "/usr/lib/jvm/java-17-openjdk-amd64")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "127.0.0.1:9092")
PACKAGES = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3,io.delta:delta-spark_2.12:3.2.1"


def _java() -> None:
    os.environ["JAVA_HOME"] = JAVA_HOME
    os.environ["PATH"] = str(Path(JAVA_HOME) / "bin") + os.pathsep + os.environ.get("PATH", "")


def session():
    _java()
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("aged-care-bed-block")
        .master("local[2]")
        .config("spark.driver.memory", "1g")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.jars.packages", PACKAGES)
        .config("spark.jars.ivy", str(LAKE / "ivy"))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def _parquet_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*.parquet"))


def stream_bronze(spark, bronze: Path) -> dict:
    started = time.perf_counter()
    if bronze.exists():
        shutil.rmtree(bronze)
    checkpoint = LAKE / "checkpoints" / "bronze"
    if checkpoint.exists():
        shutil.rmtree(checkpoint)
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", BOOTSTRAP)
        .option("subscribePattern", "agedcare\\.registry\\..*")
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )
    from pyspark.sql.functions import col

    projected = raw.select(
        col("topic"),
        col("partition"),
        col("offset"),
        col("timestamp").alias("kafka_ts"),
        col("key").cast("string").alias("message_key"),
        col("value").cast("string").alias("envelope"),
    )
    query = (
        projected.writeStream.format("delta")
        .option("checkpointLocation", str(checkpoint))
        .trigger(availableNow=True)
        .start(str(bronze))
    )
    query.awaitTermination()
    count = spark.read.format("delta").load(str(bronze)).count()
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "rows": int(count),
        "files": _parquet_files(bronze),
    }


def _events(spark, bronze: Path):
    from pyspark.sql.functions import coalesce, col, get_json_object, when

    frame = spark.read.format("delta").load(str(bronze))
    table_name = get_json_object("envelope", "$.source.table")
    op = get_json_object("envelope", "$.op")
    after = get_json_object("envelope", "$.after")
    before = get_json_object("envelope", "$.before")
    return frame.select(
        col("topic"),
        col("offset").cast("long").alias("offset"),
        get_json_object("envelope", "$.ts_ms").cast("long").alias("ts_ms"),
        when(op == "r", "c").otherwise(op).alias("op"),
        table_name.alias("table_name"),
        after.alias("after_json"),
        before.alias("before_json"),
        coalesce(after, before).alias("payload_json"),
    )


def _services(events):
    from pyspark.sql.functions import col, from_json
    from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

    schema = StructType(
        [
            StructField("service_id", StringType()),
            StructField("provider_id", StringType()),
            StructField("service_name", StringType()),
            StructField("care_type", StringType()),
            StructField("state_code", StringType()),
            StructField("acpr_name", StringType()),
            StructField("suburb", StringType()),
            StructField("residential_places", IntegerType()),
            StructField("home_care_places", IntegerType()),
            StructField("restorative_places", IntegerType()),
            StructField("source_year", IntegerType()),
            StructField("latitude", DoubleType()),
            StructField("longitude", DoubleType()),
        ]
    )
    parsed = events.where("table_name = 'services'").select(
        "op",
        "offset",
        "ts_ms",
        from_json(col("payload_json"), schema).alias("row"),
    )
    return parsed.select("op", "offset", "ts_ms", "row.*").where("service_id IS NOT NULL")


def merge_current(spark, services, target: Path) -> dict:
    """MERGE the latest CDC event per service into the current-state table."""
    from delta.tables import DeltaTable
    from pyspark.sql.functions import col, row_number
    from pyspark.sql.window import Window

    started = time.perf_counter()
    window = Window.partitionBy("service_id").orderBy(col("ts_ms").desc(), col("offset").desc())
    latest = (
        services.withColumn("rn", row_number().over(window))
        .where("rn = 1")
        .drop("rn")
        .withColumnRenamed("op", "last_op")
        .withColumnRenamed("ts_ms", "event_ts")
        .drop("offset")
    )
    latest = latest.cache()
    touched = latest.count()
    if target.exists() and DeltaTable.isDeltaTable(spark, str(target)):
        delta = DeltaTable.forPath(spark, str(target))
        (
            delta.alias("t")
            .merge(latest.alias("s"), "t.service_id = s.service_id")
            .whenMatchedDelete(condition="s.last_op = 'd'")
            .whenMatchedUpdateAll(condition="s.last_op <> 'd'")
            .whenNotMatchedInsertAll(condition="s.last_op <> 'd'")
            .execute()
        )
    else:
        latest.where("last_op <> 'd'").write.format("delta").mode("overwrite").save(str(target))
    current = spark.read.format("delta").load(str(target))
    rows = current.count()
    place_sum = current.groupBy().sum("residential_places").collect()[0][0]
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "rows_touched": int(touched),
        "current_rows": int(rows),
        "residential_places": int(place_sum or 0),
        "files": _parquet_files(target),
    }


def write_scd2(spark, services, target: Path) -> dict:
    from pyspark.sql.functions import col, lead
    from pyspark.sql.window import Window

    started = time.perf_counter()
    if target.exists():
        shutil.rmtree(target)
    window = Window.partitionBy("service_id").orderBy(col("ts_ms"), col("offset"))
    versions = (
        services.withColumn("valid_to_ts", lead("ts_ms").over(window))
        .where("op <> 'd'")
        .withColumnRenamed("ts_ms", "valid_from_ts")
        .withColumnRenamed("op", "change_op")
        .drop("offset")
    )
    versions.write.format("delta").mode("overwrite").save(str(target))
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "rows": int(spark.read.format("delta").load(str(target)).count()),
        "files": _parquet_files(target),
    }


def full_reload(spark, registry_parquet: Path, target: Path) -> dict:
    """Overwrite the current table once per year with that year's full snapshot."""
    from pyspark.sql.functions import col, lit

    started = time.perf_counter()
    if target.exists():
        shutil.rmtree(target)
    frame = spark.read.parquet(str(registry_parquet))
    years = [row.year for row in frame.select("year").distinct().orderBy("year").collect()]
    rows_touched = 0
    for year in years:
        snapshot = (
            frame.where(col("year") == year)
            .dropDuplicates(["service_id"])
            .withColumn("last_op", lit("reload"))
            .withColumn("event_ts", lit(int(year)))
            .withColumnRenamed("year", "source_year")
        )
        rows_touched += snapshot.count()
        snapshot.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(str(target))
    final_rows = spark.read.format("delta").load(str(target)).count()
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "rows_touched": int(rows_touched),
        "current_rows": int(final_rows),
        "files": _parquet_files(target),
        "years": [int(year) for year in years],
    }


def publish_gold(spark) -> None:
    gold = LAKE / "gold"
    for name in ("supply_gap_state", "supply_gap_acpr", "outlook_2031"):
        source = GOLD / f"{name}.parquet"
        dest = gold / name
        if dest.exists():
            shutil.rmtree(dest)
        spark.read.parquet(str(source)).write.format("delta").mode("overwrite").save(str(dest))


def export_current(spark, current: Path, services) -> None:
    export = LAKE / "export"
    export.mkdir(parents=True, exist_ok=True)
    spark.read.format("delta").load(str(current)).write.mode("overwrite").parquet(str(export / "services_current.parquet"))
    sample = services.limit(30).select("op", "service_id", "residential_places", "source_year", "state_code")
    rows = [row.asDict() for row in sample.collect()]
    (export / "sample_events.json").write_text(json.dumps(rows, default=str, indent=2))


def main() -> None:
    LAKE.mkdir(parents=True, exist_ok=True)
    spark = session()
    bronze = LAKE / "bronze" / "cdc"
    silver = LAKE / "silver" / "services_current"
    scd2 = LAKE / "silver" / "services_scd2"
    reload_path = LAKE / "bench" / "full_reload"
    bronze_stats = stream_bronze(spark, bronze)
    if bronze_stats["rows"] == 0:
        raise RuntimeError("Bronze is empty. Debezium did not publish registry changes to Redpanda.")
    events = _events(spark, bronze)
    services = _services(events).cache()
    merge_stats = merge_current(spark, services, silver)
    scd_stats = write_scd2(spark, services, scd2)
    reload_stats = full_reload(spark, GOLD / "service_registry.parquet", reload_path)
    publish_gold(spark)
    export_current(spark, silver, services)
    # Listed places by state, computed in Spark from the CDC current table.
    from pyspark.sql.functions import col, count
    from pyspark.sql.functions import sum as spark_sum

    listed = LAKE / "gold" / "listed_places_by_state"
    if listed.exists():
        shutil.rmtree(listed)
    (
        spark.read.format("delta")
        .load(str(silver))
        .groupBy("state_code")
        .agg(
            spark_sum(col("residential_places")).alias("listed_residential_places"),
            count("*").alias("services"),
        )
        .write.format("delta")
        .mode("overwrite")
        .save(str(listed))
    )
    benchmark = {
        "measured_on": "this machine, local[2], not a cloud cluster",
        "incremental_cdc": {
            "bronze_stream_seconds": bronze_stats["seconds"],
            "bronze_rows": bronze_stats["rows"],
            "bronze_files": bronze_stats["files"],
            "merge_seconds": merge_stats["seconds"],
            "merge_rows_touched": merge_stats["rows_touched"],
            "merge_files": merge_stats["files"],
            "current_services": merge_stats["current_rows"],
            "residential_places": merge_stats["residential_places"],
            "scd2_rows": scd_stats["rows"],
            "scd2_seconds": scd_stats["seconds"],
            "scd2_files": scd_stats["files"],
        },
        "full_reload": reload_stats,
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "benchmarks.json").write_text(json.dumps(benchmark, indent=2))
    emit_job(
        name="cdc_to_delta_lakehouse",
        inputs=["redpanda/agedcare.registry.services", "gold/supply_gap_state"],
        outputs=[
            "lakehouse/bronze/cdc",
            "lakehouse/silver/services_current",
            "lakehouse/silver/services_scd2",
            "lakehouse/gold/supply_gap_state",
            "lakehouse/gold/listed_places_by_state",
        ],
    )
    print(json.dumps(benchmark, indent=2))
    spark.stop()


if __name__ == "__main__":
    main()
