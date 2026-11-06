"""Real PostgreSQL transaction, conflict and concurrent replay tests."""

import importlib.util
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier

from scripts.ingest import load_snapshot
from test_ingest import seed_events, write_snapshot

ROOT = Path(__file__).resolve().parents[1]
HAS_DB = all(importlib.util.find_spec(name) for name in ("sqlalchemy", "alembic", "psycopg"))


@unittest.skipUnless(HAS_DB and os.environ.get("FORGERCA_TEST_POSTGRES") == "1",
                     "PostgreSQL integration requires an explicitly enabled disposable database")
class ImportTransactionTests(unittest.TestCase):
    def setUp(self):
        import sqlalchemy as sa
        from alembic import command
        from alembic.config import Config
        from alembic.migration import MigrationContext

        from app.db import schema as db
        from app.db.connection import create_db_engine
        from app.ingestion.importer import import_seed_events, import_snapshot

        self.sa, self.db = sa, db
        self.import_snapshot, self.import_events = import_snapshot, import_seed_events
        self.engine = create_db_engine()
        self.addCleanup(self.engine.dispose)
        self.assertEqual(self.engine.url.database, "forgerca_test", "Refusing to change a non-test database")
        with self.engine.connect() as connection:
            self.assertLessEqual(set(sa.inspect(connection).get_table_names()), {"alembic_version"})
            self.assertIsNone(MigrationContext.configure(connection).get_current_revision())
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        self.addCleanup(command.downgrade, config, "base")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def prepared(self, **kwargs):
        path, _ = write_snapshot(self.root, **kwargs)
        return load_snapshot(path, self.root)

    def counts(self):
        with self.engine.connect() as connection:
            return {name: connection.scalar(self.sa.select(self.sa.func.count()).select_from(table))
                    for name, table in self.db.metadata.tables.items()}

    def test_replay_reuses_run_and_revision_keeps_same_pdf_and_evidence(self):
        prepared = self.prepared()
        first = self.import_snapshot(self.engine, prepared)
        self.assertEqual(first["inserted_chunks"], 2)
        replay = self.import_snapshot(self.engine, prepared)
        self.assertEqual(replay, {**first, "inserted_chunks": 0, "reused": True})
        self.assertEqual(self.counts()["ingest_run"], 1)
        second = self.prepared(revision="B")
        self.assertEqual(second["document"]["sha256"], prepared["document"]["sha256"])
        self.assertEqual(second["chunks"][0]["evidence_id"], prepared["chunks"][0]["evidence_id"])
        self.import_snapshot(self.engine, second)
        self.assertEqual({key: self.counts()[key] for key in ("document", "chunk", "ingest_run")},
                         {"document": 2, "chunk": 4, "ingest_run": 2})
        with self.engine.connect() as connection:
            row = connection.execute(self.sa.select(self.db.chunk)).mappings().first()
            self.assertEqual(row["safety_labels"], ["warning"])
            run = connection.execute(self.sa.select(self.db.ingest_run).where(
                self.db.ingest_run.c.ingest_run_id == row["ingest_run_id"])).mappings().one()
            self.assertEqual(run["input_sha256"], prepared["input_sha256"])
            self.assertEqual(run["run_status"], "succeeded")

    def test_new_pages_append_but_changed_content_and_rechunking_do_not_overwrite(self):
        prepared = self.prepared()
        self.import_snapshot(self.engine, prepared)
        self.import_snapshot(self.engine, self.prepared(pages=(3, 4), filename="next.json"))
        self.assertEqual(self.counts()["chunk"], 4)
        before = self.counts()
        for change in ("text", "evidence_id", "source_metadata"):
            altered = deepcopy(prepared)
            altered["input_sha256"] = "d" * 64
            if change == "source_metadata":
                altered["document"][change]["url"] = "https://example.com/different.pdf"
            elif change == "text":
                altered["chunks"][0][change] = "conflicting content"
            else:
                altered["chunks"][0][change] = "ev1:" + "d" * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.import_snapshot(self.engine, altered)
            self.assertEqual(self.counts(), before)

    def test_mid_batch_database_failure_rolls_back_document_run_and_chunks(self):
        prepared = self.prepared()
        inserted = 0

        def fail_second_chunk(connection, cursor, statement, parameters, context, executemany):
            nonlocal inserted
            if statement.startswith("INSERT INTO chunk"):
                inserted += 1
                if inserted == 2:
                    raise RuntimeError("synthetic injected failure")

        self.sa.event.listen(self.engine, "before_cursor_execute", fail_second_chunk)
        try:
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                self.import_snapshot(self.engine, prepared)
        finally:
            self.sa.event.remove(self.engine, "before_cursor_execute", fail_second_chunk)
        self.assertEqual(inserted, 2)
        self.assertTrue(all(count == 0 for count in self.counts().values()))
        self.assertEqual(self.import_snapshot(self.engine, prepared)["inserted_chunks"], 2)

    def test_concurrent_same_snapshot_creates_one_successful_run(self):
        prepared = self.prepared()
        barrier = Barrier(2)

        def ingest():
            barrier.wait(timeout=10)
            return self.import_snapshot(self.engine, prepared)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ingest) for _ in range(2)]
            reports = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(report["inserted_chunks"] for report in reports), [0, 2])
        self.assertEqual(len({report["ingest_run_id"] for report in reports}), 1)
        self.assertEqual(self.counts()["ingest_run"], 1)

    def test_events_replay_without_duplicates_and_preserve_unknown_firmware(self):
        events = seed_events()
        self.assertEqual(self.import_events(self.engine, events), {"asset": 1, "work_order": 1, "alarm": 1})
        self.assertEqual(self.import_events(self.engine, events), {"asset": 0, "work_order": 0, "alarm": 0})
        with self.engine.connect() as connection:
            order = connection.execute(self.sa.select(self.db.work_order)).mappings().one()
            self.assertIsNone(order["firmware_version"])
            self.assertTrue(order["synthetic"])
            self.assertEqual(order["alarm_code"], "00a1")
            self.assertEqual(order["observations"], ["合成观察"])

    def test_event_conflict_rolls_back_earlier_new_asset_and_work_order(self):
        events = seed_events()
        self.import_events(self.engine, events)
        added = seed_events()
        for kind, prefix in (("work_order", "WO"), ("alarm", "AL")):
            row = added[kind][0]
            row.update(id=prefix + "0", asset_id="SYN-0", incident_group="history-0")
            row["locator"]["record_id"] = row["id"]
            if kind == "alarm":
                row["work_order_id"] = "WO0"
            events[kind].append(row)
        events["work_order"][0]["action"] = "conflicting action"
        before = self.counts()
        with self.assertRaisesRegex(ValueError, "different content"):
            self.import_events(self.engine, events)
        self.assertEqual(self.counts(), before)
