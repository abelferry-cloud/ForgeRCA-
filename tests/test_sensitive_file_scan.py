"""Regression checks for the M0-08 sensitive-file gate.

The fixtures below are assembled from fragments at runtime instead of being
written as literals. That keeps this file clean under the scanner it tests, so
`find_issues()` over the whole repository stays empty. A gate that cannot pass
on the repository containing its own tests is not a gate.
"""

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


FAKE_AWS_KEY = "AKIA" + "IOSFODNN7" + "EXAMPLE"
FAKE_GITHUB_TOKEN = "ghp_" + "a" * 36
FAKE_PRIVATE_KEY_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"
FAKE_PASSWORD = "hunter2" + "supersecret"
FAKE_SETTING = "DB_" + "PASSWORD"


def fake_assignment(indent=""):
    return f'{indent}{FAKE_SETTING} = "{FAKE_PASSWORD}"\n'


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
        self.assertTrue(check_text("notes.md", f"key = {FAKE_AWS_KEY}"))
        self.assertTrue(check_text("notes.md", FAKE_GITHUB_TOKEN))
        self.assertTrue(check_text("notes.md", FAKE_PRIVATE_KEY_HEADER))

    def test_non_placeholder_assignment_is_rejected(self):
        self.assertTrue(check_text("config.py", fake_assignment()))

    def test_placeholder_assignment_is_allowed(self):
        for value in ("", "${DB_PASSWORD}", "<your-password>", "changeme", "placeholder-value"):
            with self.subTest(value=value):
                self.assertFalse(check_text("config.py", f"DB_PASSWORD={value}"))

    def test_empty_env_values_are_allowed(self):
        template = "POSTGRES_PASSWORD=" + "\n" + "NEO4J_PASSWORD=" + "\n"
        self.assertFalse(check_text(".env.example", template))

    def test_escaped_newline_does_not_extend_a_value(self):
        # "PASSWORD=\nNEXT=..." must not read the escape sequence as a value.
        text = "DB_PASSWORD=" + "\\" + "nNEO4J_PASSWORD=" + "\\" + "n"
        self.assertFalse(check_text("config.py", text))

    def test_empty_assignment_does_not_borrow_the_next_line(self):
        # Regression: an .env-style template of empty values must stay clean.
        # A separator regex that accepts newlines reads the following line as
        # the value of the previous, empty assignment.
        settings = ("POSTGRES_" + "PASSWORD", "OPENSEARCH_" + "PASSWORD", "NEO4J_" + "PASSWORD", "LLM_API_" + "KEY")
        template = "\n".join(f"{name}=" for name in settings) + "\nSOME_LONG_VALUE_HERE=abcdefghijklmnopqrstuvwxyz\n"
        self.assertEqual(check_text(".env.example", template), [])

    def test_ci_keyword_is_not_a_secret(self):
        # actions/checkout uses this field; "credentials: false" is not a secret.
        self.assertFalse(check_text(".github/workflows/validate.yml", "persist-credentials: false"))

    def test_integrity_hashes_are_not_secrets(self):
        digest = "a" * 64
        self.assertFalse(check_text("data/sources/manifest.json", f'"sha256": "{digest}"'))

    def test_placeholder_helper_matches_documented_markers(self):
        self.assertTrue(is_placeholder("${POSTGRES_PASSWORD}"))
        self.assertTrue(is_placeholder("changeme"))
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
            payload.write_bytes(b"\x00" + FAKE_AWS_KEY.encode("utf-8"))
            self.assertEqual(find_issues(root=root, files=["logo.bin"], ignore_rules=False), [])

    def test_secret_literal_in_a_tracked_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leak = root / "settings.py"
            leak.write_text(fake_assignment(), encoding="utf-8")
            issues = find_issues(root=root, files=["settings.py"], ignore_rules=False)
            self.assertTrue(any("DB_PASSWORD" in issue for issue in issues))

    def test_ignore_rules_cover_local_data_in_this_repository(self):
        self.assertEqual(check_ignore_rules(), [])

    def test_repository_tracked_files_are_clean(self):
        # The gate must pass on the repository that ships it, tests included.
        self.assertEqual(find_issues(), [])


if __name__ == "__main__":
    unittest.main()
