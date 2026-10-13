"""Regression checks for the M0-08 sensitive-file gate."""

import tempfile
import unittest
from pathlib import Path

from scripts.check_sensitive_files import (
    MAX_TRACKED_BYTES,
    check_ignore_rules,
    check_path,
    check_text,
    find_issues,
    is_placeholder,
)


class ForbiddenPathTests(unittest.TestCase):
    def test_local_secret_env_is_rejected(self):
        self.assertTrue(check_path(".env"))

    def test_env_variants_are_rejected(self):
        self.assertTrue(check_path(".env.local"))

    def test_env_template_is_allowed(self):
        self.assertEqual(check_path(".env.example"), [])

    def test_vendor_original_is_rejected(self):
        self.assertTrue(check_path("data/raw/abb/acs580-01-hardware-d-zh.pdf"))

    def test_processed_and_index_outputs_are_rejected(self):
        self.assertTrue(check_path("data/processed/manual.json"))
        self.assertTrue(check_path("data/indexes/segment-1.json"))

    def test_generated_artifacts_are_rejected(self):
        self.assertTrue(check_path("artifacts/evaluations/2026-10-13/metrics.json"))

    def test_key_material_and_archives_are_rejected(self):
        self.assertTrue(check_path("deploy/service.pem"))
        self.assertTrue(check_path("backup/dump.sqlite"))

    def test_ordinary_documentation_is_allowed(self):
        self.assertEqual(check_path("docs/data-spec.md"), [])
        self.assertEqual(check_path("data/corpus/knowledge.jsonl"), [])
        self.assertEqual(check_path("scripts/validate_data.py"), [])


class SecretContentTests(unittest.TestCase):
    def test_cloud_credentials_are_rejected(self):
        self.assertTrue(check_text("notes.md", "key = AKIAIOSFODNN7EXAMPLE"))
        self.assertTrue(check_text("notes.md", "ghp_" + "a" * 36))
        self.assertTrue(check_text("notes.md", "-----BEGIN RSA PRIVATE KEY-----"))

    def test_non_placeholder_assignment_is_rejected(self):
        self.assertTrue(check_text("config.py", 'DB_PASSWORD = "hunter2supersecret"'))

    def test_placeholder_assignment_is_allowed(self):
        for value in ("", "${DB_PASSWORD}", "<your-password>", "changeme", "placeholder-value"):
            with self.subTest(value=value):
                self.assertFalse(check_text("config.py", f"DB_PASSWORD={value}"))

    def test_empty_env_values_are_allowed(self):
        self.assertFalse(check_text(".env.example", "POSTGRES_PASSWORD=\nNEO4J_PASSWORD=\n"))

    def test_ci_keyword_is_not_a_secret(self):
        # actions/checkout uses this field; "credentials: false" is not a secret.
        self.assertFalse(check_text(".github/workflows/validate.yml", "persist-credentials: false"))

    def test_integrity_hashes_are_not_secrets(self):
        digest = "a" * 64
        self.assertFalse(check_text("data/sources/manifest.json", f'"sha256": "{digest}"'))

    def test_placeholder_helper_matches_documented_markers(self):
        self.assertTrue(is_placeholder("${POSTGRES_PASSWORD}"))
        self.assertFalse(is_placeholder("s3cret-value-abcdefgh"))


class FindingTests(unittest.TestCase):
    def test_clean_tree_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "note.md").write_text("普通文档，无凭据。", encoding="utf-8")
            self.assertEqual(find_issues(root=root, files=["docs/note.md"], ignore_rules=False), [])

    def test_oversized_tracked_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "blob.bin"
            payload.write_bytes(b"\x00" * (MAX_TRACKED_BYTES + 1))
            issues = find_issues(root=root, files=["blob.bin"], ignore_rules=False)
            self.assertTrue(any("exceeds" in issue for issue in issues))

    def test_binary_payload_is_not_scanned_as_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = root / "logo.bin"
            payload.write_bytes(b"\x00AKIAIOSFODNN7EXAMPLE")
            self.assertEqual(find_issues(root=root, files=["logo.bin"], ignore_rules=False), [])

    def test_ignore_rules_cover_local_data_in_this_repository(self):
        self.assertEqual(check_ignore_rules(), [])


if __name__ == "__main__":
    unittest.main()
