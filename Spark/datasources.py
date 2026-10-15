# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Parameterized excerpts from Spark's sql/datasource.py; see README.md.
"""Reusable upstream reader/writer patterns; no selected dataset or auto-execution."""


def read_csv(spark, path, delimiter=",", schema=None):
    reader = spark.read.option("delimiter", delimiter).option("header", True)
    if schema is not None:
        reader = reader.schema(schema)
    return reader.csv(path)


def read_parquet(spark, path):
    return spark.read.parquet(path)


def read_json(spark, path, schema=None):
    reader = spark.read
    if schema is not None:
        reader = reader.schema(schema)
    return reader.json(path)


def read_jdbc(spark, url, table, properties):
    return spark.read.jdbc(url, table, properties=properties)


def write_parquet(frame, output_path):
    # Spark's default error-if-exists behavior avoids silently overwriting output.
    frame.write.parquet(output_path)
