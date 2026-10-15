# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Adapted from Spark's structured_kafka_wordcount.py; see README.md.
"""Apache's schema-independent Kafka text example, with an explicit checkpoint."""
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import explode, split

if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(f"Usage: {sys.argv[0]} <brokers> <subscribe|assign|subscribePattern> <topics> <checkpoint>")
    bootstrapServers, subscribeType, topics, checkpoint = sys.argv[1:]
    if subscribeType not in {"subscribe", "assign", "subscribePattern"}:
        sys.exit("Invalid subscription type")
    spark = SparkSession.builder.appName("StructuredKafkaWordCount").getOrCreate()
    lines = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrapServers)
        .option(subscribeType, topics)
        .load().selectExpr("CAST(value AS STRING)")
    )
    words = lines.select(explode(split(lines.value, " ")).alias("word"))
    wordCounts = words.groupBy("word").count()
    query = (
        wordCounts.writeStream.outputMode("complete").format("console")
        .option("checkpointLocation", checkpoint).start()
    )
    try:
        query.awaitTermination()
    finally:
        query.stop()
        spark.stop()
