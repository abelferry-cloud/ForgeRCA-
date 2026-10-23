"""Exercise recipe execution and failure handling in the platform's real shell."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DevCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.just = shutil.which("just")
        if not cls.just:
            raise unittest.SkipTest("just is a dev dependency; run with uv run --frozen python")

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="forgerca commands ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copyfile(ROOT / "justfile", self.root / "justfile")
        (self.root / "nested").mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "validate_data.py").write_text(
            "from pathlib import Path\nPath('validated').touch()\n", encoding="utf-8"
        )
        (self.root / "scripts" / "check_sensitive_files.py").write_text(
            "from pathlib import Path\nPath('scanned').touch()\n", encoding="utf-8"
        )

    def run_just(self, *args):
        return subprocess.run(
            [self.just, *args],
            cwd=self.root / "nested",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def test_default_lists_commands_without_running_them(self):
        result = self.run_just()
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("lint", "test", "data-check", "up", "down", "ingest"):
            self.assertIn(command, result.stdout)
        self.assertFalse((self.root / "validated").exists())
        self.assertFalse((self.root / "scanned").exists())

    def test_data_check_runs_both_checks_from_the_project_root(self):
        result = self.run_just("data-check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "validated").exists())
        self.assertTrue((self.root / "scanned").exists())

    def test_failed_data_validation_stops_before_the_next_check(self):
        (self.root / "scripts" / "validate_data.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
        result = self.run_just("data-check")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "scanned").exists())

    def test_ingest_fails_explicitly_until_the_importer_exists(self):
        result = self.run_just("ingest")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ingest is not implemented", result.stderr)
        self.assertIn("M1-07 to M1-18", result.stderr)


if __name__ == "__main__":
    unittest.main()
