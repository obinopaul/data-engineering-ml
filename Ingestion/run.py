"""Use dlt's REST/SQL/filesystem sources and Snowflake loader.

Upstream: https://github.com/dlt-hub/dlt (Apache-2.0).
These workspace adapters configure the library; they do not vendor its code.
Run from main/: python -m Ingestion.run Ingestion/pipeline.yml
"""
import argparse
import importlib.util
import json
import math
import os
import re
from datetime import date, datetime
from itertools import islice
from pathlib import Path

import yaml

from Snowflake.connection import load_local_env, read_profile

ROOT = Path(__file__).resolve().parents[1]


def read_config(path):
    config = yaml.safe_load(Path(path).read_text())
    if not isinstance(config, dict):
        raise ValueError("The ingestion configuration must be a YAML mapping.")
    for name in ("pipeline_name", "dataset", "table"):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(config.get(name, ""))):
            raise ValueError(f"{name} must be a lowercase SQL identifier.")
    if config.get("write_disposition", "merge") != "merge":
        raise ValueError("This starter uses merge; set a stable primary_key.")
    keys = config.get("primary_key")
    keys = [keys] if isinstance(keys, str) else keys
    if (
        not isinstance(keys, list)
        or not keys
        or any(not isinstance(k, str) or not k for k in keys)
    ):
        raise ValueError("Set primary_key to the source's stable record/event identifier.")
    return config


def validate_record(record, primary_key):
    keys = [primary_key] if isinstance(primary_key, str) else primary_key
    if not isinstance(record, dict) or any(
        record.get(k) is None or (isinstance(record.get(k), float) and math.isnan(record[k]))
        for k in keys
    ):
        raise ValueError("A record is missing its primary key; check the source schema.")
    return record


def normalize_missing(value):
    """Represent pandas CSV NaN cells as null for JSON and destination loading."""
    if isinstance(value, dict):
        return {key: normalize_missing(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_missing(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def source_resource(config):
    import dlt

    source = config["source"]
    kind = source["type"]
    if kind in ("rest", "sql", "netsuite", "adp"):
        # Source credentials are needed for preview/export too.
        load_local_env()
    if kind == "rest":
        from dlt.sources.rest_api import rest_api_resources

        client = {"base_url": source["base_url"]}
        if source.get("token_env"):
            client["auth"] = {"type": "bearer", "token": os.environ[source["token_env"]]}
        # endpoint is dlt's native config: path, params, data_selector, paginator.
        resource = rest_api_resources(
            {
                "client": client,
                "resources": [{"name": config["table"], "endpoint": source["endpoint"]}],
            }
        )[0]
    elif kind == "files":
        from dlt.sources.filesystem import filesystem, read_csv, read_jsonl, read_parquet

        readers = {"csv": read_csv, "parquet": read_parquet, "jsonl": read_jsonl}
        location = source["location"]
        if "://" not in location:
            location = (ROOT / location).resolve().as_uri()
        files = filesystem(bucket_url=location, file_glob=source["glob"])
        reader = readers[source["format"]](**source.get("reader_options", {}))
        resource = (files | reader).with_name(config["table"])
    elif kind == "excel":
        import pandas as pd

        def rows():
            frame = pd.read_excel(ROOT / source["path"], sheet_name=source.get("sheet", 0))
            yield frame.astype(object).where(frame.notna(), None).to_dict("records")

        resource = dlt.resource(rows, name=config["table"])
    elif kind == "sql":
        from dlt.sources.sql_database import sql_table

        resource = sql_table(
            credentials=os.environ[source["connection_env"]],
            table=source["table"],
            schema=source.get("schema"),
            chunk_size=10000,
        ).with_name(config["table"])
    elif kind in ("netsuite", "adp"):
        from Ingestion.vendor_sources import adp_rows, netsuite_rows

        reader = {"netsuite": netsuite_rows, "adp": adp_rows}[kind]
        resource = dlt.resource(reader(source), name=config["table"])
    else:
        raise ValueError("source.type must be rest, files, excel, sql, netsuite or adp")
    resource.apply_hints(primary_key=config["primary_key"], write_disposition="merge")
    resource.add_map(normalize_missing)
    resource.add_map(lambda row: validate_record(row, config["primary_key"]))
    return resource


def destination_credentials(settings):
    """Translate dbt field names to dlt; keep the same account/authentication."""
    credentials = {"host": settings["account"], "username": settings["user"]}
    for key in ("database", "warehouse", "role", "authenticator", "private_key_passphrase"):
        if key in settings:
            credentials[key] = settings[key]
    if settings.get("authenticator", "snowflake").lower() in ("snowflake", "username_password_mfa"):
        if "password" in settings:
            credentials["password"] = settings["password"]
    if settings.get("private_key_path"):
        key_path = Path(settings["private_key_path"]).expanduser()
        credentials["private_key"] = key_path.read_text("ascii")
    return credentials


def load(config, resource, columns=None):
    import dlt
    from dlt.destinations import snowflake

    pipeline = dlt.pipeline(
        pipeline_name=config["pipeline_name"],
        pipelines_dir=str(ROOT / ".cache/dlt"),
        destination=snowflake(
            credentials=destination_credentials(read_profile()),
            keep_staged_files=False,
        ),
        dataset_name=config["dataset"],
    )
    # Recover interrupted loads before supplying this batch's iterator.
    if pipeline.has_pending_data:
        recovered = pipeline.run()
        if recovered is not None:
            recovered.raise_on_failed_jobs()
    info = pipeline.run(
        resource,
        table_name=config["table"],
        primary_key=config["primary_key"],
        write_disposition="merge",
        columns=columns,
    )
    if info is not None:
        info.raise_on_failed_jobs()
        print(info)
    else:
        print("No load produced; check source availability before running dbt.")
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--unattended", action="store_true",
        help="Reject interactive browser/MFA login in scheduled jobs",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview", type=int, metavar="ROWS",
        help="Read a sample; do not write Snowflake",
    )
    mode.add_argument(
        "--jsonl", action="store_true",
        help="Extract records to stdout for Kafka; no warehouse load",
    )
    args = parser.parse_args()
    if importlib.util.find_spec("dlt") is None:
        parser.error(
            "dlt is not installed in this Python environment. From main/, run "
            "'bash install_tools.sh', then 'source .venv/bin/activate'. "
            "If installation fails, fix that error before retrying ingestion."
        )
    if args.preview is not None and args.preview < 1:
        parser.error("--preview must be positive")
    config = read_config(args.config)
    kind = config.get("source", {}).get("type")
    if kind in ("netsuite", "adp"):
        from Ingestion.vendor_sources import validate_vendor_setup

        load_local_env()
        try:
            validate_vendor_setup(kind)
        except ValueError as error:
            parser.error(str(error))
    # Fail before contacting the source if the destination is not configured.
    if args.preview is None and not args.jsonl:
        settings = read_profile()
        interactive_auth = settings.get("authenticator", "").lower() in (
            "externalbrowser", "username_password_mfa",
        )
        if args.unattended and interactive_auth:
            parser.error("Use key-pair authentication for unattended runs.")
    resource = source_resource(config)
    if args.preview is not None or args.jsonl:
        records = iter(resource)
        if args.preview is not None:
            records = islice(records, args.preview)
        for row in records:
            print(json.dumps(row, default=json_value, allow_nan=False), flush=True)
    else:
        load(config, resource)


def json_value(value):
    """Keep source datetime values usable by JSON/Spark timestamp readers."""
    return value.isoformat() if isinstance(value, (date, datetime)) else str(value)


if __name__ == "__main__":
    main()
