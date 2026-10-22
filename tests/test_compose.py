"""Validate Compose interpolation without a daemon or local credentials."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ComposeConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker Compose CLI is not installed")
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=20)
        if result.returncode:
            raise unittest.SkipTest("Docker Compose CLI is not installed")

    def compose_config(self, overrides=None):
        # Explicit template and environment: never read the developer's .env.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("POSTGRES_", "OPENSEARCH_", "NEO4J_", "COMPOSE_"))
        }
        env.update({"POSTGRES_PASSWORD": "example-pg", "NEO4J_PASSWORD": "example-neo4j"})
        for key, value in (overrides or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [
                "docker", "compose", "--project-name", "forgerca-config-test",
                "--env-file", str(ROOT / ".env.example"), "-f", str(ROOT / "compose.yaml"),
                "config", "--format", "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def services(self, overrides=None):
        result = self.compose_config(overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["services"]

    def test_ports_stay_on_loopback_with_defaults_and_overrides(self):
        cases = (
            ({}, {"postgres": [5432], "opensearch": [9200], "neo4j": [7474, 7687]}),
            (
                {
                    "POSTGRES_PORT": "15432", "OPENSEARCH_PORT": "19200",
                    "NEO4J_HTTP_PORT": "17474", "NEO4J_BOLT_PORT": "17687",
                },
                {"postgres": [15432], "opensearch": [19200], "neo4j": [17474, 17687]},
            ),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                services = self.services(overrides)
                self.assertEqual(set(services), set(expected))
                for name, ports in expected.items():
                    published = services[name]["ports"]
                    self.assertEqual(sorted(int(port["published"]) for port in published), sorted(ports))
                    self.assertTrue(all(port["host_ip"] == "127.0.0.1" for port in published))

    def test_missing_or_empty_credentials_fail_before_startup(self):
        for name in ("POSTGRES_PASSWORD", "NEO4J_PASSWORD"):
            for value in (None, ""):
                with self.subTest(name=name, value=value):
                    result = self.compose_config({name: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name, result.stderr)

    def test_credentials_are_not_interpolated_into_health_commands(self):
        sample = "example-$DOLLAR with space;value"
        services = self.services({"POSTGRES_PASSWORD": sample, "NEO4J_PASSWORD": sample})
        # `config` escapes dollars so its output can be parsed again as Compose.
        serialized = sample.replace("$", "$$")
        self.assertEqual(services["postgres"]["environment"]["POSTGRES_PASSWORD"], serialized)
        self.assertEqual(services["neo4j"]["environment"]["HEALTH_PASSWORD"], serialized)
        for service in services.values():
            self.assertNotIn(sample, str(service["healthcheck"]["test"]))
            self.assertNotIn(serialized, str(service["healthcheck"]["test"]))

    def test_neo4j_bootstrap_user_is_fixed_even_with_a_different_client_user(self):
        neo4j = self.services({"NEO4J_USER": "application-user"})["neo4j"]
        self.assertEqual(neo4j["environment"]["NEO4J_AUTH"], "neo4j/example-neo4j")
        self.assertEqual(neo4j["environment"]["HEALTH_USER"], "neo4j")


if __name__ == "__main__":
    unittest.main()
