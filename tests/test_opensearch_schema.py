"""Index contracts and opt-in OpenSearch checks use only fabricated records/vectors."""

import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.retrieval.index_schema import index_record_id, load_mapping, validate_index_record


def record(**changes):
    # Shape fixture, not an actual manufacturer document or model-generated vector.
    return {"evidence_id": "ev1:" + "b" * 64, "document_key": "SYNTHETIC@A:" + "a" * 64,
            "source_id": "SYNTHETIC", "document_revision": "A", "record_kind": "manual_chunk",
            "chunk_type": "section", "model": ["TEST-DRIVE", "TEST-SECOND"],
            "firmware_scope": "ASCKX 2.16", "firmware_version": None, "firmware_state": "known",
            "synthetic": False, "available_at": "2026-01-01T08:00:00+08:00", "alarm_code": ["00a1"],
            "text": "合成字段测试，非厂商原文。", "embedding": [1.0] + [0.0] * 1023, **changes}


def event_record(**changes):
    return record(evidence_id="WO-fixture", document_key=None, source_id=None, document_revision=None,
                  record_kind="work_order", chunk_type=None, firmware_scope=None, firmware_version=None,
                  firmware_state="unknown", synthetic=True, **changes)


class IndexSchemaTests(unittest.TestCase):
    def setUp(self):
        self.mapping = load_mapping()

    def test_tampered_mapping_bytes_fail_before_use(self):
        with patch.object(Path, "read_bytes", return_value=b"{}"), self.assertRaisesRegex(ValueError, "fingerprint"):
            load_mapping()

    def test_manufacturer_notes_and_events_keep_distinct_identity_and_firmware_semantics(self):
        fixtures = [record(), record(firmware_scope=None, firmware_state="unrestricted"), event_record(),
                    {**event_record(), "firmware_version": "ASCKX 2.16", "firmware_state": "known"},
                    record(evidence_id="K-fixture", record_kind="knowledge_note", document_key=None, chunk_type=None),
                    record(evidence_id="K-synthetic", record_kind="knowledge_note", document_key=None,
                           source_id=None, chunk_type=None, synthetic=True, document_revision="SIM-1")]
        for fixture in fixtures:
            with self.subTest(kind=fixture["record_kind"], state=fixture["firmware_state"]):
                original = deepcopy(fixture)
                validate_index_record(fixture, self.mapping)
                self.assertEqual(fixture, original)

    def test_required_fields_and_evaluation_keys_are_rejected(self):
        for field in record():
            invalid = record()
            invalid.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_index_record(invalid, self.mapping)
        for field in ("gold_evidence_ids", "expected_status", "acceptable_cause_ids", "review_status"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_index_record(record(**{field: "forbidden"}), self.mapping)

    def test_null_and_parent_metadata_cannot_be_silently_reinterpreted(self):
        invalid = [record(firmware_scope=None), record(firmware_version="ASCKX 2.16"),
                   record(firmware_scope="unknown"), record(firmware_scope="A"),
                   record(document_revision="B"), record(source_id="OTHER"), record(synthetic=True),
                   record(evidence_id="WO1"), {**event_record(), "firmware_state": "unrestricted"},
                   {**event_record(), "document_revision": "A"}, {**event_record(), "document_key": "fake"}]
        for index, value in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(ValueError):
                validate_index_record(value, self.mapping)

    def test_keywords_and_times_require_explicit_types(self):
        for changes in ({"model": []}, {"model": "TEST-DRIVE"}, {"model": ["A", "A"]},
                        {"model": [42]}, {"alarm_code": [161]}, {"synthetic": "false"},
                        {"available_at": "2026-01-01"}, {"available_at": "2026-01-01T08:00:00"},
                        {"record_kind": "evaluation"}, {"text": " "}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValueError):
                validate_index_record(record(**changes), self.mapping)

    def test_vectors_reject_wrong_dimension_boolean_nonfinite_and_zero(self):
        for vector in ([1.0], [0.0] * 1024, [True] + [0.0] * 1023,
                       [float("nan")] + [0.0] * 1023, [float("inf")] + [0.0] * 1023,
                       [10 ** 400] + [0.0] * 1023):
            with self.subTest(first=vector[0]), self.assertRaises(ValueError):
                validate_index_record(record(embedding=vector), self.mapping)

    def test_index_ids_include_document_revision_and_record_kind(self):
        first = record()
        revision = record(document_key="SYNTHETIC@B:" + "a" * 64, document_revision="B")
        self.assertNotEqual(index_record_id(first), index_record_id(revision))
        self.assertEqual(index_record_id(first), index_record_id({**first, "embedding": [2.0] * 1024}))
        event = event_record()
        self.assertNotEqual(index_record_id(event), index_record_id({**event, "record_kind": "alarm"}))
        self.assertRegex(index_record_id(first), r"^[0-9a-f]{64}$")

    def test_record_validation_does_not_open_corpus_or_evaluation_files(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("Unexpected file read")):
            validate_index_record(record(), self.mapping)
            index_record_id(record())


@unittest.skipUnless(os.environ.get("FORGERCA_TEST_OPENSEARCH") == "1",
                     "Enable explicitly for a disposable local OpenSearch test index")
class OpenSearchMappingTests(unittest.TestCase):
    def test_mapping_roundtrip_exact_filters_and_rejected_documents(self):
        index = "forgerca-mapping-test-" + uuid4().hex
        base = "http://127.0.0.1:9200/" + index

        def request(path="", payload=None, method="GET"):
            body = (json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    if payload is not None else None)
            req = Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=30) as response:
                return json.load(response)

        spec = load_mapping()
        self.assertTrue(request(payload=spec, method="PUT")["acknowledged"])
        self.addCleanup(request, method="DELETE")  # Only the UUID-named index created by this test.
        self.assertEqual(request("/_mapping")[index]["mappings"], spec["mappings"])
        fixtures = [record(), record(document_key="SYNTHETIC@B:" + "a" * 64, document_revision="B",
                                     firmware_scope=None, firmware_state="unrestricted"), event_record()]
        for value in fixtures:
            validate_index_record(value, spec)
            path = "/_doc/" + index_record_id(value)
            self.assertEqual(request(path, value, "PUT")["result"], "created")
            self.assertEqual(request(path)["_source"], value)
        request("/_refresh", method="POST")

        def count(query):
            return request("/_count", {"query": query}, "POST")["count"]

        self.assertEqual(count({"match_all": {}}), 3)
        for field, term, expected in (("model", "TEST-DRIVE", 3), ("model", "TEST-SECOND", 3),
                                      ("model", "test-drive", 0), ("model", "TEST", 0),
                                      ("document_revision", "A", 1), ("document_revision", "a", 0),
                                      ("alarm_code", "00a1", 3), ("alarm_code", "00A1", 0),
                                      ("alarm_code", "a1", 0), ("firmware_scope", "ASCKX 2.16", 1),
                                      ("firmware_state", "unrestricted", 1), ("firmware_state", "unknown", 1),
                                      ("record_kind", "manual_chunk", 2), ("synthetic", True, 1)):
            with self.subTest(field=field, term=term):
                self.assertEqual(count({"term": {field: term}}), expected)
        self.assertEqual(count({"exists": {"field": "firmware_scope"}}), 1)
        self.assertEqual(count({"exists": {"field": "firmware_version"}}), 0)
        self.assertEqual(count({"range": {"available_at": {"lte": "2026-01-01T00:00:00Z"}}}), 3)
        self.assertEqual(count({"range": {"available_at": {"lt": "2026-01-01T00:00:00Z"}}}), 0)
        for changes in ({"embedding": [1.0, 0.0]}, {"gold_evidence_ids": ["forbidden"]},
                        {"model": {"nested": "no"}}, {"available_at": "invalid-date"}):
            with self.subTest(fields=list(changes)), self.assertRaises(HTTPError) as raised:
                request("/_doc/invalid", record(**changes), "PUT")
            with raised.exception as error:
                self.assertEqual(error.code, 400, error.read())
        self.assertEqual(count({"match_all": {}}), 3)


if __name__ == "__main__":
    unittest.main()
