"""Shared Snowflake login, one-time bootstrap, and dbt launcher.

Run from main/: python Snowflake/connection.py --help
No connection is opened on import. Secrets stay in the local .env/profile.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENV_REF = re.compile(r"\{\{\s*env_var\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\)\s*\}\}")


def load_local_env():
    """Read .env as data, never as shell commands; keep existing exported values."""
    if (ROOT / ".env").exists():
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False, interpolate=False)


def read_profile(profile_path=None):
    """Read YAML and resolve only exact {{ env_var('NAME') }} references."""
    if profile_path is None:
        load_local_env()
    profile_path = Path(profile_path or ROOT / "dbt/profiles.yml")
    if not profile_path.exists():
        raise FileNotFoundError("Copy dbt/profiles.example.yml to dbt/profiles.yml first.")
    profile = yaml.safe_load(profile_path.read_text())["dbt_project"]
    settings = dict(profile["outputs"][profile["target"]])
    if settings["type"] != "snowflake":
        raise ValueError("The selected dbt profile must use type: snowflake")
    for key, value in settings.items():
        if isinstance(value, str) and "{{" in value:
            match = ENV_REF.fullmatch(value)
            if not match:
                raise ValueError("Use plain YAML or an exact env_var('NAME') reference.")
            variable = match.group(1)
            if not os.environ.get(variable):
                raise ValueError(f"Set {variable} in main/.env or your terminal first.")
            settings[key] = os.environ[variable]
    for key in ("account", "user", "database", "warehouse", "role", "schema"):
        if not settings.get(key) or str(settings[key]).startswith("YOUR_"):
            raise ValueError(f"Fill in {key} in dbt/profiles.yml first.")
    return settings


def connector_options(settings, *, login_only=False, setup=False):
    keys = ("account", "user", "role", "warehouse", "database", "schema", "authenticator")
    config = {key: settings[key] for key in keys if key in settings}
    auth = str(settings.get("authenticator", "snowflake")).lower()
    if auth in ("snowflake", "username_password_mfa") and "password" in settings:
        config["password"] = settings["password"]
    if "private_key_path" in settings:
        config["private_key_file"] = str(Path(settings["private_key_path"]).expanduser())
    if "private_key_passphrase" in settings:
        config["private_key_file_pwd"] = settings["private_key_passphrase"]
    config.update(login_timeout=60, network_timeout=30)
    if login_only or setup:
        # These objects may not exist yet. Authenticate before selecting them.
        for key in ("role", "warehouse", "database", "schema"):
            config.pop(key, None)
    if setup:
        config["role"] = "ACCOUNTADMIN"
    return config


def connect(*, login_only=False, setup=False):
    import snowflake.connector

    return snowflake.connector.connect(
        **connector_options(read_profile(), login_only=login_only, setup=setup)
    )


def bootstrap():
    settings = read_profile()
    expected = {"role": "INTERVIEW_ROLE", "database": "INTERVIEW_DB",
                "warehouse": "COMPUTE_WH", "schema": "ANALYTICS"}
    if any(str(settings.get(k, "")).upper() != value for k, value in expected.items()):
        raise ValueError("Setup SQL targets INTERVIEW_DB / INTERVIEW_ROLE / COMPUTE_WH / ANALYTICS. Review it for other profile names.")
    with connect(setup=True) as connection:
        cursors = connection.execute_string(
            (ROOT / "Snowflake/sql/000_bootstrap.sql").read_text()
        )
        try:
            print("Setup completed; RAW and ANALYTICS write checks:", cursors[-1].fetchone())
        finally:
            for cursor in cursors:
                cursor.close()


def run_dbt(arguments):
    load_local_env()
    executable = ROOT / ".venv/bin/dbt"
    if not executable.is_file():
        raise FileNotFoundError("dbt is not installed in .venv. Run bash install_tools.sh.")
    return subprocess.run(
        [str(executable), *arguments, "--project-dir", str(ROOT / "dbt"),
         "--profiles-dir", str(ROOT / "dbt")], cwd=ROOT, check=False,
    ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--login-only", action="store_true", help="Authenticate before role/database creation")
    modes.add_argument("--setup", action="store_true", help="Run bootstrap SQL using your ACCOUNTADMIN access")
    modes.add_argument("--dbt", nargs=argparse.REMAINDER, help="Run dbt with .env loaded, e.g. --dbt debug")
    args = parser.parse_args()
    if args.dbt is not None:
        if not args.dbt:
            parser.error("Provide a dbt command, such as --dbt debug")
        return run_dbt(args.dbt)
    if args.setup:
        bootstrap()
    else:
        with connect(login_only=args.login_only) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE()")
                print("Connected (user, role, database, schema, warehouse):", cursor.fetchone())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        message = str(exc)
        for name in ("SNOWFLAKE_PASSWORD", "SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
            if os.environ.get(name):
                message = message.replace(os.environ[name], "[redacted]")
        sys.exit(f"Snowflake command failed ({type(exc).__name__}): {message}")
