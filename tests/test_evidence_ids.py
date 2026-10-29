"""Physical evidence identity must not depend on transient parser numbering."""

import unittest
from copy import deepcopy

from app.ingestion.evidence import identify_chunk

KEY = "SYNTHETIC@A:" + "a" * 64


def bbox(left=10, t=20, r=30, b=40, origin="TOPLEFT"):
    return {"l": left, "t": t, "r": r, "b": b, "coord_origin": origin}


def prov(page=7, box=None, span=(0, 5)):
    return {"page_no": page, "bbox": box or bbox(), "charspan": list(span)}


def document():
    return {
        "pages": {str(n): {"page_no": n, "size": {"width": 200, "height": 300}} for n in (7, 8)},
        "texts": [{"self_ref": "#/texts/0", "text": "alpha", "prov": [prov()]},
                  {"self_ref": "#/texts/1", "text": "bravo", "prov": [prov(box=bbox(t=50, b=60))]}],
        "pictures": [{"self_ref": "#/pictures/0", "prov": [prov(box=bbox(left=50, r=60))]}],
        "tables": [{"self_ref": "#/tables/0", "prov": [prov()], "data": {"table_cells": [
            {"text": "0010", "bbox": bbox(t=100, b=110), "start_row_offset_idx": 1},
            {"text": "shared action", "bbox": bbox(t=100, b=190), "start_row_offset_idx": 1},
            {"text": "next", "bbox": bbox(t=200, b=210), "start_row_offset_idx": 10},
        ]}}],
    }


def chunk(refs=("#/texts/0",), **extra):
    return {"document_key": KEY, "chunk_type": "section", "source_refs": list(refs),
            "heading_refs": [], "text": "display text", **extra}


class EvidenceIdTests(unittest.TestCase):
    def test_repeated_identity_is_versioned_and_inputs_are_unchanged(self):
        doc, piece = document(), chunk()
        original = deepcopy((doc, piece))
        first = identify_chunk(doc, piece)
        self.assertEqual(first, identify_chunk(doc, piece))
        self.assertRegex(first["evidence_id"], r"^ev1:[0-9a-f]{64}$")
        self.assertEqual(first["evidence_id"],
                         "ev1:61270d39d1cfd3aa18b816acb51a6b7417166d4edc0b7ff3bd3ccba277e3e82b")
        self.assertEqual(first["evidence_locator"], {
            "version": 1, "source_id": "SYNTHETIC", "sha256": "a" * 64,
            "elements": [{"kind": "text", "pdf_page": 7, "bbox_milli": [10000, 20000, 30000, 40000],
                          "charspan": [0, 5]}],
        })
        self.assertEqual((doc, piece), original)

    def test_reference_order_duplicates_and_display_metadata_do_not_change_id(self):
        doc = document()
        first = identify_chunk(doc, chunk(("#/texts/0", "#/texts/1")))
        second = identify_chunk(doc, chunk(("#/texts/1", "#/texts/0", "#/texts/0"),
                                           text="reformatted", section=["changed heading"],
                                           heading_refs=["#/texts/99"], rank=999, chunk_type="renamed"))
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual(first["evidence_locator"], second["evidence_locator"])

    def test_text_array_renumbering_and_unrelated_items_do_not_change_id(self):
        doc = document()
        expected = identify_chunk(doc, chunk())["evidence_id"]
        doc["texts"].reverse()
        doc["texts"].insert(0, {"text": "unrelated"})
        for index, item in enumerate(doc["texts"]):
            item["self_ref"] = f"#/texts/{index}"
        self.assertEqual(identify_chunk(doc, chunk(("#/texts/2",)))["evidence_id"], expected)

    def test_reordered_chunks_and_duplicate_coverage_keep_their_ids(self):
        doc = document()
        pieces = [chunk(("#/texts/0",)), chunk(("#/texts/1",))]
        expected = [identify_chunk(doc, piece)["evidence_id"] for piece in pieces]
        actual = [identify_chunk(doc, piece)["evidence_id"] for piece in [pieces[1], pieces[0], pieces[1]]]
        self.assertEqual(actual, [expected[1], expected[0], expected[1]])

    def test_different_source_or_pdf_digest_changes_identity(self):
        expected = identify_chunk(document(), chunk())["evidence_id"]
        for key in ("OTHER@A:" + "a" * 64, "SYNTHETIC@A:" + "b" * 64):
            with self.subTest(key=key):
                self.assertNotEqual(expected, identify_chunk(document(), chunk(document_key=key))["evidence_id"])

    def test_document_revision_metadata_alone_does_not_change_physical_identity(self):
        self.assertEqual(identify_chunk(document(), chunk())["evidence_id"],
                         identify_chunk(document(), chunk(document_key="SYNTHETIC@B:" + "a" * 64))["evidence_id"])

    def test_changed_page_box_span_or_coverage_changes_identity(self):
        expected = identify_chunk(document(), chunk())["evidence_id"]
        for changes in ({"page_no": 8}, {"bbox": bbox(left=11)}, {"charspan": [1, 5]}):
            with self.subTest(changes=changes):
                doc = document()
                doc["texts"][0]["prov"][0].update(changes)
                self.assertNotEqual(expected, identify_chunk(doc, chunk())["evidence_id"])
        self.assertNotEqual(expected, identify_chunk(document(), chunk(("#/texts/0", "#/texts/1")))["evidence_id"])

    def test_identical_text_at_different_positions_is_not_conflated(self):
        doc = document()
        doc["texts"][1]["text"] = doc["texts"][0]["text"]
        self.assertNotEqual(identify_chunk(doc, chunk())["evidence_id"],
                            identify_chunk(doc, chunk(("#/texts/1",)))["evidence_id"])

    def test_origin_numeric_representation_and_subprecision_noise_are_canonical(self):
        expected = identify_chunk(document(), chunk())["evidence_id"]
        for box in (bbox(10.0, 20.0, 30.0, 40.0), bbox(t=20.00001), bbox(t=280, b=260, origin="BOTTOMLEFT")):
            with self.subTest(box=box):
                doc = document()
                doc["texts"][0]["prov"][0]["bbox"] = box
                self.assertEqual(expected, identify_chunk(doc, chunk())["evidence_id"])

    def test_multiple_text_pages_and_provenance_order_are_preserved(self):
        doc = document()
        doc["texts"][0]["prov"].append(prov(page=8, span=(5, 10)))
        result = identify_chunk(doc, chunk())
        self.assertEqual({e["pdf_page"] for e in result["evidence_locator"]["elements"]}, {7, 8})
        doc["texts"][0]["prov"].reverse()
        self.assertEqual(result["evidence_id"], identify_chunk(doc, chunk())["evidence_id"])

    def test_picture_coordinates_participate_without_inventing_text(self):
        result = identify_chunk(document(), chunk(("#/pictures/0",)))
        self.assertEqual(result["evidence_locator"]["elements"][0]["kind"], "picture")
        self.assertNotIn("charspan", result["evidence_locator"]["elements"][0])

    def test_table_and_cell_array_renumbering_do_not_change_identity(self):
        doc = document()
        piece = chunk(("#/tables/0/data/table_cells/0", "#/tables/0/data/table_cells/1"),
                      chunk_type="fault_rows", row_range=[1, 10])
        expected = identify_chunk(doc, piece)["evidence_id"]
        doc["tables"][0]["data"]["table_cells"].reverse()
        doc["tables"].insert(0, {"data": {"table_cells": []}})
        doc["tables"][1]["self_ref"] = "#/tables/1"
        for cell in doc["tables"][1]["data"]["table_cells"]:
            cell["start_row_offset_idx"] += 100
        renamed = chunk(("#/tables/1/data/table_cells/2", "#/tables/1/data/table_cells/1"), row_range=[101, 110])
        self.assertEqual(expected, identify_chunk(doc, renamed)["evidence_id"])
        self.assertNotEqual(expected, identify_chunk(doc, chunk(("#/tables/1/data/table_cells/0",)))["evidence_id"])

    def test_missing_or_ambiguous_table_cell_positions_fail(self):
        for missing_box, pages in ((True, [prov()]), (False, [prov(), prov(page=8)]), (False, [])):
            with self.subTest(missing_box=missing_box, pages=len(pages)):
                doc = document()
                doc["tables"][0]["prov"] = pages
                if missing_box:
                    doc["tables"][0]["data"]["table_cells"][0]["bbox"] = None
                with self.assertRaises(ValueError):
                    identify_chunk(doc, chunk(("#/tables/0/data/table_cells/0",)))

    def test_invalid_references_or_empty_coverage_fail_without_index_fallback(self):
        for refs in ((), ("#/texts/99",), ("#/texts/-1",), ("#/groups/0",), ("#/tables/0",)):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                identify_chunk(document(), chunk(refs))

    def test_missing_or_invalid_provenance_fails(self):
        for value in (None, [], [{"page_no": 7}], [prov(page=True)], [prov(page=0)], [prov(page=9)],
                      [prov(span=(-1, 5))], [prov(span=(5, 1))], [prov(span=(0, True))]):
            with self.subTest(value=value):
                doc = document()
                doc["texts"][0]["prov"] = value
                with self.assertRaises(ValueError):
                    identify_chunk(doc, chunk())

    def test_invalid_geometry_and_page_dimensions_fail(self):
        for box in (bbox(left=float("nan")), bbox(r=float("inf")), bbox(left=True), bbox(left="10"),
                    bbox(left=-1), bbox(r=201), bbox(b=301), bbox(r=10), bbox(t=41), bbox(origin="UNKNOWN")):
            with self.subTest(box=box):
                doc = document()
                doc["texts"][0]["prov"][0]["bbox"] = box
                with self.assertRaises(ValueError):
                    identify_chunk(doc, chunk())
        doc = document()
        doc["pages"]["7"]["size"]["height"] = 0
        with self.assertRaises(ValueError):
            identify_chunk(doc, chunk())


if __name__ == "__main__":
    unittest.main()
