"""Offline authentication/bootstrap checks; never contact Snowflake."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

from Snowflake.connection import bootstrap, connector_options, read_profile, run_dbt


class ConnectionTests(unittest.TestCase):
    def settings(self):
        return dict(
            type="snowflake", account="org-account", user="tester",
            role="INTERVIEW_ROLE", database="INTERVIEW_DB", schema="ANALYTICS",
            warehouse="COMPUTE_WH", authenticator="username_password_mfa",
            password="test-fixture-only",
        )

    def test_login_does_not_require_uncreated_objects(self):
        config = connector_options(self.settings(), login_only=True)
        for field in ("role", "database", "schema", "warehouse"):
            self.assertNotIn(field, config)
        self.assertEqual(config["password"], "test-fixture-only")

    def test_admin_context_is_only_used_for_setup(self):
        self.assertEqual(connector_options(self.settings())["role"], "INTERVIEW_ROLE")
        setup = connector_options(self.settings(), setup=True)
        self.assertEqual(setup["role"], "ACCOUNTADMIN")
        self.assertNotIn("database", setup)

    def test_password_is_not_sent_with_browser_or_keypair(self):
        for auth in ("externalbrowser", "snowflake_jwt"):
            settings = self.settings()
            settings["authenticator"] = auth
            self.assertNotIn("password", connector_options(settings))

    def test_env_reference_resolves_without_evaluating_other_jinja(self):
        settings = self.settings()
        settings["password"] = "{{ env_var('TEST_SNOWFLAKE_SECRET') }}"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profiles.yml"
            def write():
                path.write_text(yaml.safe_dump({"dbt_project": {
                    "target": "test", "outputs": {"test": settings},
                }}))
            write()
            with patch.dict(os.environ, {"TEST_SNOWFLAKE_SECRET": "fixture"}):
                self.assertEqual(read_profile(path)["password"], "fixture")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "TEST_SNOWFLAKE_SECRET"):
                    read_profile(path)
            settings["password"] = "{{ unsupported_expression() }}"
            write()
            with self.assertRaises(ValueError):
                read_profile(path)

    def test_bootstrap_rejects_other_target_names_before_connecting(self):
        settings = self.settings()
        settings["database"] = "SOME_EXISTING_DB"
        with patch("Snowflake.connection.read_profile", return_value=settings), patch("Snowflake.connection.connect") as connect:
            with self.assertRaises(ValueError):
                bootstrap()
            connect.assert_not_called()

    def test_dbt_loads_env_and_returns_failure_exit_code(self):
        with patch("Snowflake.connection.load_local_env") as load_env, patch.object(Path, "is_file", return_value=True), patch("Snowflake.connection.subprocess.run", return_value=MagicMock(returncode=2)) as run:
            self.assertEqual(run_dbt(["build"]), 2)
            load_env.assert_called_once()
            command = run.call_args.args[0]
            self.assertTrue(command[0].endswith("/.venv/bin/dbt"))
            self.assertIn("--profiles-dir", command)
            self.assertNotIn("shell", run.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
