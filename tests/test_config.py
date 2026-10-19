"""Tests for typed settings and secret handling (M1-03)."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from app.config import ConfigError, Secret, Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# Kept next to the template on purpose: the test below fails when the two drift.
EXPECTED_DEFAULTS: dict[str, object] = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": 5432,
    "POSTGRES_DB": "forgerca",
    "POSTGRES_USER": "forgerca",
    "POSTGRES_PASSWORD": "",
    "OPENSEARCH_HOST": "localhost",
    "OPENSEARCH_PORT": 9200,
    "OPENSEARCH_USER": "",
    "OPENSEARCH_PASSWORD": "",
    "OPENSEARCH_INDEX_PREFIX": "forgerca",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "",
    "EMBEDDING_MODEL": "",
    "RERANKER_MODEL": "",
    "LLM_PROVIDER": "",
    "LLM_MODEL": "",
    "LLM_API_KEY": "",
    "LANGFUSE_HOST": "",
    "LANGFUSE_PUBLIC_KEY": "",
    "LANGFUSE_SECRET_KEY": "",
}


def parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


class SettingsDefaultsTests(unittest.TestCase):
    def test_defaults_match_env_example(self):
        documented = parse_env_example()
        self.assertEqual(set(documented), set(EXPECTED_DEFAULTS))
        settings = Settings()
        for name, expected in EXPECTED_DEFAULTS.items():
            with self.subTest(name=name):
                actual = getattr(settings, name.lower())
                if isinstance(actual, Secret):
                    self.assertEqual(actual.reveal(), expected)
                else:
                    self.assertEqual(actual, expected)

    def test_redacted_covers_every_documented_variable(self):
        self.assertEqual(set(Settings().redacted()), set(parse_env_example()))

    def test_settings_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            Settings().postgres_host = "elsewhere"  # type: ignore[misc]


class SettingsParsingTests(unittest.TestCase):
    def test_environment_overrides_are_typed(self):
        settings = Settings.from_env(
            {
                "POSTGRES_HOST": "db.internal",
                "POSTGRES_PORT": "6543",
                "OPENSEARCH_INDEX_PREFIX": "  staging  ",
                "LLM_MODEL": "example-model-v1",
            }
        )
        self.assertEqual(settings.postgres_host, "db.internal")
        self.assertEqual(settings.postgres_port, 6543)
        self.assertEqual(settings.opensearch_index_prefix, "staging")
        self.assertEqual(settings.llm_model, "example-model-v1")

    def test_invalid_port_names_the_variable_without_echoing_the_value(self):
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env({"POSTGRES_PORT": "p@ssw0rd-do-not-log"})
        message = str(caught.exception)
        self.assertIn("POSTGRES_PORT", message)
        self.assertNotIn("p@ssw0rd", message)

    def test_port_out_of_range_is_rejected(self):
        for raw in ("0", "65536", "-1"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ConfigError, "between 1 and 65535"):
                Settings.from_env({"OPENSEARCH_PORT": raw})

    def test_blank_values_fall_back_to_defaults(self):
        settings = Settings.from_env({"POSTGRES_DB": "   ", "NEO4J_USER": ""})
        self.assertEqual(settings.postgres_db, "forgerca")
        self.assertEqual(settings.neo4j_user, "neo4j")

    def test_unknown_variables_are_ignored(self):
        settings = Settings.from_env({"PATH": "/usr/bin", "RANDOM_UNRELATED": "x"})
        self.assertEqual(settings, Settings())


class RequiredVariableTests(unittest.TestCase):
    def test_missing_required_variables_are_listed_together(self):
        with self.assertRaises(ConfigError) as caught:
            Settings.from_env({}, required=("POSTGRES_PASSWORD", "NEO4J_PASSWORD"))
        message = str(caught.exception)
        self.assertIn("POSTGRES_PASSWORD", message)
        self.assertIn("NEO4J_PASSWORD", message)

    def test_blank_required_variable_counts_as_missing(self):
        with self.assertRaisesRegex(ConfigError, "POSTGRES_PASSWORD"):
            Settings.from_env({"POSTGRES_PASSWORD": "   "}, required=("POSTGRES_PASSWORD",))

    def test_required_variable_present_passes(self):
        settings = Settings.from_env({"POSTGRES_PASSWORD": "x"}, required=("POSTGRES_PASSWORD",))
        self.assertTrue(settings.postgres_password)


class SecretTests(unittest.TestCase):
    def test_repr_and_str_never_contain_the_value(self):
        settings = Settings.from_env(
            {
                "POSTGRES_PASSWORD": "pg-super-secret-123",
                "LLM_API_KEY": "sk-live-should-not-appear",
                "LANGFUSE_SECRET_KEY": "lf-secret-value",
            }
        )
        for rendered in (repr(settings), str(settings), f"{settings}"):
            self.assertNotIn("pg-super-secret-123", rendered)
            self.assertNotIn("sk-live-should-not-appear", rendered)
            self.assertNotIn("lf-secret-value", rendered)
        self.assertIn("Secret(***)", repr(settings))

    def test_redacted_masks_secrets_and_keeps_plain_values(self):
        settings = Settings.from_env(
            {"POSTGRES_HOST": "db.internal", "POSTGRES_PASSWORD": "pg-super-secret-123"}
        )
        redacted = settings.redacted()
        self.assertEqual(redacted["POSTGRES_HOST"], "db.internal")
        self.assertEqual(redacted["POSTGRES_PASSWORD"], "***")
        self.assertIsNone(redacted["NEO4J_PASSWORD"])
        self.assertNotIn("pg-super-secret-123", str(redacted))

    def test_secret_truthiness_reflects_presence(self):
        self.assertFalse(Secret.of(None))
        self.assertFalse(Secret.of(""))
        self.assertTrue(Secret.of("value"))
        self.assertEqual(len(Secret.of("value")), 5)


if __name__ == "__main__":
    unittest.main()
