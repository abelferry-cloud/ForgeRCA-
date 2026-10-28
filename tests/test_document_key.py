"""Contract tests for stable document keys (M1-08)."""

from __future__ import annotations

import json
import re
import unittest
from copy import deepcopy
from pathlib import Path

from app.schemas.document import (
    FIRMWARE_PATTERN,
    DocumentKey,
    DocumentKeyConflict,
    DocumentKeyError,
    document_keys,
    parse_key,
)
from scripts.validate_data import validate_firmware

ROOT = Path(__file__).resolve().parents[1]


def load_sources():
    data = json.loads((ROOT / "data/sources/manifest.json").read_text(encoding="utf-8"))
    return data["sources"]


class DocumentKeyTests(unittest.TestCase):
    def setUp(self):
        self.sources = load_sources()
        self.firmware = next(source for source in self.sources if source["id"] == "ABB-FW-H-ZH")
        self.hardware = next(source for source in self.sources if source["id"] == "ABB-HW-D-ZH")

    def test_manifest_sources_produce_expected_keys(self):
        with self.subTest(source="firmware"):
            key = DocumentKey.from_source(self.firmware)
            self.assertEqual(key.value, f"ABB-FW-H-ZH@H:{self.firmware['sha256']}")
            self.assertEqual(key.document_code, "3AXD50000016430")
            self.assertEqual(key.firmware_scope, "ASCKX 2.16")
            self.assertEqual(key.source_url, self.firmware["url"])
            self.assertEqual(key.accessed_at, "2026-10-13")
        with self.subTest(source="hardware"):
            key = DocumentKey.from_source(self.hardware)
            self.assertEqual(key.value, f"ABB-HW-D-ZH@D:{self.hardware['sha256']}")
            # ``null`` firmware scope means "not firmware-limited" and must survive as None.
            self.assertIsNone(key.firmware_scope)

    def test_every_manifest_source_yields_one_key(self):
        keys = document_keys(self.sources)
        self.assertEqual(len(keys), len(self.sources))
        for source in self.sources:
            with self.subTest(source=source["id"]):
                self.assertIn(DocumentKey.from_source(source).value, keys)

    def test_key_moves_with_revision_and_digest(self):
        base = DocumentKey.from_source(self.firmware)
        revised = deepcopy(self.firmware)
        revised["revision"] = "I"
        replaced = deepcopy(self.firmware)
        replaced["sha256"] = "0" * 64
        self.assertNotEqual(base.value, DocumentKey.from_source(revised).value)
        self.assertNotEqual(base.value, DocumentKey.from_source(replaced).value)

    def test_key_ignores_non_identity_fields(self):
        changed = deepcopy(self.firmware)
        changed["document_code"] = "3AXD50000999999"
        changed["title"] = "另一个标题"
        changed["url"] = "https://example.com/mirror.pdf"
        changed["accessed_at"] = "2026-10-28"
        self.assertEqual(DocumentKey.from_source(self.firmware).value, DocumentKey.from_source(changed).value)

    def test_matching_digest_prefix_does_not_alias_a_different_file(self):
        changed = deepcopy(self.firmware)
        changed["sha256"] = self.firmware["sha256"][:12] + "0" * 52
        self.assertNotEqual(DocumentKey.from_source(self.firmware).value, DocumentKey.from_source(changed).value)

    def test_revisions_of_one_document_code_have_distinct_keys(self):
        revised = deepcopy(self.firmware)
        revised.update(revision="I", sha256="1" * 64)
        keys = document_keys([self.firmware, revised])
        self.assertEqual(len(keys), 2)
        self.assertEqual({key.document_code for key in keys.values()}, {self.firmware["document_code"]})

    def test_source_order_does_not_change_keys(self):
        self.assertEqual(document_keys(self.sources), document_keys(reversed(self.sources)))

    def test_invalid_identifier_separators_are_rejected(self):
        for field in ("id", "revision"):
            for value in ("", "has space", "with@separator", "with:separator", None):
                with self.subTest(field=field, value=value):
                    source = deepcopy(self.firmware)
                    source[field] = value
                    with self.assertRaisesRegex(DocumentKeyError, f"Invalid {field}"):
                        DocumentKey.from_source(source)

    def test_invalid_digest_is_rejected(self):
        for value in ("E6ED9EAB8C6A06AF", self.firmware["sha256"][:63], self.firmware["sha256"] + "0", "", None):
            with self.subTest(sha256=value):
                source = deepcopy(self.firmware)
                source["sha256"] = value
                with self.assertRaisesRegex(DocumentKeyError, "Invalid sha256"):
                    DocumentKey.from_source(source)

    def test_missing_identity_fields_are_rejected(self):
        for field in ("id", "document_code", "revision", "firmware_scope", "sha256", "url", "accessed_at"):
            with self.subTest(field=field):
                source = deepcopy(self.firmware)
                source.pop(field)
                with self.assertRaisesRegex(DocumentKeyError, f"Invalid {field}"):
                    DocumentKey.from_source(source)

    def test_revision_cannot_stand_in_for_firmware(self):
        source = deepcopy(self.firmware)
        source["firmware_scope"] = source["revision"]
        with self.assertRaisesRegex(DocumentKeyError, "Invalid firmware_scope"):
            DocumentKey.from_source(source)

    def test_accessed_at_requires_plain_iso_date(self):
        for value in ("2026-13-01", "2026-1-3", "2026-10-13T00:00:00+08:00", "2026-10-13Z"):
            with self.subTest(accessed_at=value):
                source = deepcopy(self.firmware)
                source["accessed_at"] = value
                with self.assertRaisesRegex(DocumentKeyError, "Invalid accessed_at"):
                    DocumentKey.from_source(source)

    def test_duplicate_revision_slot_is_rejected(self):
        clone = deepcopy(self.firmware)
        clone["sha256"] = "1" * 64
        with self.assertRaisesRegex(DocumentKeyConflict, "Duplicate document revision"):
            document_keys([self.firmware, clone])

    def test_duplicate_key_is_rejected_even_with_different_metadata(self):
        for code in (self.firmware["document_code"], "DIFFERENT"):
            with self.subTest(document_code=code):
                clone = deepcopy(self.firmware)
                clone["document_code"] = code
                with self.assertRaisesRegex(DocumentKeyConflict, "Duplicate document key"):
                    document_keys([self.firmware, clone])

    def test_duplicate_digest_is_rejected(self):
        clone = deepcopy(self.firmware)
        clone["id"] = "ABB-FW-H-ZH-COPY"
        with self.assertRaisesRegex(DocumentKeyConflict, "Duplicate document digest"):
            document_keys([self.firmware, clone])

    def test_parse_key_round_trip(self):
        key = DocumentKey.from_source(self.firmware)
        parsed = parse_key(key.value)
        self.assertEqual(parsed.source_id, "ABB-FW-H-ZH")
        self.assertEqual(parsed.revision, "H")
        self.assertEqual(parsed.sha256, key.sha256)

    def test_parse_key_rejects_malformed_values(self):
        key = DocumentKey.from_source(self.firmware).value
        for value in (
            key.upper(),
            key[:-1],
            key + "0",
            "ABB-FW-H-ZH:e6ed9eab8c6a",
            "ABB-FW-H-ZH@H@e6ed9eab8c6a",
            "ABB-FW-H-ZH@H",
            "",
            None,
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(DocumentKeyError, "Invalid document key"):
                    parse_key(value)

    def test_firmware_pattern_matches_the_data_validator(self):
        # The key module and the data validator must never drift apart.
        samples = (
            None,
            "ASCKX 2.16",
            "ASCKX 2.1",
            "ASCKX 10.20",
            "H",
            "",
            "unknown",
            "ASCKX 2.16 ",
            "ASCKX2.16",
            "ASCKX 2",
            2.16,
        )
        for value in samples:
            with self.subTest(value=value):
                try:
                    validate_firmware(value, "probe")
                    accepted = True
                except ValueError:
                    accepted = False
                matches = value is None or (
                    isinstance(value, str) and re.fullmatch(FIRMWARE_PATTERN, value) is not None
                )
                self.assertEqual(accepted, matches)


if __name__ == "__main__":
    unittest.main()
