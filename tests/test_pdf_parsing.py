"""Parser contracts use synthetic Docling items; no vendor PDF or model download."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ingestion import pdf
from app.ingestion.chunking import chunk_document
from app.ingestion.evidence import identify_chunk
from app.ingestion.metadata import locate_chunk
from app.ingestion.quality import validate_document_quality
from scripts import download_parser_models, parse_pdf


class ParserModelTests(unittest.TestCase):
    def test_missing_or_corrupt_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(pdf, "MODELS_DIR", Path(directory)):
            pins = {"layout": {"repo_id": "example/model", "revision": "a" * 40,
                               "files": {"model.safetensors": hashlib.sha256(b"valid").hexdigest()}}}
            with patch.object(pdf, "MODEL_PINS", pins):
                with self.assertRaisesRegex(ValueError, "Missing or invalid"):
                    pdf.verify_models()
                target = Path(directory) / "example--model/model.safetensors"
                target.parent.mkdir()
                target.write_bytes(b"corrupt")
                with self.assertRaisesRegex(ValueError, "Missing or invalid"):
                    pdf.verify_models()
                target.write_bytes(b"valid")
                pdf.verify_models()


@unittest.skipUnless(importlib.util.find_spec("docling"), "Run with uv sync --frozen for parser dependencies")
class DoclingContractTests(unittest.TestCase):
    def setUp(self):
        from docling_core.types.doc import (
            BoundingBox,
            DocItemLabel,
            DoclingDocument,
            ProvenanceItem,
            Size,
            TableCell,
            TableData,
        )

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "synthetic.pdf"
        self.source.write_bytes(b"%PDF-1.4\nmock converter input")
        self.doc = DoclingDocument(name="synthetic")
        for page in (7, 8):
            self.doc.add_page(page_no=page, size=Size(width=200, height=300))
        prov = ProvenanceItem(page_no=7, bbox=BoundingBox(l=0, t=30, r=100, b=0, coord_origin="BOTTOMLEFT"),
                              charspan=(0, 5))
        self.doc.add_heading(text="Title", prov=prov)
        self.doc.add_text(label=DocItemLabel.TEXT, text="Before table", prov=prov)
        cells = [
            TableCell(text="Merged header", column_header=True, col_span=2,
                      start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=2),
            TableCell(text="0010", start_row_offset_idx=1, end_row_offset_idx=2,
                      start_col_offset_idx=0, end_col_offset_idx=1),
            TableCell(text="Synthetic action", start_row_offset_idx=1, end_row_offset_idx=2,
                      start_col_offset_idx=1, end_col_offset_idx=2),
        ]
        table = self.doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov)
        table.prov.append(prov.model_copy(update={"page_no": 8}))
        self.doc.add_text(label=DocItemLabel.TEXT, text="After table", prov=prov)
        self.doc.add_text(label=DocItemLabel.TEXT, text="Next page", prov=prov.model_copy(update={"page_no": 8}))

    def convert(self, status="success"):
        from docling.datamodel.base_models import ConversionStatus

        with patch.object(pdf, "verify_models"), patch("docling.document_converter.DocumentConverter") as factory:
            factory.return_value.convert.return_value = SimpleNamespace(
                status=ConversionStatus(status), document=self.doc,
            )
            result = pdf.parse_pdf(self.source, (7, 8))
        return result, factory

    def test_tree_order_page_provenance_and_merged_cells_survive(self):
        from docling.datamodel.base_models import InputFormat
        from docling_core.types.doc import DoclingDocument

        result, factory = self.convert()
        restored = DoclingDocument.model_validate(json.loads(json.dumps(result))["document"])
        self.assertEqual([item.self_ref for item, _ in restored.iterate_items()],
                         ["#/texts/0", "#/texts/1", "#/tables/0", "#/texts/2", "#/texts/3"])
        self.assertEqual([item.prov[0].page_no for item, _ in restored.iterate_items()], [7, 7, 7, 7, 8])
        self.assertEqual([prov.page_no for prov in restored.tables[0].prov], [7, 8])
        self.assertEqual(restored.tables[0].data.table_cells[0].col_span, 2)
        self.assertEqual(restored.tables[0].data.table_cells[1].text, "0010")
        options = factory.call_args.kwargs["format_options"][InputFormat.PDF].pipeline_options
        self.assertFalse(options.do_ocr)
        self.assertFalse(options.enable_remote_services)
        self.assertEqual(options.accelerator_options.device.value, "cpu")
        self.assertEqual(options.layout_options.model_spec.revision, pdf.MODEL_PINS["layout"]["revision"])
        factory.return_value.convert.assert_called_once_with(self.source, page_range=(7, 8))

    def test_partial_success_is_not_published_as_success(self):
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            self.convert("partial_success")

    def test_native_docling_tree_can_be_chunked_without_losing_table_context(self):
        result, _ = self.convert()
        chunks = chunk_document(result["document"], "synthetic-document")
        self.assertEqual([chunk["chunk_type"] for chunk in chunks], ["section", "table", "section"])
        self.assertEqual([chunk["section"] for chunk in chunks], [["Title"]] * 3)
        self.assertIn("0010\tSynthetic action", chunks[1]["text"])
        self.assertTrue(chunks[2]["text"].endswith("After table\nNext page"))

    def test_native_provenance_has_the_same_identity_before_and_after_json_serialization(self):
        result, _ = self.convert()
        chunks = chunk_document(result["document"], "SYNTHETIC@A:" + "0" * 64)
        identified = identify_chunk(result["document"], chunks[0])
        restored = json.loads(json.dumps(result))["document"]
        self.assertEqual(identified["evidence_id"], identify_chunk(restored, chunks[0])["evidence_id"])
        self.assertEqual(identified["evidence_locator"]["elements"][0]["pdf_page"], 7)

    def test_missing_requested_page_is_rejected(self):
        del self.doc.pages[8]
        with self.assertRaisesRegex(RuntimeError, "every requested page"):
            self.convert()

    def test_native_chinese_text_survives_export_and_quality_checks(self):
        value = "合成中文：电压 ±5%，温度 25°C；\n第二行\t检查项目。"
        self.doc.texts[1].text = value
        self.doc.texts[1].prov[0].charspan = (0, len(value))
        result, _ = self.convert()
        restored = json.loads(json.dumps(result, ensure_ascii=False))["document"]
        validate_document_quality(restored)
        self.assertEqual(restored["texts"][1]["text"], value)
        self.assertEqual(chunk_document(restored, "synthetic")[0]["text"], "Title\n" + value)

    def test_native_empty_pages_are_present_without_invented_content(self):
        from docling_core.types.doc import DoclingDocument, Size

        self.doc = DoclingDocument(name="empty-pages")
        for page in (7, 8):
            self.doc.add_page(page_no=page, size=Size(width=200, height=300))
        result, _ = self.convert()
        validate_document_quality(result["document"])
        self.assertEqual({int(page) for page in result["document"]["pages"]}, {7, 8})
        self.assertEqual(chunk_document(result["document"], "synthetic"), [])

    def test_missing_native_page_prevents_cli_output(self):
        from docling.datamodel.base_models import ConversionStatus

        del self.doc.pages[8]
        root = Path(self.directory.name)
        (root / "data/sources").mkdir(parents=True)
        source = {"id": "SYNTHETIC", "local_path": "synthetic.pdf", "pages": 8,
                  "document_code": "SYNTHETIC-MANUAL", "revision": "A", "firmware_scope": None,
                  "url": "https://example.com/synthetic.pdf", "accessed_at": "2026-10-29",
                  "sha256": pdf.file_sha256(self.source), "bytes": self.source.stat().st_size}
        (root / "data/sources/manifest.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
        output = root / "data/processed/result.json"
        with (patch.object(parse_pdf, "ROOT", root), patch.object(pdf, "verify_models"),
              patch("docling.document_converter.DocumentConverter") as factory):
            factory.return_value.convert.return_value = SimpleNamespace(
                status=ConversionStatus.SUCCESS, document=self.doc,
            )
            with self.assertRaisesRegex(RuntimeError, "every requested page"):
                parse_pdf.main(["--source", "SYNTHETIC", "--pages", "7", "8", "--output", str(output)])
        self.assertFalse(output.exists())

    def test_native_cross_page_prose_preserves_locations_and_parent(self):
        result, _ = self.convert()
        key = "SYNTHETIC@A:" + "0" * 64
        chunk = chunk_document(result["document"], key)[2]
        identified = identify_chunk(result["document"], chunk)
        source = {"id": "SYNTHETIC", "document_code": "SYNTHETIC-MANUAL", "revision": "A",
                  "sha256": "0" * 64, "firmware_scope": None, "url": "https://example.com/manual.pdf",
                  "accessed_at": "2026-10-29", "pages": 8}
        located = locate_chunk(identified, source)
        self.assertEqual(located["locations"], [{"pdf_page": 7, "printed_page": None},
                                                {"pdf_page": 8, "printed_page": None}])
        self.assertEqual(located["section"], ["Title"])
        self.assertEqual(located["document_key"], key)
        self.assertEqual(located["evidence_id"], identified["evidence_id"])

    def test_downloader_repairs_corrupt_cache_at_the_pinned_revision(self):
        pins = {"layout": {"repo_id": "example/model", "revision": "a" * 40,
                           "files": {"model.safetensors": hashlib.sha256(b"valid").hexdigest()}}}
        with patch.object(pdf, "MODELS_DIR", Path(self.directory.name)), patch.object(pdf, "MODEL_PINS", pins):
            target = pdf.MODELS_DIR / "example--model/model.safetensors"
            target.parent.mkdir()
            target.write_bytes(b"corrupt")
            with patch(
                "huggingface_hub.hf_hub_download", side_effect=lambda **kw: target.write_bytes(b"valid"),
            ) as fetch:
                download_parser_models.main()
                download_parser_models.main()
            fetch.assert_called_once_with(
                repo_id="example/model", revision="a" * 40, filename="model.safetensors",
                local_dir=target.parent, force_download=True,
            )


class ParseCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / "data/processed/result.json"
        source = self.root / "data/raw/synthetic.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"%PDF-1.4\nsynthetic")
        manifest = {"sources": [{"id": "SYNTHETIC", "local_path": "data/raw/synthetic.pdf", "pages": 2,
                                  "document_code": "SYNTHETIC-MANUAL", "revision": "A", "firmware_scope": None,
                                  "url": "https://example.com/synthetic.pdf", "accessed_at": "2026-10-28",
                                  "bytes": source.stat().st_size, "sha256": pdf.file_sha256(source)}]}
        (self.root / "data/sources").mkdir()
        (self.root / "data/sources/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.args = ["--source", "SYNTHETIC", "--pages", "1", "2", "--output", str(self.output)]
        self.addCleanup(patch.stopall)
        patch.object(parse_pdf, "ROOT", self.root).start()
        self.convert = patch.object(parse_pdf, "parse_pdf", return_value={"document": {}}).start()

    def test_writes_local_json_with_verified_source_identity(self):
        parse_pdf.main(self.args)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        digest = pdf.file_sha256(self.root / "data/raw/synthetic.pdf")
        self.assertEqual(result["source"], {
            "document_key": f"SYNTHETIC@A:{digest}", "source_id": "SYNTHETIC",
            "document_code": "SYNTHETIC-MANUAL", "revision": "A", "firmware_scope": None,
            "sha256": digest, "source_url": "https://example.com/synthetic.pdf", "accessed_at": "2026-10-28",
        })
        self.assertEqual(result["fault_codes"], [])
        self.assertEqual(result["chunks"], [])

    def test_serializes_raw_and_normalized_fault_codes_without_changing_cells(self):
        manifest_path = self.root / "data/sources/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = manifest["sources"][0]
        source["verified_pdf_pages"] = [1]
        source["printed_page_map"] = {"sha256": source["sha256"], "verification_ref": "synthetic.md",
                                      "pages": {"1": "iv"}}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        cells = []
        for text, row, column, header in (("编码（hex）", 0, 0, True), ("故障/辅助代码", 0, 1, True),
                                          (" 00a1 ", 1, 0, False), ("0002", 1, 1, False)):
            cells.append({
                "text": text, "column_header": header,
                "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                "start_col_offset_idx": column, "end_col_offset_idx": column + 1,
                "bbox": {"l": column * 50, "t": row * 20, "r": column * 50 + 40,
                         "b": row * 20 + 10, "coord_origin": "TOPLEFT"},
            })
        document = {"body": {"children": [{"$ref": "#/tables/0"}]},
                    "pages": {"1": {"page_no": 1, "size": {"width": 200, "height": 300}}},
                    "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": [{"page_no": 1}],
                                "data": {"num_rows": 2, "num_cols": 2, "table_cells": cells}}]}
        self.convert.return_value = {"document": document}
        parse_pdf.main(self.args)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(result["fault_codes"], [{
            "raw_code": " 00a1 ", "normalized_code": "00A1", "cell_ref": "#/tables/0/data/table_cells/2",
        }])
        self.assertEqual(result["document"]["tables"][0]["data"]["table_cells"][2]["text"], " 00a1 ")
        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["chunks"][0]["document_key"], result["source"]["document_key"])
        self.assertEqual(result["chunks"][0]["fault_codes"], result["fault_codes"])
        self.assertIn(" 00a1 \t0002", result["chunks"][0]["text"])
        self.assertRegex(result["chunks"][0]["evidence_id"], r"^ev1:[0-9a-f]{64}$")
        self.assertEqual(result["chunks"][0]["evidence_locator"]["sha256"], result["source"]["sha256"])
        self.assertEqual(result["chunks"][0]["locations"], [{"pdf_page": 1, "printed_page": "iv"}])
        self.assertEqual(result["source"]["printed_page_map"], source["printed_page_map"])
        self.assertEqual(result["chunks"][0]["table_row"], {"table_ref": "#/tables/0", "row_range": [1, 2]})

    def test_stale_printed_page_map_fails_before_parsing(self):
        path = self.root / "data/sources/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["sources"][0]["printed_page_map"] = {"sha256": "0" * 64}
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Printed page map"):
            parse_pdf.main(self.args)
        self.convert.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_evidence_provenance_leaves_no_output(self):
        self.convert.return_value = {"document": {
            "body": {"children": [{"$ref": "#/texts/0"}]},
            "texts": [{"self_ref": "#/texts/0", "label": "text", "text": "unanchored", "children": []}],
        }}
        with self.assertRaisesRegex(ValueError, "provenance"):
            parse_pdf.main(self.args)
        self.assertFalse(self.output.exists())

    def test_different_page_ranges_share_the_same_document_key(self):
        parse_pdf.main(self.args)
        first = json.loads(self.output.read_text(encoding="utf-8"))
        second_path = self.output.with_name("second.json")
        parse_pdf.main(["--source", "SYNTHETIC", "--pages", "2", "2", "--output", str(second_path)])
        second = json.loads(second_path.read_text(encoding="utf-8"))
        self.assertEqual(first["source"], second["source"])

    def test_missing_document_metadata_fails_before_parsing(self):
        path = self.root / "data/sources/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["sources"][0]["firmware_scope"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid firmware_scope"):
            parse_pdf.main(self.args)
        self.convert.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_ambiguous_source_selection_fails_before_parsing(self):
        path = self.root / "data/sources/manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["sources"].append({**manifest["sources"][0], "revision": "B", "sha256": "1" * 64})
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source IDs must be unique"):
            parse_pdf.main(self.args)
        self.convert.assert_not_called()

    def test_output_outside_processed_is_rejected_before_parsing(self):
        with self.assertRaises(SystemExit):
            parse_pdf.main(self.args[:-1] + [str(self.root / "published.json")])
        self.convert.assert_not_called()

    def test_existing_output_is_preserved(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("keep", encoding="utf-8")
        with self.assertRaises(SystemExit):
            parse_pdf.main(self.args)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep")
        self.convert.assert_not_called()

    def test_bad_source_fingerprint_fails_before_parsing(self):
        (self.root / "data/raw/synthetic.pdf").write_bytes(b"%PDF-1.4\nCORRUPTED")
        with self.assertRaises(ValueError):
            parse_pdf.main(self.args)
        self.convert.assert_not_called()

    def test_invalid_page_ranges_are_rejected_before_parsing(self):
        for start, end in ((0, 1), (2, 1), (1, 3)):
            with self.subTest(start=start, end=end), self.assertRaises(SystemExit):
                parse_pdf.main(["--source", "SYNTHETIC", "--pages", str(start), str(end),
                                "--output", str(self.output)])
        self.convert.assert_not_called()

    def test_failed_parse_leaves_no_output(self):
        self.convert.side_effect = RuntimeError("partial conversion")
        with self.assertRaises(RuntimeError):
            parse_pdf.main(self.args)
        self.assertFalse(self.output.exists())
