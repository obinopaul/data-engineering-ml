# Copyright 2016 Confluent Inc.
# Licensed under the Apache License, Version 2.0 (the "License").
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Adapted from confluent-kafka-python/examples/consumer.py; see README.md.
"""Print messages, then store their offsets; Ctrl+C closes the consumer."""
import sys
from confluent_kafka import Consumer, KafkaException

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(f"Usage: {sys.argv[0]} <broker:port> <group> <topic> [topic ...]")
    broker, group, *topics = sys.argv[1:]
    c = Consumer({
        "bootstrap.servers": broker,
        "group.id": group,
        "session.timeout.ms": 6000,
        "auto.offset.reset": "earliest",
        "enable.auto.offset.store": False,
    })
    c.subscribe(topics)
    try:
        while True:
            msg = c.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            print(msg.value(), flush=True)
            # Store only after processing. Auto-commit persists stored offsets.
            c.store_offsets(msg)
    except KeyboardInterrupt:
        pass
    finally:
        c.close()
