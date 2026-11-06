"""Destructive integration test, explicitly enabled only for a disposable database."""

import importlib.util
import os
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
HAS_DB = all(importlib.util.find_spec(name) for name in ("sqlalchemy", "alembic", "psycopg"))


@unittest.skipUnless(HAS_DB and os.environ.get("FORGERCA_TEST_POSTGRES") == "1",
                     "PostgreSQL integration requires an explicitly enabled disposable database")
class PostgreSQLMigrationTests(unittest.TestCase):
    def test_upgrade_constraints_and_downgrade_roundtrip(self):
        import sqlalchemy as sa
        from alembic import command
        from alembic.config import Config
        from alembic.migration import MigrationContext

        from app.db import schema as db
        from app.db.connection import create_db_engine

        engine = create_db_engine()
        self.addCleanup(engine.dispose)
        self.assertEqual(engine.url.database, "forgerca_test", "Refusing to change a non-test database")
        with engine.connect() as connection:
            self.assertLessEqual(set(sa.inspect(connection).get_table_names()), {"alembic_version"},
                                 "Use a new empty test database")
            self.assertIsNone(MigrationContext.configure(connection).get_current_revision())
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        self.addCleanup(command.downgrade, config, "base")
        command.check(config)
        with engine.connect() as connection:
            self.assertEqual(set(sa.inspect(connection).get_table_names()),
                             set(db.metadata.tables) | {"alembic_version"})
            self.assertEqual(MigrationContext.configure(connection).get_current_revision(), "0001")

        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        key = "SYNTHETIC@A:" + "a" * 64
        doc = {"document_key": key, "source_id": "SYNTHETIC", "document_code": "SYNTHETIC-MANUAL",
               "revision": "A", "sha256": "a" * 64, "models": ["TEST-MODEL"], "firmware_scope": None,
               "source_url": "https://example.com/manual.pdf", "accessed_at": date(2026, 1, 1),
               "source_metadata": {"synthetic_fixture": True}}
        evidence = {"document_key": key, "evidence_id": "ev1:" + "b" * 64, "chunk_type": "section",
                    "text": "合成测试证据", "evidence_locator": {"version": 1, "source_id": "SYNTHETIC"},
                    "locations": [{"pdf_page": 1, "printed_page": None}], "section": [],
                    "source_refs": ["#/texts/0"], "heading_refs": [], "table_row": None,
                    "fault_codes": [], "safety_labels": ["warning"]}
        asset = {"asset_id": "SYN-1", "model": "TEST-MODEL", "synthetic": True}
        work = {**asset, "work_order_id": "WO1", "incident_group": "history-1", "firmware_version": None,
                "alarm_code": "00a1", "opened_at": timestamp, "closed_at": timestamp + timedelta(hours=2),
                "available_at": timestamp + timedelta(hours=2), "observations": ["合成观察"],
                "confirmed_cause": "synthetic_cause", "action": "合成动作", "outcome": "合成结果",
                "text": "合成历史记录", "locator": {"record_id": "WO1"}}
        alarm = {**asset, "alarm_id": "AL1", "incident_group": "history-1", "firmware_version": None,
                 "work_order_id": "WO1", "alarm_code": "00a1", "occurred_at": timestamp + timedelta(hours=1),
                 "available_at": timestamp + timedelta(hours=1), "text": "合成告警", "locator": {"record_id": "AL1"}}
        ingest = {"ingest_run_id": uuid4(), "document_key": key, "input_path": "data/processed/synthetic.json",
                  "input_sha256": "c" * 64, "parser": {"synthetic": True}, "started_at": timestamp}
        evidence["ingest_run_id"] = ingest["ingest_run_id"]
        diagnosis = {"diagnosis_id": uuid4(), "asset_id": "SYN-1", "model": "TEST-MODEL",
                     "firmware_version": None, "as_of": timestamp, "request": {"query": "合成问题"},
                     "runtime_config": {"synthetic": True}, "started_at": timestamp}
        with engine.begin() as connection:
            for table, record in ((db.document, doc), (db.ingest_run, ingest), (db.chunk, evidence), (db.asset, asset),
                                  (db.work_order, work), (db.alarm, alarm),
                                  (db.diagnosis_run, diagnosis)):
                connection.execute(table.insert().values(**record))
            # A revision label can change without changing PDF bytes or the physical evidence ID.
            second_key = key.replace("@A:", "@B:")
            second_run = uuid4()
            connection.execute(db.document.insert().values(**{
                **doc, "revision": "B", "document_key": second_key,
            }))
            connection.execute(db.ingest_run.insert().values(**{
                **ingest, "ingest_run_id": second_run, "document_key": second_key,
            }))
            connection.execute(db.chunk.insert().values(**{
                **evidence, "document_key": second_key, "ingest_run_id": second_run,
            }))
            connection.execute(db.alarm.insert().values(**{**alarm, "alarm_id": "AL2", "work_order_id": None}))
            connection.execute(db.ingest_run.update().values(run_status="succeeded", finished_at=timestamp))
            connection.execute(db.diagnosis_run.update().values(
                run_status="succeeded", status="insufficient", response={"status": "insufficient"},
                finished_at=timestamp,
            ))
            connection.execute(db.ingest_run.insert().values(**{
                **ingest, "ingest_run_id": uuid4(), "document_key": None, "run_status": "failed",
                "finished_at": timestamp, "error_code": "synthetic_failure",
            }))
        invalid = [
            (db.document, doc),
            (db.document, {**doc, "sha256": "d" * 64, "document_key": "SYNTHETIC@A:" + "d" * 64}),
            (db.document, {**doc, "document_key": "wrong-key", "revision": "C"}),
            (db.document, {**doc, "document_key": key.replace("@A:", "@C:"), "revision": "C", "models": {}}),
            (db.chunk, evidence),
            (db.chunk, {**evidence, "document_key": "MISSING@A:" + "a" * 64}),
            (db.chunk, {**evidence, "evidence_id": "not-an-evidence-id"}),
            (db.chunk, {**evidence, "evidence_id": "ev1:" + "d" * 64, "ingest_run_id": second_run}),
            (db.chunk, {**evidence, "evidence_id": "ev1:" + "d" * 64, "locations": []}),
            (db.chunk, {**evidence, "evidence_id": "ev1:" + "d" * 64, "safety_labels": {}}),
            (db.work_order, {**work, "work_order_id": "WO2", "synthetic": False}),
            (db.work_order, {**work, "work_order_id": "WO2", "model": "WRONG-MODEL"}),
            (db.work_order, {**work, "work_order_id": "WO2", "available_at": timestamp}),
            (db.work_order, {**work, "work_order_id": "WO2", "closed_at": timestamp - timedelta(seconds=1)}),
            (db.alarm, {**alarm, "alarm_id": "AL3", "incident_group": "wrong-incident"}),
            (db.alarm, {**alarm, "alarm_id": "AL3", "work_order_id": "MISSING"}),
            (db.alarm, {**alarm, "alarm_id": "AL3", "available_at": timestamp}),
            (db.ingest_run, {**ingest, "ingest_run_id": uuid4(), "run_status": "succeeded"}),
            (db.ingest_run, {**ingest, "ingest_run_id": uuid4(), "input_sha256": "short"}),
            (db.diagnosis_run, {**diagnosis, "diagnosis_id": uuid4(), "run_status": "succeeded",
                                "finished_at": timestamp}),
            (db.diagnosis_run, {**diagnosis, "diagnosis_id": uuid4(), "status": "supported"}),
            (db.diagnosis_run, {**diagnosis, "diagnosis_id": uuid4(), "response": []}),
        ]
        for index, (table, record) in enumerate(invalid):
            with self.subTest(table=table.name, case=index), self.assertRaises(sa.exc.IntegrityError):
                with engine.begin() as connection:
                    connection.execute(table.insert().values(**record))
        with self.assertRaises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(db.document.delete().where(db.document.c.document_key == key))
        # Re-applying the revision must preserve data, not recreate the tables.
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            self.assertEqual(connection.scalar(sa.select(sa.func.count()).select_from(db.chunk)), 2)
            row = connection.execute(sa.select(db.chunk).where(db.chunk.c.document_key == key)).mappings().one()
            self.assertEqual(row["text"], evidence["text"])
            self.assertEqual(row["locations"], evidence["locations"])
            self.assertIsNone(row["table_row"])
            self.assertIsNotNone(row["created_at"].tzinfo)
            self.assertEqual(connection.scalar(sa.select(db.work_order.c.alarm_code)), "00a1")
        command.downgrade(config, "base")
        with engine.connect() as connection:
            self.assertEqual(sa.inspect(connection).get_table_names(), ["alembic_version"])
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            for table in db.metadata.tables.values():
                self.assertEqual(connection.scalar(sa.select(sa.func.count()).select_from(table)), 0)
