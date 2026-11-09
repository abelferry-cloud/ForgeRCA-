"""Projection preserves provenance without reading evaluation, graph or review data."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.retrieval import corpus
from app.retrieval.index_schema import index_record_id
from scripts.corpus_allowlist import INDEXABLE_CORPUS_FILES


def manual_row():
    source = {"id": "SYNTHETIC", "revision": "A", "sha256": "a" * 64, "models": ["TEST-MODEL"],
              "firmware_scope": None, "effective_date": "2024-03-30"}
    return {"document_key": "SYNTHETIC@A:" + "a" * 64, "evidence_id": "ev1:" + "b" * 64,
            "source_id": "SYNTHETIC", "revision": "A", "models": ["TEST-MODEL"], "firmware_scope": None,
            "chunk_type": "section", "text": "Synthetic manual fixture.", "source_metadata": source,
            "fault_codes": [{"raw_code": "00a1", "normalized_code": "00A1"},
                            {"raw_code": "00a1", "normalized_code": "00A1"}]}


class CorpusProjectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for relative in (*INDEXABLE_CORPUS_FILES, "data/sources/manifest.json"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((corpus.ROOT / relative).read_bytes())

    def test_file_loader_reads_only_explicit_corpus_and_source_manifest(self):
        allowed = {(self.root / relative).resolve() for relative in
                   (*INDEXABLE_CORPUS_FILES, "data/sources/manifest.json")}
        # Mapping is configuration, not retrieval input.
        allowed.add((corpus.ROOT / "versions.lock.json").resolve())
        read = Path.read_text
        visited = set()

        def guarded_read(path, *args, **kwargs):
            self.assertIn(path.resolve(), allowed)
            visited.add(path.resolve())
            return read(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded_read):
            records = corpus.load_file_records(self.root)
        self.assertEqual(len(records), 33)
        self.assertTrue(all((self.root / relative).resolve() in visited for relative in INDEXABLE_CORPUS_FILES))
        by_id = {record["evidence_id"]: record for record in records}
        self.assertEqual(by_id["K001"]["record_kind"], "knowledge_note")
        self.assertEqual(by_id["K001"]["source_id"], "ABB-FW-H-ZH")
        self.assertIsNone(by_id["K001"]["document_key"])
        self.assertFalse(by_id["K001"]["synthetic"])
        self.assertTrue(by_id["K009"]["synthetic"])
        self.assertIsNone(by_id["K009"]["source_id"])
        for record in records:
            self.assertNotIn("embedding", record)
            if record["record_kind"] in ("work_order", "alarm"):
                self.assertTrue(record["synthetic"])
                self.assertIsNone(record["document_revision"])
                if record["firmware_version"] is None:
                    self.assertEqual(record["firmware_state"], "unknown")

    def test_extra_evaluation_fields_and_tampered_source_scope_are_rejected(self):
        path = self.root / "data/corpus/knowledge.jsonl"
        original = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for changes in ({"gold_evidence_ids": ["K001"]}, {"model": "UNREGISTERED"},
                        {"document_revision": "OTHER"}, {"firmware_scope": None}):
            rows = deepcopy(original)
            rows[0].update(changes)
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                corpus.load_file_records(self.root)

    def test_manual_uses_effective_date_parent_and_raw_code(self):
        row = manual_row()
        row.update(accessed_at="2099-01-01", created_at="2099-01-01")
        record = corpus.project_manual(row)
        corpus.validate_records([record])
        self.assertEqual(record["available_at"], "2024-03-30T00:00:00+08:00")
        self.assertEqual(record["alarm_code"], ["00a1"])
        self.assertEqual(record["firmware_state"], "unrestricted")
        self.assertEqual(record["document_key"], row["document_key"])
        self.assertEqual(record["record_kind"], "manual_chunk")
        self.assertFalse(record["synthetic"])

    def test_manual_metadata_and_fingerprint_mismatch_are_rejected(self):
        for changes in ({"source_id": "OTHER"}, {"models": ["OTHER"]}, {"revision": "B"},
                        {"firmware_scope": "ASCKX 2.16"}, {"document_key": "SYNTHETIC@A:" + "c" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                corpus.project_manual({**manual_row(), **changes})
        row = manual_row()
        row["source_metadata"].pop("effective_date")
        with self.assertRaises(KeyError):
            corpus.project_manual(row)

    def test_duplicates_fail_but_cross_revision_evidence_remains_distinct(self):
        first = corpus.project_manual(manual_row())
        with self.assertRaisesRegex(ValueError, "Duplicate corpus identity"):
            corpus.validate_records([first, first])
        second = {**first, "document_key": "SYNTHETIC@B:" + "c" * 64, "document_revision": "B"}
        corpus.validate_records([first, second])
        self.assertNotEqual(index_record_id(first), index_record_id(second))
