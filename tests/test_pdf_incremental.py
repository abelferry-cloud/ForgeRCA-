"""Incremental comparison uses synthetic snapshots, never evaluation labels."""

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.ingestion.evidence import identify_chunk
from app.ingestion.incremental import compare_parses
from scripts import compare_parses as command

KEY = "SYNTHETIC@A:" + "a" * 64


def snapshot():
    doc = {"pages": {str(n): {"page_no": n, "size": {"width": 200, "height": 300}} for n in (7, 8)},
           "texts": [], "tables": []}
    chunks = []
    for index, page in enumerate((7, 8)):
        doc["texts"].append({"text": f"合成段落{index}", "prov": [{
            "page_no": page, "charspan": [0, 5],
            "bbox": {"l": 10, "t": 20, "r": 100, "b": 40, "coord_origin": "TOPLEFT"},
        }]})
        chunks.append(identify_chunk(doc, {
            "document_key": KEY, "text": f"合成段落{index}", "chunk_type": "section", "section": ["合成章节"],
            "source_refs": [f"#/texts/{index}"], "heading_refs": [],
            "locations": [{"pdf_page": page, "printed_page": None}], "table_row": None,
        }))
    doc["tables"].append({"prov": [{"page_no": 7}], "data": {"table_cells": [
        {"text": code, "bbox": {"l": n * 50, "t": 100, "r": n * 50 + 40, "b": 120, "coord_origin": "TOPLEFT"}}
        for n, code in enumerate(("00a1", "00b2"))
    ]}})
    refs = [f"#/tables/0/data/table_cells/{n}" for n in (0, 1)]
    chunks.append(identify_chunk(doc, {
        "document_key": KEY, "text": "00a1\t00b2", "chunk_type": "fault_rows", "section": ["合成章节"],
        "source_refs": refs, "heading_refs": [], "table_ref": "#/tables/0", "row_range": [1, 2],
        "table_row": {"table_ref": "#/tables/0", "row_range": [1, 2]},
        "locations": [{"pdf_page": 7, "printed_page": "vii"}],
        "fault_codes": [{"raw_code": code, "normalized_code": code.upper(), "cell_ref": ref}
                        for code, ref in zip(("00a1", "00b2"), refs, strict=True)],
    }))
    return {
        "schema_version": 1, "document": doc, "chunks": chunks,
        "source": {"document_key": KEY, "source_id": "SYNTHETIC", "revision": "A", "sha256": "a" * 64,
                   "document_code": "SYNTHETIC-MANUAL", "firmware_scope": None,
                   "source_url": "https://example.com/manual.pdf", "accessed_at": "2026-11-01"},
        "parser": {"page_range": [7, 8], "packages": {"docling": "synthetic-1"},
                   "options": {"device": "cpu", "do_ocr": False},
                   "models": {"layout": {"revision": "0" * 40, "files": {"synthetic.bin": "1" * 64}}}},
    }


class IncrementalTests(unittest.TestCase):
    def test_equal_snapshots_have_no_changes_and_inputs_are_unchanged(self):
        before, after = snapshot(), snapshot()
        original = deepcopy((before, after))
        report = compare_parses(before, after)
        self.assertEqual((report["added"], report["removed"], report["modified"]), ([], [], []))
        self.assertEqual(report["unchanged_count"], 3)
        self.assertFalse(report["parser_changed"])
        self.assertEqual(report["source_metadata_changed"], [])
        self.assertEqual(report["parser_fingerprint_before"], report["parser_fingerprint_after"])
        self.assertRegex(report["parser_fingerprint_before"], r"^[0-9a-f]{64}$")
        self.assertEqual(report, compare_parses(before, after))
        self.assertEqual((before, after), original)

    def test_array_and_reference_renumbering_do_not_create_changes(self):
        before, after = snapshot(), snapshot()
        after["document"]["texts"].reverse()
        for index, chunk in enumerate(after["chunks"][:2]):
            chunk["source_refs"] = [f"#/texts/{1 - index}"]
        after["document"]["tables"][0]["data"]["table_cells"].reverse()
        after["document"]["tables"].insert(0, {"data": {"table_cells": []}})
        chunk = after["chunks"][2]
        chunk["source_refs"] = [f"#/tables/1/data/table_cells/{n}" for n in (1, 0)]
        chunk["table_ref"] = chunk["table_row"]["table_ref"] = "#/tables/1"
        chunk["heading_refs"] = ["#/texts/0"]
        for code, ref in zip(chunk["fault_codes"], chunk["source_refs"], strict=True):
            code["cell_ref"] = ref
        chunk["fault_codes"].reverse()
        chunk["source_refs"].reverse()
        after["chunks"].reverse()
        report = compare_parses(before, after)
        self.assertEqual(report["modified"], [])
        self.assertEqual(report["unchanged_count"], 3)

    def test_added_and_removed_ids_are_deterministic(self):
        before, after = snapshot(), snapshot()
        removed = after["chunks"].pop(1)["evidence_id"]
        # A changed physical anchor is a removal plus addition, not a guessed match.
        after["document"]["texts"][0]["prov"][0]["bbox"]["l"] = 11
        previous = after["chunks"][0]["evidence_id"]
        after["chunks"][0] = identify_chunk(after["document"], after["chunks"][0])
        report = compare_parses(before, after)
        self.assertEqual(report["removed"], sorted([removed, previous]))
        self.assertEqual(report["added"], [after["chunks"][0]["evidence_id"]])
        self.assertEqual(report["modified"], [])
        self.assertEqual(report["unchanged_count"], 1)

    def test_same_anchor_content_and_display_metadata_changes_are_reported(self):
        changes = {"text": "更新合成内容", "section": ["新章节"], "chunk_type": "table_rows",
                   "locations": [{"pdf_page": 7, "printed_page": "viii"}], "row_range": [1, 3],
                   "table_row": {"table_ref": "#/tables/0", "row_range": [1, 3]},
                   "fault_codes": [{"raw_code": "00a2", "normalized_code": "00A2", "cell_ref": "local"}],
                   "safety_labels": ["warning"]}
        for field, value in changes.items():
            before, after = snapshot(), snapshot()
            after["chunks"][2][field] = value
            report = compare_parses(before, after)
            with self.subTest(field=field):
                self.assertEqual(report["modified"], [{"evidence_id": before["chunks"][2]["evidence_id"],
                                                        "fields": [field]}])
                self.assertEqual(report["unchanged_count"], 2)

    def test_missing_metadata_is_distinct_from_explicit_null(self):
        before, after = snapshot(), snapshot()
        del before["chunks"][0]["table_row"]
        self.assertEqual(compare_parses(before, after)["modified"][0]["fields"], ["table_row"])

    def test_parser_changes_do_not_mark_identical_chunks_as_modified(self):
        for field, value in (("packages", {"docling": "synthetic-2"}), ("options", {"do_ocr": True}),
                             ("models", {"layout": {"revision": "2" * 40}})):
            before, after = snapshot(), snapshot()
            after["parser"][field] = value
            with self.subTest(field=field):
                report = compare_parses(before, after)
                self.assertTrue(report["parser_changed"])
                self.assertNotEqual(report["parser_fingerprint_before"], report["parser_fingerprint_after"])
                self.assertEqual(report["modified"], [])
                self.assertEqual(report["unchanged_count"], 3)

    def test_mapping_key_order_does_not_change_configuration_fingerprint(self):
        before, after = snapshot(), snapshot()
        after["parser"]["options"] = dict(reversed(list(after["parser"]["options"].items())))
        self.assertFalse(compare_parses(before, after)["parser_changed"])

    def test_source_metadata_changes_are_separate_from_chunk_changes(self):
        before, after = snapshot(), snapshot()
        after["source"]["accessed_at"] = "2026-11-02"
        report = compare_parses(before, after)
        self.assertEqual(report["source_metadata_changed"], ["accessed_at"])
        self.assertEqual(report["modified"], [])

    def test_empty_snapshots_are_valid_but_missing_chunks_are_not(self):
        empty = snapshot()
        empty["chunks"] = []
        self.assertEqual(compare_parses(empty, empty)["unchanged_count"], 0)
        del empty["chunks"]
        with self.assertRaises(ValueError):
            compare_parses(empty, snapshot())

    def test_different_parent_source_revision_or_digest_is_not_compared(self):
        for field, value in (("source_id", "OTHER"), ("revision", "B"), ("sha256", "b" * 64)):
            before, after = snapshot(), snapshot()
            after["source"][field] = value
            source = after["source"]
            source["document_key"] = f"{source['source_id']}@{source['revision']}:{source['sha256']}"
            for chunk in after["chunks"]:
                chunk["document_key"] = source["document_key"]
            after["chunks"] = [identify_chunk(after["document"], chunk) for chunk in after["chunks"]]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "same parent document"):
                compare_parses(before, after)

    def test_different_page_ranges_do_not_report_unparsed_pages_as_removed(self):
        before, after = snapshot(), snapshot()
        after["parser"]["page_range"] = [7, 7]
        del after["document"]["pages"]["8"]
        after["document"]["texts"].pop(1)
        after["chunks"].pop(1)
        with self.assertRaisesRegex(ValueError, "same physical page range"):
            compare_parses(before, after)

    def test_incomplete_page_coverage_and_invalid_page_ranges_are_rejected(self):
        for pages in ([7, 9], [0, 8], [8, 7], [True, 8], [7], "7-8"):
            after = snapshot()
            after["parser"]["page_range"] = pages
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                compare_parses(snapshot(), after)

    def test_legacy_missing_configuration_and_unknown_schema_are_rejected(self):
        for kind in ("id", "locator", "packages", "options", "models", "schema"):
            after = snapshot()
            if kind in ("id", "locator"):
                del after["chunks"][0]["evidence_" + kind]
            elif kind == "schema":
                after["schema_version"] = 2
            else:
                after["parser"].pop(kind)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                compare_parses(snapshot(), after)

    def test_duplicate_ids_and_inconsistent_identity_are_rejected(self):
        for kind in ("duplicate", "id", "locator", "parent", "source"):
            after = snapshot()
            if kind == "duplicate":
                after["chunks"].append(deepcopy(after["chunks"][0]))
            elif kind == "id":
                after["chunks"][0]["evidence_id"] = "ev1:" + "0" * 64
            elif kind == "locator":
                after["chunks"][0]["evidence_locator"]["elements"][0]["pdf_page"] = 8
            elif kind == "parent":
                after["chunks"][0]["document_key"] = "OTHER@A:" + "a" * 64
            else:
                after["source"]["sha256"] = "b" * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                compare_parses(snapshot(), after)


class ComparisonCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        folder = self.root / "data/processed"
        folder.mkdir(parents=True)
        self.before, self.after = folder / "before.json", folder / "after.json"
        for path in (self.before, self.after):
            path.write_text(json.dumps(snapshot(), ensure_ascii=False), encoding="utf-8")
        self.output = self.root / "artifacts/diffs/result.json"
        self.args = ["--before", str(self.before), "--after", str(self.after), "--output", str(self.output)]
        patcher = patch.object(command, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_report_is_text_free_records_input_fingerprints_and_preserves_inputs(self):
        original = [path.read_bytes() for path in (self.before, self.after)]
        command.main(self.args)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["unchanged_count"], 3)
        self.assertEqual(report["inputs"]["before"], {
            "path": "data/processed/before.json", "sha256": hashlib.sha256(original[0]).hexdigest(),
        })
        self.assertNotIn("合成段落", self.output.read_text(encoding="utf-8"))
        self.assertEqual([path.read_bytes() for path in (self.before, self.after)], original)

    def test_output_outside_artifacts_or_existing_output_is_rejected(self):
        for output in (self.before, self.root / "published.json", self.root / "artifacts/result.txt"):
            with self.subTest(output=str(output)), self.assertRaises(SystemExit):
                command.main(self.args[:-1] + [str(output)])
        self.output.parent.mkdir(parents=True)
        self.output.write_text("keep", encoding="utf-8")
        with self.assertRaises(SystemExit):
            command.main(self.args)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep")

    def test_inputs_outside_processed_are_rejected_before_reading(self):
        for path in (self.root / "data/evaluation/labels.json", self.root / "data/processed/../outside.json",
                     self.root / "data/processed/result.txt"):
            with self.subTest(path=str(path)), self.assertRaises(SystemExit):
                command.main(["--before", str(path), *self.args[2:]])
        self.assertFalse(self.output.exists())

    def test_invalid_snapshot_leaves_no_report(self):
        for value in ("{broken json", json.dumps({"schema_version": 1}), json.dumps({"schema_version": 2})):
            self.after.write_text(value, encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                command.main(self.args)
            self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
