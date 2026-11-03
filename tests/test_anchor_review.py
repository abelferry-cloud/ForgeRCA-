"""Human-review preparation uses synthetic PDFs and snapshots, never gold labels."""

import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from app.ingestion.evidence import identify_chunk
from app.ingestion.metadata import locate_chunk
from app.schemas.document import DocumentKey
from scripts import prepare_anchor_review as command
from scripts.corpus_allowlist import IndexScopeError, assert_indexable


class AnchorReviewTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch.object(command, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        raw = b"%PDF-synthetic-review-fixture\n"
        self.pdf = self.root / "data/raw/synthetic.pdf"
        self.pdf.parent.mkdir(parents=True)
        self.pdf.write_bytes(raw)
        self.source = {
            "id": "SYNTHETIC", "revision": "A", "sha256": hashlib.sha256(raw).hexdigest(),
            "document_code": "SYNTHETIC-MANUAL", "firmware_scope": None,
            "url": "https://example.com/manual.pdf", "accessed_at": "2026-11-01",
            "local_path": "data/raw/synthetic.pdf", "bytes": len(raw), "pages": 8,
        }
        self.manifest = self.root / "data/sources/manifest.json"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({"sources": [self.source]}), encoding="utf-8")
        key = DocumentKey.from_source(self.source)
        document = {"pages": {str(n): {"page_no": n, "size": {"width": 200, "height": 1000}} for n in (7, 8)},
                    "texts": []}
        chunks = []
        for index in range(30):
            text = f"合成原文 <script>not_code</script> {index}"
            document["texts"].append({"text": text, "prov": [{
                "page_no": 7 + index % 2, "charspan": [0, len(text)],
                "bbox": {"l": 10, "r": 100, "t": index * 20 + 10, "b": index * 20 + 20,
                         "coord_origin": "TOPLEFT"},
            }]})
            chunk = identify_chunk(document, {"document_key": key.value, "chunk_type": "section",
                                              "text": text, "section": ["合成标题"],
                                              "source_refs": [f"#/texts/{index}"], "heading_refs": []})
            chunks.append(locate_chunk(chunk, self.source))
        self.snapshot = {
            "schema_version": 1, "source": {"document_key": key.value, **asdict(key)},
            "parser": {"page_range": [7, 8], "packages": {"docling": "synthetic-1"},
                       "options": {"do_ocr": False}, "models": {"layout": {"revision": "0" * 40}}},
            "document": document, "chunks": chunks,
        }
        self.input = self.root / "data/processed/synthetic.json"
        self.input.parent.mkdir(parents=True)
        self.save_snapshot()
        self.inventory = self.root / "docs/reviews/anchors.json"
        self.output = self.root / "artifacts/review/anchors.html"
        self.args = ["--inputs", str(self.input), "--inventory", str(self.inventory), "--output", str(self.output)]

    def save_snapshot(self):
        self.input.write_text(json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8")

    def test_inventory_has_no_original_text_and_all_decisions_are_pending(self):
        inventory, packet = command.build_review([self.input])
        self.assertEqual(len(inventory["items"]), 30)
        self.assertEqual(inventory["inputs"][0]["sha256"], hashlib.sha256(self.input.read_bytes()).hexdigest())
        self.assertEqual(inventory["inputs"][0]["pdf_sha256"], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual(inventory["source_manifest_sha256"], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        for index, item in enumerate(inventory["items"]):
            self.assertEqual(item["evidence_id"], self.snapshot["chunks"][index]["evidence_id"])
            self.assertEqual((item["reviewer"], item["review_date"], item["decision"], item["notes"]),
                             (None, None, "pending", None))
        public = json.dumps(inventory, ensure_ascii=False)
        self.assertNotIn("合成原文", public)
        self.assertNotIn("合成标题", public)
        self.assertNotIn("<script>", packet)
        self.assertIn("&lt;script&gt;not_code&lt;/script&gt;", packet)
        self.assertIn(self.pdf.as_uri() + "#page=7", packet)
        self.assertIn(self.pdf.as_uri() + "#page=8", packet)
        self.assertIn("evidence_locator", packet)
        self.assertEqual((inventory, packet), command.build_review([self.input]))

    def test_cli_writes_new_files_without_changing_sources(self):
        before = self.input.read_bytes(), self.pdf.read_bytes(), self.manifest.read_bytes()
        command.main(self.args)
        self.assertEqual(len(json.loads(self.inventory.read_text(encoding="utf-8"))["items"]), 30)
        self.assertIn("待人工核对", self.output.read_text(encoding="utf-8"))
        self.assertEqual(before, (self.input.read_bytes(), self.pdf.read_bytes(), self.manifest.read_bytes()))

    def test_insufficient_sample_fails_without_outputs(self):
        self.snapshot["chunks"].pop()
        self.save_snapshot()
        with self.assertRaisesRegex(ValueError, "at least 30"):
            command.main(self.args)
        self.assertFalse(self.inventory.exists())
        self.assertFalse(self.output.exists())

    def test_duplicate_inputs_and_duplicate_anchors_cannot_pad_sample(self):
        with self.assertRaisesRegex(ValueError, "Repeated input"):
            command.build_review([self.input, self.input])
        another = self.input.with_name("another.json")
        another.write_bytes(self.input.read_bytes())
        with self.assertRaisesRegex(ValueError, "Repeated evidence ID"):
            command.build_review([self.input, another])

    def test_bad_id_or_missing_display_metadata_is_rejected(self):
        for field in ("evidence_id", "locations", "table_row"):
            value = self.snapshot["chunks"][0].pop(field)
            self.save_snapshot()
            with self.subTest(field=field), self.assertRaises(ValueError):
                command.main(self.args)
            self.snapshot["chunks"][0][field] = value
        self.assertFalse(self.inventory.exists())
        self.assertFalse(self.output.exists())

    def test_wrong_display_page_is_rejected(self):
        self.snapshot["chunks"][0]["locations"][0]["pdf_page"] = 8
        self.save_snapshot()
        with self.assertRaisesRegex(ValueError, "display locations"):
            command.main(self.args)

    def test_changed_original_pdf_is_rejected(self):
        self.pdf.write_bytes(self.pdf.read_bytes().replace(b"fixture", b"changed"))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            command.main(self.args)
        self.assertFalse(self.output.exists())

    def test_source_metadata_mismatch_is_rejected(self):
        self.snapshot["source"]["revision"] = "B"
        self.save_snapshot()
        with self.assertRaises(ValueError):
            command.main(self.args)
        self.snapshot["source"]["revision"] = "A"
        self.snapshot["source"]["document_code"] = "OTHER"
        self.save_snapshot()
        with self.assertRaisesRegex(ValueError, "registered source"):
            command.main(self.args)

    def test_existing_human_records_or_packet_are_not_overwritten(self):
        for path in (self.inventory, self.output):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("preserve human notes", encoding="utf-8")
            with self.subTest(path=path), self.assertRaises(SystemExit):
                command.main(self.args)
            self.assertEqual(path.read_text(encoding="utf-8"), "preserve human notes")
            path.unlink()

    def test_paths_outside_local_input_and_review_output_scopes_are_rejected(self):
        for index, value in ((1, "data/evaluation/labels.json"), (1, "data/processed/../outside.json"),
                             (3, "data/corpus/review.json"), (5, "docs/reviews/original.html"),
                             (3, "docs/reviews/review.txt"), (5, "artifacts/review.txt")):
            args = list(self.args)
            args[index] = str(self.root / value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                command.main(args)
        self.assertFalse(self.inventory.exists())
        self.assertFalse(self.output.exists())

    def test_review_materials_remain_outside_retrieval_allowlist(self):
        for path in ("docs/reviews/m1-15-anchors.json", "artifacts/reviews/m1-15.html"):
            with self.subTest(path=path), self.assertRaises(IndexScopeError):
                assert_indexable(path)


if __name__ == "__main__":
    unittest.main()
