"""Synthetic corruption and table regressions; no model or vendor fixtures."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.ingestion.chunking import chunk_document
from app.ingestion.evidence import identify_chunk
from app.ingestion.fault_codes import extract_fault_codes
from app.ingestion.quality import validate_document_quality
from scripts import parse_pdf

KEY = "SYNTHETIC@A:" + "a" * 64


def document():
    cells = []
    for row, values in enumerate((
        ("编码（hex）", "故障/辅助代码", "原因", "措施"),
        ("00a1", "合成甲", "原因甲", "检查甲"),
        ("42\nF1", "合成乙", "原因乙", "检查乙"),
        ("00b2", "合成丙", "原因丙", "检查丙"),
    )):
        for col, value in enumerate(values):
            cells.append({
                "text": value, "column_header": row == 0, "row_span": 1, "col_span": 1,
                "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                "start_col_offset_idx": col, "end_col_offset_idx": col + 1,
                "bbox": {"l": col * 40, "r": col * 40 + 35, "t": row * 20 + 50,
                         "b": row * 20 + 65, "coord_origin": "TOPLEFT"},
            })
    return {
        "pages": {"7": {"page_no": 7, "size": {"width": 200, "height": 300}}},
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/tables/0"}]},
        "texts": [{"self_ref": "#/texts/0", "label": "section_header", "text": "合成故障表", "level": 1}],
        "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 7}],
                    "data": {"num_rows": 4, "num_cols": 4, "table_cells": cells}}],
    }


class TextQualityTests(unittest.TestCase):
    def test_chinese_symbols_tabs_and_line_endings_survive_json_and_chunking(self):
        value = "中文合成段落：温度 25°C，电压 ±5%，Ω/μ。\n第二行\t项目\r\n𠀀"
        doc = document()
        doc["texts"][0].update(label="text", text=value)
        original = deepcopy(doc)
        validate_document_quality(doc)
        restored = json.loads(json.dumps(doc, ensure_ascii=False))
        self.assertEqual(chunk_document(restored, KEY)[0]["text"], value)
        self.assertEqual(doc, original)

    def test_replacement_and_non_layout_control_characters_are_rejected(self):
        for character in ("\ufffd", "\x00", "\x08", "\x0b", "\x0c", "\x1f", "\x7f", "\x85", "\x9f"):
            for target in ("paragraph", "cell"):
                doc = document()
                item = doc["texts"][0] if target == "paragraph" else doc["tables"][0]["data"]["table_cells"][7]
                item["text"] = f"合成{character}文本"
                original = deepcopy(doc)
                with self.subTest(character=repr(character), target=target):
                    with self.assertRaisesRegex(ValueError, "Invalid text character at #/"):
                        validate_document_quality(doc)
                    self.assertEqual(doc, original)

    def test_empty_and_furniture_only_pages_preserve_pages_without_chunks(self):
        for texts in ([], [{"self_ref": "#/texts/0", "label": "page_header", "text": "合成页眉"}]):
            doc = {"pages": document()["pages"], "texts": texts,
                   "body": {"children": [{"$ref": item["self_ref"]} for item in texts]}}
            validate_document_quality(doc)
            self.assertEqual(chunk_document(doc, KEY), [])
            self.assertEqual(list(doc["pages"]), ["7"])


class TableQualityTests(unittest.TestCase):
    def test_duplicate_or_overlapping_cells_are_rejected_before_silent_overwrite(self):
        for changes in ({}, {"start_row_offset_idx": 0, "row_span": 2},
                        {"start_col_offset_idx": 0, "col_span": 2}):
            doc = document()
            cells = doc["tables"][0]["data"]["table_cells"]
            cells.append({**cells[5], "text": "不可覆盖原单元格", **changes})
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Overlapping table cells"):
                validate_document_quality(doc)

    def test_invalid_cell_bounds_and_span_disagreement_are_rejected(self):
        changes = (
            {"start_row_offset_idx": -1}, {"end_row_offset_idx": 5}, {"start_col_offset_idx": 4},
            {"end_col_offset_idx": 5}, {"start_row_offset_idx": True}, {"end_col_offset_idx": 1.5},
            {"end_row_offset_idx": 0}, {"row_span": 2}, {"col_span": 0}, {"row_span": True},
        )
        for update in changes:
            doc = document()
            doc["tables"][0]["data"]["table_cells"][0].update(update)
            with self.subTest(update=update), self.assertRaisesRegex(ValueError, "Invalid table cell"):
                validate_document_quality(doc)

    def test_invalid_declared_dimensions_are_rejected(self):
        for field, size in (("num_rows", -1), ("num_cols", True), ("num_rows", 2.5), ("num_cols", None)):
            doc = document()
            doc["tables"][0]["data"][field] = size
            with self.subTest(field=field, size=size), self.assertRaisesRegex(ValueError, "table dimensions"):
                validate_document_quality(doc)

    def test_valid_merged_cells_and_sparse_slots_are_not_mistaken_for_overlap(self):
        doc = document()
        data = doc["tables"][0]["data"]
        # Share one action across three rows; leave a different blank slot unoccupied.
        data["table_cells"][7].update(row_span=3, end_row_offset_idx=4)
        data["table_cells"] = [cell for i, cell in enumerate(data["table_cells"]) if i not in (10, 11, 15)]
        validate_document_quality(doc)
        chunks = chunk_document(doc, KEY)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(chunk["text"].count("检查甲") == 1 for chunk in chunks))

    def test_broken_code_is_retained_without_repair_or_inheriting_a_previous_code(self):
        doc = document()
        original = deepcopy(doc)
        validate_document_quality(doc)
        codes = extract_fault_codes(doc)
        self.assertEqual([code["normalized_code"] for code in codes], ["00A1", "00B2"])
        chunks = chunk_document(doc, KEY)
        self.assertEqual([chunk["chunk_type"] for chunk in chunks], ["fault_rows", "table_rows", "fault_rows"])
        self.assertEqual(chunks[1]["fault_codes"], [])
        self.assertIn("42\nF1", chunks[1]["text"])
        self.assertIn("检查乙", chunks[1]["text"])
        self.assertNotIn("检查甲", chunks[1]["text"])
        self.assertNotIn("检查丙", chunks[1]["text"])
        self.assertEqual(doc, original)

    def test_cross_page_cells_remain_ambiguous_instead_of_using_the_first_page(self):
        doc = document()
        doc["tables"][0]["prov"].append({"page_no": 8})
        doc["pages"]["8"] = {**doc["pages"]["7"], "page_no": 8}
        validate_document_quality(doc)
        with self.assertRaisesRegex(ValueError, "unambiguous single physical page"):
            identify_chunk(doc, chunk_document(doc, KEY)[0])
        self.assertEqual([p["page_no"] for p in doc["tables"][0]["prov"]], [7, 8])


class QualityCommandTests(unittest.TestCase):
    def test_quality_failure_does_not_publish_output_or_modify_input(self):
        invalid = []
        for kind in ("text", "table", "cross_page"):
            doc = document()
            if kind == "text":
                doc["texts"][0]["text"] = "损坏\ufffd标题"
            elif kind == "table":
                cells = doc["tables"][0]["data"]["table_cells"]
                cells.append(deepcopy(cells[5]))
            else:
                doc["tables"][0]["prov"].append({"page_no": 8})
            invalid.append(doc)
        for doc in invalid:
            original = deepcopy(doc)
            with self.subTest(doc=doc["texts"][0]["text"]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data/sources").mkdir(parents=True)
                source = {"id": "SYNTHETIC", "local_path": "synthetic.pdf", "pages": 8,
                          "document_code": "SYNTHETIC-MANUAL", "revision": "A", "firmware_scope": None,
                          "url": "https://example.com/synthetic.pdf", "accessed_at": "2026-10-29", "sha256": "a" * 64}
                (root / "data/sources/manifest.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
                output = root / "data/processed/result.json"
                with (patch.object(parse_pdf, "ROOT", root), patch.object(parse_pdf, "verify_file"),
                      patch.object(parse_pdf, "parse_pdf", return_value={"document": doc})):
                    with self.assertRaises(ValueError):
                        parse_pdf.main(["--source", "SYNTHETIC", "--pages", "7", "8", "--output", str(output)])
                self.assertFalse(output.exists())
                self.assertEqual(doc, original)


if __name__ == "__main__":
    unittest.main()
