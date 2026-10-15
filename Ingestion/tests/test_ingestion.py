"""Offline regression checks; external dlt/Snowflake calls are mocked explicitly."""
import contextlib
import io
import json
import math
import os
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from Ingestion.run import destination_credentials, load, main, normalize_missing, read_config, source_resource, validate_record
from Snowflake.connection import read_profile


class IngestionTests(unittest.TestCase):
    def test_missing_measurements_become_json_null_without_changing_zero_or_key_rules(self):
        row = {"id": 1, "measurement": math.nan, "zero": 0.0,
               "nested": [{"missing": math.nan}], "literal": "NaN"}
        cleaned = normalize_missing(row)
        self.assertIsNone(json.loads(json.dumps(cleaned, allow_nan=False))["measurement"])
        self.assertEqual(cleaned["nested"], [{"missing": None}])
        self.assertEqual(cleaned["zero"], 0.0)
        self.assertEqual(cleaned["literal"], "NaN")
        self.assertTrue(math.isnan(row["measurement"]))
        with self.assertRaises(ValueError):
            validate_record(normalize_missing({"id": math.nan}), "id")
        with self.assertRaises(ValueError):
            json.dumps(normalize_missing({"value": math.inf}), allow_nan=False)

    def test_csv_reader_handles_empty_sensor_cells_for_json_export(self):
        import importlib.util
        if importlib.util.find_spec("dlt") is None:
            self.skipTest("dlt is not installed")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "measurements.csv").write_text("id,value\n1,\n2,0\n")
            config = {"table": "measurements", "primary_key": "id", "source": {
                "type": "files", "location": directory, "glob": "measurements.csv", "format": "csv"}}
            rows = list(source_resource(config))
            self.assertIsNone(rows[0]["value"])
            self.assertEqual(rows[1]["value"], 0)
            json.dumps(rows, allow_nan=False)

    def test_missing_vendor_settings_exit_before_source_or_destination(self):
        error = io.StringIO()
        with patch.object(sys, "argv", ["ingestion", "Ingestion/netsuite.example.yml", "--preview", "5"]), patch(
            "Ingestion.run.importlib.util.find_spec", return_value=object()
        ), patch.dict(os.environ, {}, clear=True), patch("Ingestion.run.load_local_env"), patch(
            "Ingestion.run.source_resource"
        ) as source, patch("Ingestion.run.read_profile") as profile, contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        for name in ("NETSUITE_ACCOUNT_ID", "NETSUITE_CLIENT_ID", "NETSUITE_CERTIFICATE_ID", "NETSUITE_PRIVATE_KEY_PATH"):
            self.assertIn(name, error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        source.assert_not_called()
        profile.assert_not_called()

    def test_missing_dlt_exits_with_install_instructions_before_contacting_source(self):
        error = io.StringIO()
        with patch.object(sys, "argv", ["ingestion", "Ingestion/netsuite.example.yml", "--preview", "5"]), patch(
            "Ingestion.run.importlib.util.find_spec", return_value=None
        ), patch("Ingestion.run.source_resource") as source, contextlib.redirect_stderr(error):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("bash install_tools.sh", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        source.assert_not_called()

    def test_primary_key_required_and_nan_rejected(self):
        for row in ({}, {"id": None}, {"id": math.nan}, []):
            with self.assertRaises(ValueError):
                validate_record(row, "id")
        self.assertEqual(validate_record({"id": 0}, "id"), {"id": 0})
        with self.assertRaises(ValueError):
            validate_record({"id": 1}, ["id", "version"])

    def test_config_prevents_append_without_replay_protection(self):
        config = {"pipeline_name": "demo", "dataset": "raw", "table": "events", "primary_key": "id"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pipeline.yml"
            path.write_text(yaml.safe_dump(config))
            self.assertEqual(read_config(path), config)
            config["write_disposition"] = "append"
            path.write_text(yaml.safe_dump(config))
            with self.assertRaises(ValueError):
                read_config(path)

    def test_profile_selects_target_and_rejects_placeholders(self):
        settings = {"type": "snowflake", "account": "org-account", "user": "tester", "role": "role", "database": "db", "warehouse": "COMPUTE_WH", "schema": "ANALYTICS"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.yml"
            def write():
                path.write_text(yaml.safe_dump({"dbt_project": {"target": "selected", "outputs": {"selected": settings}}}))
            write()
            self.assertEqual(read_profile(path), settings)
            settings["account"] = "YOUR_ACCOUNT_IDENTIFIER"
            write()
            with self.assertRaises(ValueError):
                read_profile(path)

    def test_destination_reuses_profile_without_analytics_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key.p8"
            key.write_text("test-key-fixture")
            mapped = destination_credentials({
                "account": "org-account", "user": "tester", "database": "db",
                "warehouse": "COMPUTE_WH", "schema": "ANALYTICS",
                "authenticator": "snowflake_jwt", "private_key_path": str(key),
                "private_key_passphrase": "test-passphrase",
            })
            self.assertEqual(mapped["host"], "org-account")
            self.assertEqual(mapped["username"], "tester")
            self.assertEqual(mapped["private_key"], "test-key-fixture")
            self.assertNotIn("schema", mapped)  # destination dataset comes from ingestion config
            self.assertNotIn("private_key_path", mapped)

    def test_pending_load_is_recovered_before_new_batch(self):
        dlt = types.ModuleType("dlt")
        destinations = types.ModuleType("dlt.destinations")
        destinations.snowflake = MagicMock()
        pipeline = MagicMock(has_pending_data=True)
        recovered, current = MagicMock(), MagicMock()
        pipeline.run.side_effect = [recovered, current]
        dlt.pipeline = MagicMock(return_value=pipeline)
        config = {"pipeline_name": "demo", "dataset": "raw", "table": "events", "primary_key": "id"}
        batch = iter([{"id": 1}])
        with patch.dict(sys.modules, {"dlt": dlt, "dlt.destinations": destinations}), patch("Ingestion.run.read_profile", return_value={"account": "a", "user": "u"}), contextlib.redirect_stdout(io.StringIO()):
            load(config, batch)
        self.assertEqual(pipeline.run.call_args_list[0].args, ())
        self.assertIs(pipeline.run.call_args_list[1].args[0], batch)
        recovered.raise_on_failed_jobs.assert_called_once()
        current.raise_on_failed_jobs.assert_called_once()
        self.assertEqual(dlt.pipeline.call_args.kwargs["dataset_name"], "raw")

    def test_failed_load_propagates_to_caller(self):
        dlt = types.ModuleType("dlt")
        destinations = types.ModuleType("dlt.destinations")
        destinations.snowflake = MagicMock()
        pipeline = MagicMock(has_pending_data=False)
        pipeline.run.return_value.raise_on_failed_jobs.side_effect = RuntimeError("load failed")
        dlt.pipeline = MagicMock(return_value=pipeline)
        config = {"pipeline_name": "demo", "dataset": "raw", "table": "events", "primary_key": "id"}
        with patch.dict(sys.modules, {"dlt": dlt, "dlt.destinations": destinations}), patch("Ingestion.run.read_profile", return_value={"account": "a", "user": "u"}):
            with self.assertRaisesRegex(RuntimeError, "load failed"):
                load(config, [{"id": 1}])

    def producer(self, rows, failure=False, backpressure=False):
        sent = []
        class Producer:
            def __init__(self, settings):
                self.block = backpressure
            def produce(self, topic, value, key=None, callback=None):
                if self.block:
                    self.block = False
                    raise BufferError()
                sent.append((topic, value, key))
                callback("delivery failed" if failure else None, types.SimpleNamespace(topic=lambda: topic, partition=lambda: 0, offset=lambda: 1))
            def poll(self, timeout):
                pass
            def flush(self, timeout):
                return 0
        module = types.ModuleType("confluent_kafka")
        module.Producer = Producer
        path = Path(__file__).resolve().parents[2] / "Kafka/producer.py"
        with patch.dict(sys.modules, {"confluent_kafka": module}), patch.object(sys, "argv", [str(path), "localhost:9092", "interview", "--key-field", "id"]), patch.object(sys, "stdin", io.StringIO(rows)), contextlib.redirect_stderr(io.StringIO()):
            runpy.run_path(str(path), run_name="__main__")
        return sent

    def test_producer_retries_same_record_and_sets_key(self):
        self.assertEqual(self.producer('{"id": 7}\n', backpressure=True), [("interview", '{"id": 7}', "7")])

    def test_producer_failure_is_not_silent(self):
        with self.assertRaises(SystemExit):
            self.producer('{"id": 7}\n', failure=True)
        with self.assertRaises(SystemExit):
            self.producer('{"wrong_key": 7}\n')


if __name__ == "__main__":
    unittest.main()
