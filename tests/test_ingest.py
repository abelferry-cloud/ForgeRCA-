"""Offline import boundaries using synthetic PDF bytes and native document shapes."""

import hashlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from app.ingestion.chunking import chunk_document
from app.ingestion.evidence import identify_chunk
from app.ingestion.metadata import locate_chunk
from app.schemas.document import DocumentKey
from app.schemas.events import EVENT_FILES, validate_seed_events
from scripts import ingest


def write_snapshot(root, *, revision="A", pages=(1, 2), filename="snapshot.json"):
    pdf = b"%PDF-synthetic fixture only"
    source = {"id": "SYNTHETIC", "document_code": "SYNTHETIC-MANUAL", "revision": revision,
              "sha256": hashlib.sha256(pdf).hexdigest(), "models": ["TEST-MODEL"], "firmware_scope": None,
              "url": "https://example.com/manual.pdf", "accessed_at": "2026-11-06",
              "local_path": "data/raw/abb/synthetic.pdf", "bytes": len(pdf), "pages": 4}
    for name in ("data/raw/abb", "data/processed", "data/sources"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / source["local_path"]).write_bytes(pdf)
    (root / "data/sources/manifest.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    document = {"body": {"children": []}, "texts": [], "tables": [], "pages": {}}
    for page in pages:
        document["pages"][str(page)] = {"page_no": page, "size": {"width": 200, "height": 300}}
        for offset, label in enumerate(("section_header", "text")):
            ref = f"#/texts/{len(document['texts'])}"
            value = f"合成章节{page}" if not offset else f"警告！合成内容{page}"
            document["texts"].append({"self_ref": ref, "text": value, "label": label, "level": 1,
                                      "children": [], "prov": [{"page_no": page, "charspan": [0, len(value)],
                                      "bbox": {"l": 10, "t": 10 + offset * 30, "r": 100,
                                               "b": 30 + offset * 30, "coord_origin": "TOPLEFT"}}]})
            document["body"]["children"].append({"$ref": ref})
    key = DocumentKey.from_source(source)
    result = {"schema_version": 1, "source": {"document_key": key.value, **asdict(key)}, "document": document,
              "parser": {"page_range": [min(pages), max(pages)], "packages": {"fixture": "1"},
                         "options": {"do_ocr": False}, "models": {"fixture": "synthetic"}},
              "chunks": [locate_chunk(identify_chunk(document, chunk), source)
                         for chunk in chunk_document(document, key.value)]}
    path = root / "data/processed" / filename
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return path, result


def seed_events():
    common = {"model": "TEST-MODEL", "firmware_version": None, "synthetic": True, "asset_id": "SYN-1",
              "incident_group": "history-1", "alarm_code": "00a1", "text": "合成事件"}
    work = {**common, "id": "WO1", "kind": "work_order", "opened_at": "2026-01-01T08:00:00+08:00",
            "closed_at": "2026-01-01T10:00:00+08:00", "available_at": "2026-01-01T10:00:00+08:00",
            "observations": ["合成观察"], "confirmed_cause": "synthetic_cause", "action": "合成动作",
            "outcome": "合成结果", "locator": {"file": EVENT_FILES["work_order"], "record_id": "WO1"}}
    alarm = {**common, "id": "AL1", "kind": "alarm", "work_order_id": "WO1",
             "occurred_at": "2026-01-01T09:00:00+08:00", "available_at": "2026-01-01T09:00:00+08:00",
             "locator": {"file": EVENT_FILES["alarm"], "record_id": "AL1"}}
    return {"work_order": [work], "alarm": [alarm]}


class ImportPreparationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_snapshot_keeps_input_and_pdf_digests_separate(self):
        path, result = write_snapshot(self.root)
        prepared = ingest.load_snapshot(path, self.root)
        self.assertEqual(prepared["input_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertNotEqual(prepared["input_sha256"], prepared["document"]["sha256"])
        self.assertEqual(prepared["input_path"], "data/processed/snapshot.json")
        self.assertEqual(len(prepared["chunks"]), 2)
        self.assertEqual(prepared["chunks"][0]["safety_labels"], ["warning"])
        self.assertEqual(prepared["chunks"][0]["evidence_id"], result["chunks"][0]["evidence_id"])

    def test_forbidden_inputs_are_rejected_before_reading(self):
        for name in ("data/evaluation/dev.jsonl", "data/graph/reference.json", "docs/reviews/review.json",
                     "artifacts/snapshot.json", "data/processed/../../data/evaluation/test.json"):
            with self.subTest(path=name), patch.object(Path, "read_bytes") as read:
                with self.assertRaisesRegex(ValueError, "inside data/processed"):
                    ingest.load_snapshot(name, self.root)
                read.assert_not_called()

    def test_snapshot_rejects_mismatched_source_and_tampered_chunks(self):
        path, original = write_snapshot(self.root)
        mutations = [lambda r: r["source"].update(sha256="0" * 64),
                     lambda r: r["source"].update(source_url="https://example.com/other.pdf"),
                     lambda r: r["chunks"][0].update(text="invented"),
                     lambda r: r["chunks"][0].update(evidence_id="ev1:" + "0" * 64),
                     lambda r: r["chunks"].append(deepcopy(r["chunks"][0])),
                     lambda r: r["chunks"][0].update(locations=[{"pdf_page": 4, "printed_page": None}]),
                     lambda r: r["chunks"][0].update(safety_labels=[]),
                     lambda r: r["document"]["pages"].pop("2")]
        for index, mutate in enumerate(mutations):
            value = deepcopy(original)
            mutate(value)
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(case=index), self.assertRaises(ValueError):
                ingest.load_snapshot(path, self.root)

    def test_raw_pdf_is_verified(self):
        path, _ = write_snapshot(self.root)
        pdf = self.root / "data/raw/abb/synthetic.pdf"
        pdf.write_bytes(pdf.read_bytes()[:-1] + b"!")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            ingest.load_snapshot(path, self.root)

    def test_seed_loader_reads_only_two_allowlisted_files(self):
        events = seed_events()
        for kind, name in EVENT_FILES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(events[kind][0], ensure_ascii=False) + "\n", encoding="utf-8")
        original = Path.read_text
        reads = []

        def read(path, *args, **kwargs):
            reads.append(path.relative_to(self.root).as_posix())
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", read):
            self.assertEqual(ingest.load_seed_events(self.root), events)
        self.assertEqual(reads, list(EVENT_FILES.values()))

    def test_seed_relationships_and_time_rules_are_shared(self):
        events = seed_events()
        self.assertEqual(set(validate_seed_events(events)), {"WO1"})
        mutations = [lambda c: c["alarm"][0].update(firmware_version="ASCKX 2.16"),
                     lambda c: c["alarm"][0].update(model="OTHER"),
                     lambda c: c["alarm"][0].update(incident_group="another"),
                     lambda c: c["alarm"][0].update(synthetic=False),
                     lambda c: c["alarm"][0].update(occurred_at="2026-01-01T11:00:00+08:00"),
                     lambda c: c["alarm"][0].update(available_at="2026-01-01T09:00:00"),
                     lambda c: c["work_order"][0].update(observations="not a list"),
                     lambda c: c["work_order"][0].update(gold_evidence_ids=["forbidden"]),
                     lambda c: c["alarm"].append(deepcopy(c["alarm"][0]))]
        for index, mutate in enumerate(mutations):
            value = deepcopy(events)
            mutate(value)
            with self.subTest(case=index), self.assertRaises(ValueError):
                validate_seed_events(value)

    def test_cli_requires_explicit_input_and_fails_before_database_setup(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as missing:
                ingest.main([])
            self.assertEqual(missing.exception.code, 2)
            with patch.object(ingest, "load_snapshot", side_effect=ValueError("invalid snapshot")):
                with self.assertRaises(SystemExit) as invalid:
                    ingest.main(["--snapshot", "bad.json"])
                self.assertEqual(invalid.exception.code, 1)
