"""Regression checks for corrupt provenance and evaluation leakage."""

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.validate_data import check_raw, load_data, validate


class DataValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = load_data()

    def setUp(self):
        self.data = deepcopy(self.seed)

    def test_seed_is_consistent(self):
        self.assertEqual(validate(self.data)["questions"], 17)

    def test_missing_gold_evidence_is_rejected(self):
        self.data["evaluations"]["dev"][0]["gold_evidence_ids"] = ["MISSING"]
        with self.assertRaisesRegex(ValueError, "Unknown gold evidence"):
            validate(self.data)

    def test_future_closed_work_order_is_rejected(self):
        self.data["evaluations"]["dev"][0]["as_of"] = "2026-06-01T09:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "Future evidence"):
            validate(self.data)

    def test_wrong_model_evidence_is_rejected(self):
        self.data["evaluations"]["dev"][0]["gold_evidence_ids"] = ["K009"]
        with self.assertRaisesRegex(ValueError, "Wrong-model"):
            validate(self.data)

    def test_shared_incident_across_splits_is_rejected(self):
        self.data["evaluations"]["demo"][0]["incident_group"] = self.data["evaluations"]["dev"][0]["incident_group"]
        with self.assertRaisesRegex(ValueError, "Incident leaks"):
            validate(self.data)

    def test_target_incident_in_corpus_is_rejected(self):
        self.data["evaluations"]["dev"][0]["incident_group"] = "history-1"
        with self.assertRaisesRegex(ValueError, "Target incident leaked"):
            validate(self.data)

    def test_false_real_event_flag_is_rejected(self):
        self.data["corpus"]["work_order"][0]["synthetic"] = False
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            validate(self.data)

    def test_alarm_asset_mismatch_is_rejected(self):
        self.data["corpus"]["alarm"][0]["asset_id"] = "SYN-WRONG"
        with self.assertRaisesRegex(ValueError, "Alarm/work-order mismatch"):
            validate(self.data)

    def test_dangling_graph_evidence_is_rejected(self):
        self.data["graph"]["edges"][0]["evidence_id"] = "MISSING"
        with self.assertRaisesRegex(ValueError, "Dangling graph evidence"):
            validate(self.data)

    def test_duplicate_evidence_is_rejected(self):
        self.data["corpus"]["knowledge_note"].append(self.data["corpus"]["knowledge_note"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate evidence"):
            validate(self.data)

    def test_unsupported_firmware_is_rejected(self):
        self.data["evaluations"]["dev"][0]["firmware_version"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unsupported firmware"):
            validate(self.data)

    def test_raw_hash_mismatch_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "data/raw/abb/example.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"%PDF-example")
            source = {"local_path": "data/raw/abb/example.pdf", "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            check_raw([source], root)
            source["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                check_raw([source], root)
            source["local_path"] = "../outside.pdf"
            with self.assertRaisesRegex(ValueError, "Unsafe raw path"):
                check_raw([source], root)


if __name__ == "__main__":
    unittest.main()
