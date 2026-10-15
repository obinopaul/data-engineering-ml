# Copyright 2016 Confluent Inc.
# Licensed under the Apache License, Version 2.0 (the "License").
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Adapted from confluent-kafka-python/examples/producer.py; see README.md.
"""Send newline-delimited text from stdin. No application schema is imposed."""
import sys
import argparse
import json
from confluent_kafka import Producer

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("broker")
    parser.add_argument("topic")
    parser.add_argument("--key-field", help="JSON field used as the Kafka message key")
    args = parser.parse_args()
    broker, topic = args.broker, args.topic
    p = Producer({"bootstrap.servers": broker, "enable.idempotence": True, "acks": "all", "delivery.timeout.ms": 30000})
    delivery_errors = []

    def delivery_callback(err, msg):
        if err:
            delivery_errors.append(str(err))
            sys.stderr.write(f"Message failed delivery: {err}\n")
        else:
            sys.stderr.write(f"Delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}\n")

    for line in sys.stdin:
        key = None
        if args.key_field:
            record = json.loads(line)
            if not isinstance(record, dict) or record.get(args.key_field) is None:
                sys.exit("JSON record is missing the configured Kafka key field")
            key = str(record[args.key_field])
        # Retry the same line on backpressure; the original example drops it.
        while True:
            try:
                p.produce(topic, line.rstrip("\r\n"), key=key, callback=delivery_callback)
                break
            except BufferError:
                p.poll(0.1)
        p.poll(0)
    remaining = p.flush(35)
    if delivery_errors or remaining:
        sys.exit("One or more records were not delivered")
