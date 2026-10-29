"""Display page labels and table rows never replace physical evidence identity."""

import unittest
from copy import deepcopy

from app.ingestion.evidence import identify_chunk
from app.ingestion.metadata import locate_chunk
from app.schemas.document import DocumentKey, printed_page_labels


def source():
    return {
        "id": "SYNTHETIC", "document_code": "SYNTHETIC-MANUAL", "revision": "A", "firmware_scope": None,
        "sha256": "a" * 64, "url": "https://example.com/synthetic.pdf", "accessed_at": "2026-10-29",
        "pages": 10, "verified_pdf_pages": [7, 8],
        "printed_page_map": {"sha256": "a" * 64, "verification_ref": "synthetic-verification.md",
                             "pages": {"7": "vii", "8": "A-1"}},
    }


def identified_chunk():
    document = {
        "pages": {str(n): {"page_no": n, "size": {"width": 200, "height": 300}} for n in (7, 8)},
        "texts": [{"prov": [
            {"page_no": n, "bbox": {"l": 10, "t": 20, "r": 30, "b": 40, "coord_origin": "TOPLEFT"},
             "charspan": [0, 5]} for n in (8, 7, 8)
        ]}],
    }
    return identify_chunk(document, {
        "document_key": DocumentKey.from_source(source()).value, "chunk_type": "section",
        "source_refs": ["#/texts/0"], "section": ["Parent", "Child"], "text": "synthetic prose",
    })


class PrintedPageLabelsTests(unittest.TestCase):
    def test_explicit_labels_preserve_roman_prefixed_and_zero_padded_values(self):
        self.assertEqual(printed_page_labels(source()), {7: "vii", 8: "A-1"})
        item = source()
        item["printed_page_map"]["pages"]["7"] = "007"
        self.assertEqual(printed_page_labels(item)[7], "007")

    def test_absent_map_does_not_infer_labels_from_verified_physical_pages(self):
        item = source()
        del item["printed_page_map"]
        self.assertEqual(printed_page_labels(item), {})

    def test_stale_missing_or_malformed_fingerprint_is_rejected(self):
        for mapping in (None, [], {}, {**source()["printed_page_map"], "sha256": "b" * 64}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(ValueError, "SHA-256"):
                printed_page_labels({**source(), "printed_page_map": mapping})

    def test_verification_reference_is_required(self):
        for reference in (None, "", " ", " spaced "):
            item = source()
            item["printed_page_map"]["verification_ref"] = reference
            with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, "verification reference"):
                printed_page_labels(item)

    def test_invalid_unverified_and_out_of_bounds_physical_keys_are_rejected(self):
        for page in (7, "07", "0", "-1", "7.0", "７", "11", "5"):
            item = source()
            item["printed_page_map"]["pages"] = {page: "vii"}
            with self.subTest(page=page), self.assertRaises(ValueError):
                printed_page_labels(item)

    def test_unknown_or_non_string_labels_are_not_published(self):
        for label in (None, 7, True, "", " 7", "7 ", "A\n1"):
            item = source()
            item["printed_page_map"]["pages"]["7"] = label
            with self.subTest(label=label), self.assertRaises(ValueError):
                printed_page_labels(item)

    def test_invalid_map_and_page_lists_are_rejected(self):
        for field, value in (("pages", True), ("pages", 0), ("verified_pdf_pages", None),
                             ("verified_pdf_pages", [True])):
            item = {**source(), field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                printed_page_labels(item)
        item = source()
        item["printed_page_map"]["pages"] = []
        with self.assertRaises(ValueError):
            printed_page_labels(item)


class ChunkLocationTests(unittest.TestCase):
    def test_cross_page_content_preserves_all_unique_pages_parent_and_section(self):
        piece, item = identified_chunk(), source()
        original = deepcopy((piece, item))
        result = locate_chunk(piece, item)
        self.assertEqual(result["locations"], [{"pdf_page": 7, "printed_page": "vii"},
                                                {"pdf_page": 8, "printed_page": "A-1"}])
        for field in ("document_key", "section", "source_refs", "evidence_id", "evidence_locator"):
            self.assertEqual(result[field], piece[field])
        self.assertIsNone(result["table_row"])
        self.assertEqual((piece, item), original)

    def test_unmapped_pages_stay_null_without_copying_neighbor_or_physical_label(self):
        item = source()
        del item["printed_page_map"]["pages"]["8"]
        self.assertEqual(locate_chunk(identified_chunk(), item)["locations"][1],
                         {"pdf_page": 8, "printed_page": None})
        del item["printed_page_map"]
        self.assertTrue(all(p["printed_page"] is None for p in locate_chunk(identified_chunk(), item)["locations"]))

    def test_corrected_display_labels_do_not_change_evidence_identity(self):
        piece = identified_chunk()
        item = source()
        item["printed_page_map"]["pages"]["8"] = "A-2"
        result = locate_chunk(piece, item)
        self.assertEqual(result["evidence_id"], piece["evidence_id"])
        self.assertEqual(result["evidence_locator"], piece["evidence_locator"])
        self.assertEqual(result["locations"][1]["printed_page"], "A-2")

    def test_different_source_or_revision_cannot_be_used_as_parent(self):
        for field, value in (("id", "OTHER"), ("revision", "B"), ("sha256", "b" * 64)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "parent document"):
                locate_chunk(identified_chunk(), {**source(), field: value})
        for field in ("source_id", "sha256"):
            piece = identified_chunk()
            piece["evidence_locator"][field] = "wrong"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "parent document"):
                locate_chunk(piece, source())

    def test_table_row_ranges_remain_scoped_to_their_table(self):
        for ref in ("#/tables/0", "#/tables/1"):
            piece = {**identified_chunk(), "chunk_type": "table_rows", "table_ref": ref, "row_range": [1, 10]}
            result = locate_chunk(piece, source())
            self.assertEqual(result["table_row"], {"table_ref": ref, "row_range": [1, 10]})
            result["table_row"]["row_range"][0] = 2
            self.assertEqual(piece["row_range"], [1, 10])

    def test_missing_or_invalid_physical_page_cannot_be_published(self):
        for pages in ([], [0], [11], [True]):
            piece = identified_chunk()
            piece["evidence_locator"]["elements"] = [{"pdf_page": page} for page in pages]
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "physical pages"):
                locate_chunk(piece, source())


if __name__ == "__main__":
    unittest.main()
