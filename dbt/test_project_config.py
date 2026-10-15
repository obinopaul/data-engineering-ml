"""Exercise dbt debug's strict project-loading path without a cloud connection.

From main/: .venv/bin/python -m unittest discover -s dbt -p 'test_*.py'
"""
from pathlib import Path
from argparse import Namespace
from types import SimpleNamespace
import unittest

from dbt.flags import get_flags, set_flags, set_from_args
from dbt.config.project import Project
from dbt.config.renderer import DbtProjectYamlRenderer


class ProjectConfigTests(unittest.TestCase):
    def setUp(self):
        # Initialize the CLI defaults needed by the project/selector loaders.
        previous_flags = get_flags()
        self.addCleanup(set_flags, previous_flags)
        set_from_args(Namespace(send_anonymous_usage_stats=False), {})

    def test_default_and_explicit_workloads_keep_resources_separate(self):
        profile = SimpleNamespace(to_target_dict=lambda: {
            "schema": "ANALYTICS", "database": "INTERVIEW_DB",
            "type": "snowflake", "name": "test", "threads": 1,
        })
        for variables, workload in [({}, "starter"), ({"workload": "starter"}, "starter"),
                                    ({"workload": "demo"}, "demo"),
                                    ({"workload": "events"}, "events")]:
            with self.subTest(variables=variables):
                # Same loader/strict renderer used by DebugTask._load_project.
                project = Project.from_project_root(
                    str(Path(__file__).resolve().parent),
                    DbtProjectYamlRenderer(profile, variables),
                )
                models = project.models["dbt_project"]
                seeds = project.seeds["dbt_project"]
                snapshots = project.snapshots["dbt_project"]
                self.assertEqual(models["example"]["+enabled"], workload == "starter")
                self.assertEqual(models["events"]["+enabled"], workload != "starter")
                self.assertEqual(seeds["demo"]["+enabled"], workload == "demo")
                self.assertEqual(seeds["reference"]["+enabled"], workload != "starter")
                self.assertEqual(snapshots["+enabled"], workload != "starter")
                for config in (models["events"], seeds, snapshots):
                    self.assertEqual(config["+schema"], f"ANALYTICS_{workload}")


if __name__ == "__main__":
    unittest.main()
