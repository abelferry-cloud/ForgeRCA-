"""Offline migration and connection contracts; no database or corpus required."""

import importlib.util
import io
import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import ConfigError, Secret, Settings

ROOT = Path(__file__).resolve().parents[1]
HAS_DB = all(importlib.util.find_spec(name) for name in ("sqlalchemy", "alembic", "psycopg"))


@unittest.skipUnless(HAS_DB, "Run with uv sync --frozen for PostgreSQL dependencies")
class DatabaseSchemaTests(unittest.TestCase):
    def test_structured_url_preserves_special_characters_without_printing_credentials(self):
        from app.db.connection import database_url

        value = "fixture@:/%#" + "保密" * 4
        fixture = Secret.of(value)
        settings = Settings(postgres_user="fixture-user", postgres_password=fixture, postgres_port=55432)
        url = database_url(settings)
        self.assertEqual(url.password, value)
        self.assertEqual((url.drivername, url.port, url.database), ("postgresql+psycopg", 55432, "forgerca"))
        self.assertNotIn(value, str(url))
        self.assertNotIn(value, repr(url))

    def test_missing_password_fails_before_engine_creation(self):
        from app.db.connection import create_db_engine

        with patch.dict(os.environ, {}, clear=True), patch("app.db.connection.sa.create_engine") as create:
            with self.assertRaisesRegex(ConfigError, "POSTGRES_PASSWORD"):
                create_db_engine()
            create.assert_not_called()

    def test_engine_hides_parameters_and_bounds_connection_wait(self):
        from app.db.connection import create_db_engine

        settings = Settings(postgres_password=Secret.of("synthetic"))
        with patch("app.db.connection.sa.create_engine") as create:
            create_db_engine(settings)
        self.assertTrue(create.call_args.kwargs["hide_parameters"])
        self.assertEqual(create.call_args.kwargs["connect_args"], {"connect_timeout": 10})

    def test_offline_upgrade_works_without_credentials_and_keeps_frozen_revision(self):
        import sqlalchemy as sa
        from alembic import command
        from alembic.config import Config

        from app.db import schema

        output = io.StringIO()
        config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
        # A historical revision must not create whatever happens to be in today's metadata.
        with patch.dict(os.environ, {}, clear=True), patch.object(schema, "metadata", sa.MetaData()):
            command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        for name in ("document", "chunk", "asset", "work_order", "alarm", "ingest_run", "diagnosis_run"):
            self.assertIn(f"CREATE TABLE {name} (", sql)
        self.assertIn("JSONB", sql)
        self.assertIn("TIMESTAMP WITH TIME ZONE", sql)
        self.assertIn("PRIMARY KEY (document_key, evidence_id)", sql)
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)

    def test_offline_downgrade_drops_children_before_parents(self):
        from alembic import command
        from alembic.config import Config

        output = io.StringIO()
        command.downgrade(Config(str(ROOT / "alembic.ini"), output_buffer=output), "0001:base", sql=True)
        sql = output.getvalue()
        self.assertLess(sql.index("DROP TABLE alarm"), sql.index("DROP TABLE work_order"))
        self.assertLess(sql.index("DROP TABLE chunk"), sql.index("DROP TABLE document"))
        self.assertLess(sql.index("DROP TABLE diagnosis_run"), sql.index("DROP TABLE asset"))

    def test_locked_migration_tool_matches_artifact_pin(self):
        lock = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))
        packages = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        package = next(item for item in packages if item["name"] == "alembic")
        pin = lock["packages"]["alembic"]
        self.assertEqual(package["version"], pin["version"])
        self.assertIn((pin["url"], "sha256:" + pin["sha256"]),
                      [(wheel["url"], wheel["hash"]) for wheel in package["wheels"]])
