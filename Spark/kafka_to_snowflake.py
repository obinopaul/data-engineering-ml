"""Kafka JSON -> Spark microbatches -> dlt -> Snowflake.

Uses Apache Spark's documented Kafka/from_json/foreachBatch APIs:
https://spark.apache.org/docs/latest/streaming/structured-streaming-kafka-integration.html
https://spark.apache.org/docs/latest/streaming/apis-on-dataframes-and-datasets.html
This small local adapter transfers rows through the driver; scale the sink before
using high-volume streams. Run with spark-submit from main/ (see root README).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Ingestion.run import load, read_config, validate_record
from Snowflake.connection import read_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--continuous", action="store_true",
        help="Wait for new events; default drains available events and exits",
    )
    args = parser.parse_args()
    from pyspark.sql import SparkSession, functions as F
    from pyspark.sql.types import StructType
    config = read_config(args.config)
    settings = read_profile()
    if settings.get("authenticator", "").lower() in ("externalbrowser", "username_password_mfa"):
        parser.error("Configure key-pair authentication in dbt/profiles.yml first.")
    stream = config["stream"]
    config["pipeline_name"] += "_stream"
    schema_path = ROOT / stream.get("schema_file", "Spark/event_schema.example.json")
    schema = StructType.fromJson(json.loads(schema_path.read_text()))
    metadata = {
        "ingest_kafka_offset", "ingest_kafka_partition",
        "ingest_kafka_topic", "ingest_raw_json",
    }
    if metadata.intersection(schema.fieldNames()):
        parser.error("Event schema uses reserved ingest_* metadata field names.")
    keys = config["primary_key"]
    keys = [keys] if isinstance(keys, str) else keys
    if not set(keys).issubset(schema.fieldNames()):
        parser.error("Every primary_key field must appear in the Spark event schema.")
    checkpoint = ROOT / ".cache/spark" / config["pipeline_name"]
    spark = SparkSession.builder.appName(config["pipeline_name"]).getOrCreate()
    query = None
    try:
        raw = (
            spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", stream.get("broker", "localhost:9092"))
            .option("subscribe", stream.get("topic", "interview"))
            .option("startingOffsets", "earliest")
            .option("failOnDataLoss", "true")
            .option("maxOffsetsPerTrigger", 10000).load()
        )
        parsed = raw.select(
            F.from_json(
                F.col("value").cast("string"), schema, {"mode": "FAILFAST"},
            ).alias("event"),
            F.col("value").cast("string").alias("ingest_raw_json"),
            F.col("offset").alias("ingest_kafka_offset"),
            F.col("partition").alias("ingest_kafka_partition"),
            F.col("topic").alias("ingest_kafka_topic"),
        ).select(
            "event.*", "ingest_raw_json", "ingest_kafka_offset",
            "ingest_kafka_partition", "ingest_kafka_topic",
        )
        # Add assessment-specific Spark transformations to `parsed` here.
        # A trained ML model may add prediction columns; fit it separately.

        def write_batch(frame, batch_id):
            if frame.isEmpty():
                return

            def rows():
                for row in frame.toLocalIterator():
                    yield validate_record(
                        row.asDict(recursive=True), config["primary_key"],
                    )

            # Errors propagate to Spark: its checkpoint advances only on success.
            # Same-key messages must stay on the same Kafka partition.
            load(
                config, rows(),
                columns={"ingest_kafka_offset": {"dedup_sort": "desc"}},
            )
            print(f"Loaded Spark batch {batch_id}")

        writer = parsed.writeStream.foreachBatch(write_batch).option(
            "checkpointLocation", str(checkpoint),
        )
        if args.continuous:
            writer = writer.trigger(processingTime="30 seconds")
        else:
            writer = writer.trigger(availableNow=True)
        query = writer.start()
        query.awaitTermination()
    finally:
        if query is not None:
            query.stop()
        spark.stop()


if __name__ == "__main__":
    main()
