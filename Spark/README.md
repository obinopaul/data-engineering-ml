# Spark

For the connected **Kafka → Spark → Snowflake** route, use `kafka_to_snowflake.py` as shown in the [root checklist](../README.md). Edit `event_schema.example.json` for your data and add transformations at the marked location. It processes available events and exits by default; `--continuous` keeps consuming. The shared profile must use unattended authentication. The dlt sink transfers rows through the driver, so this is a small-volume starter rather than a distributed warehouse connector. Detailed recovery/scale notes are in [Ingestion](../Ingestion/README.md).

Use the same `.venv`, plus Java 17 or another Java version supported by Spark. Requirements select PySpark 4.2.0, which supports the existing Python 3.14 environment.

```python
from pyspark.sql import SparkSession
from Spark.datasources import read_csv, read_parquet, read_json, read_jdbc, write_parquet

spark = SparkSession.builder.master("local[2]").appName("interview").getOrCreate()
# frame = read_csv(spark, YOUR_PATH, schema=YOUR_SCHEMA)
# Add transformations here, then call spark.stop() when finished.
```

Readers take a Spark session and path; CSV/JSON accept an optional schema. JDBC takes a URL, table and connection properties and needs its database driver JAR. `write_parquet(frame, path)` fails if the output already exists.

For Kafka streaming, start the broker/topic from [Kafka's guide](../Kafka/README.md), then run from `main/`:

```bash
source .venv/bin/activate
spark-submit --master 'local[2]' \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.2.0 \
  Spark/kafka_wordcount.py localhost:9092 subscribe interview "$PWD/.cache/spark-checkpoint"
```

Start Spark before producing messages. It prints running word counts and stores restart state in `.cache/`. First use downloads the Kafka connector. Stop with Ctrl+C; use a new checkpoint path for a different query/topic.

Adapted from [Apache Spark examples](https://github.com/apache/spark/tree/master/examples/src/main/python/sql). The selected [PySpark release](https://pypi.org/project/pyspark/4.2.0/) and Scala 2.13 connector replace the old Spark 3.5 setup. Live execution is pending installation.
