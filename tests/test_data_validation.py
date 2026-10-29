"""Regression checks for corrupt provenance and evaluation leakage."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.validate_data import check_raw, load_data, validate


class DataValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = load_data()

    def setUp(self):
        self.data = deepcopy(self.seed)

    def test_seed_is_consistent(self):
        self.assertEqual(validate(self.data)["questions"], 17)

    def test_stale_or_unverified_printed_page_mapping_is_rejected(self):
        for field, value in (("sha256", "0" * 64), ("pages", {"1": "1"})):
            data = deepcopy(self.seed)
            data["sources"][0]["printed_page_map"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Printed page"):
                validate(data)

    def test_direct_script_works_without_repository_on_pythonpath(self):
        script = Path(__file__).resolve().parents[1] / "scripts/validate_data.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-I", str(script)], cwd=directory,
                capture_output=True, text=True, encoding="utf-8", timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"sources": 2', result.stdout)

    def test_missing_document_metadata_is_rejected(self):
        for field in ("document_code", "revision", "url", "accessed_at"):
            with self.subTest(field=field):
                data = deepcopy(self.seed)
                del data["sources"][0][field]
                with self.assertRaisesRegex(ValueError, f"Invalid {field}"):
                    validate(data)

    def test_duplicate_document_bytes_are_rejected(self):
        self.data["sources"][1]["sha256"] = self.data["sources"][0]["sha256"]
        with self.assertRaisesRegex(ValueError, "Duplicate document digest"):
            validate(self.data)

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
        self.data["evaluations"]["dev"][0]["firmware_version"] = "ASCKX 0.00"
        with self.assertRaisesRegex(ValueError, "Unsupported firmware"):
            validate(self.data)

    def test_mismatched_firmware_is_rejected_for_insufficient_question(self):
        self.data["evaluations"]["dev"][8]["firmware_version"] = "ASCKX 0.00"
        with self.assertRaisesRegex(ValueError, "Unsupported firmware: Q009 K001"):
            validate(self.data)

    def test_unknown_question_firmware_cannot_support_diagnosis(self):
        self.data["evaluations"]["dev"][0]["firmware_version"] = None
        with self.assertRaisesRegex(ValueError, "Unknown firmware: Q001 K001"):
            validate(self.data)

    def test_unknown_history_firmware_cannot_support_diagnosis(self):
        self.data["corpus"]["work_order"][0]["firmware_version"] = None
        for alarm in self.data["corpus"]["alarm"]:
            if alarm["work_order_id"] == "WO001":
                alarm["firmware_version"] = None
        with self.assertRaisesRegex(ValueError, "Unknown firmware: Q001 WO001"):
            validate(self.data)

    def test_unknown_firmware_can_explain_insufficient_question(self):
        question = self.data["evaluations"]["dev"][11]
        self.assertIsNone(question["firmware_version"])
        self.assertEqual(question["gold_evidence_ids"], ["K008"])
        self.assertEqual(validate(self.data)["questions"], 17)

    def test_unrestricted_hardware_note_allows_unknown_firmware(self):
        question = self.data["evaluations"]["dev"][5]
        question["firmware_version"] = None
        question["gold_evidence_ids"] = ["K007"]
        self.assertEqual(validate(self.data)["questions"], 17)

    def test_invalid_firmware_values_are_not_treated_as_matches(self):
        for value in ("unknown", "", "H", False, 2.16):
            with self.subTest(value=value):
                data = deepcopy(self.seed)
                data["evaluations"]["dev"][0]["firmware_version"] = value
                data["evaluations"]["dev"][0]["gold_evidence_ids"] = ["WO001"]
                data["corpus"]["work_order"][0]["firmware_version"] = value
                for alarm in data["corpus"]["alarm"]:
                    if alarm["work_order_id"] == "WO001":
                        alarm["firmware_version"] = value
                with self.assertRaisesRegex(ValueError, "Invalid firmware"):
                    validate(data)

    def test_note_model_must_belong_to_source(self):
        note = deepcopy(self.data["corpus"]["knowledge_note"][7])
        note.update(id="K010", model="SIM-OTHER-DRIVE")
        self.data["corpus"]["knowledge_note"].append(note)
        with self.assertRaisesRegex(ValueError, "Source model mismatch: K010"):
            validate(self.data)

    def test_source_models_must_be_explicit(self):
        for models in ([], "ACS580-01", [""], [None], ["ACS580-01", "ACS580-01"]):
            with self.subTest(models=models):
                self.data["sources"][0]["models"] = models
                with self.assertRaisesRegex(ValueError, "Invalid source models"):
                    validate(self.data)

    def test_revision_and_firmware_scope_must_match_source(self):
        for field, value, message in (
            ("document_revision", "ASCKX 2.16", "Revision mismatch"),
            ("firmware_scope", "ASCKX 0.00", "Firmware scope mismatch"),
            ("firmware_scope", None, "Firmware scope mismatch"),
        ):
            with self.subTest(field=field, value=value):
                data = deepcopy(self.seed)
                data["corpus"]["knowledge_note"][0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate(data)

    def test_locator_page_and_text_are_validated(self):
        for field, value, message in (
            ("pdf_page", 536.0, "Invalid PDF page"),
            ("pdf_page", True, "Invalid PDF page"),
            ("pdf_page", 535, "Unverified PDF page"),
            ("printed_page", "   ", "Incomplete locator"),
            ("section", "   ", "Incomplete locator"),
        ):
            with self.subTest(field=field, value=value):
                data = deepcopy(self.seed)
                data["corpus"]["knowledge_note"][0]["locator"][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate(data)

    def test_question_model_and_status_must_agree(self):
        for model, status in (("SIM-OTHER-DRIVE", "insufficient"), ("ACS580-01", "out_of_scope")):
            with self.subTest(model=model, status=status):
                data = deepcopy(self.seed)
                question = data["evaluations"]["dev"][10]
                question.update(model=model, expected_status=status)
                with self.assertRaisesRegex(ValueError, "Model/status mismatch"):
                    validate(data)

    def test_missing_model_is_not_an_out_of_scope_model(self):
        for model in (None, "", "   "):
            with self.subTest(model=model):
                self.data["evaluations"]["dev"][10]["model"] = model
                with self.assertRaisesRegex(ValueError, "Invalid question model"):
                    validate(self.data)

    def test_raw_hash_mismatch_and_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "data/raw/abb/example.pdf"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"%PDF-example")
            source = {
                "local_path": "data/raw/abb/example.pdf",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            check_raw([source], root)
            source["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                check_raw([source], root)
            source["local_path"] = "../outside.pdf"
            with self.assertRaisesRegex(ValueError, "Unsafe raw path"):
                check_raw([source], root)


if __name__ == "__main__":
    unittest.main()
