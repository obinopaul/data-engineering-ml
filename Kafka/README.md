# Kafka

Use `.venv` for both scripts. Kafka also needs a broker; the optional Compose file starts one locally.

From `main/`:

```bash
source .venv/bin/activate
docker compose -p interview-kafka -f Kafka/compose.yml up -d
# Once the broker is healthy:
docker compose -p interview-kafka -f Kafka/compose.yml exec broker kafka-topics --bootstrap-server broker:29092 --create --if-not-exists --topic interview --partitions 1 --replication-factor 1
python Kafka/consumer.py localhost:9092 interview-group interview
```

In another terminal, activate the **same `.venv`** and send messages:

```bash
python Kafka/producer.py localhost:9092 interview
```

Type one message per line; Ctrl+D finishes. You can also redirect your own text/JSONL file into the producer. The consumer prints received bytes; replace that step with your assessment's processing logic. Ctrl+C stops the consumer.

For the REST-to-Snowflake route, use `--key-field id` on the producer so matching JSON IDs share a partition. [The root checklist](../README.md) connects the existing producer to dlt extraction and Spark loading. Match that key to your real event identifier. Producer idempotence handles delivery retries within its session; destination merges handle replayed records across sessions.

To remove the disposable broker and its data:

```bash
docker compose -p interview-kafka -f Kafka/compose.yml down
```

Adapted from [Confluent's Python examples](https://github.com/confluentinc/confluent-kafka-python/tree/master/examples); local Compose comes from Stage Two's E2E tutorial. These defaults use a local plaintext connection.
