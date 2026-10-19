"""Offline tests for the optional public dataset downloader."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_public_data.py"
spec = importlib.util.spec_from_file_location("download_public_data", SCRIPT)
downloader = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(downloader)


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, url: str):
        super().__init__(data)
        self.url = url

    def geturl(self) -> str:
        return self.url


class DownloadPublicDataTests(unittest.TestCase):
    def test_urls_must_be_https_and_allowlisted(self):
        for url in ["http://archive.ics.uci.edu/x", "https://evil.example/file", "file:///etc/passwd"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                downloader.ensure_allowlisted_url(url)
        downloader.ensure_allowlisted_url("https://raw.githubusercontent.com/nlp-tlp/maintie/main/data/gold_release.json")

    def test_catalog_load_and_list_without_network(self):
        items = downloader.load_catalog()
        self.assertIn("maintie-gold", items)
        self.assertIn("ai4i", items)
        with patch.object(downloader, "urlopen", side_effect=AssertionError("should not access network")):
            self.assertEqual(downloader.main(["--list"]), 0)

    def test_reject_large_download_without_confirmation(self):
        entry = downloader.load_catalog()["metropt3"]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "allow-large"):
                downloader.download_dataset("metropt3", entry, Path(temp))

    def test_maintie_download_writes_provenance_and_skips_existing(self):
        entry = downloader.load_catalog()["maintie-gold"]
        payload = json.dumps([{"text": "pump hot", "tokens": ["pump", "hot"],
                               "entities": [], "relations": []}]).encode("utf-8")
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(downloader, "urlopen", return_value=FakeResponse(payload, entry["download_url"])) as request:
                location = downloader.download_dataset("maintie-gold", entry, Path(temp))
                self.assertTrue(location.exists())
                manifest = json.loads((location.parent / "PROVENANCE.json").read_text())
                self.assertEqual(manifest["records"], 1)
                self.assertEqual(len(manifest["file_sha256"]), 64)
                self.assertTrue(manifest["not_abb_work_order_data"])
                downloader.download_dataset("maintie-gold", entry, Path(temp))
                self.assertEqual(request.call_count, 1)
                location.write_text("tampered data", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    downloader.download_dataset("maintie-gold", entry, Path(temp))

    def test_ai4i_extraction_and_column_validation(self):
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("nested/ai4i2020.csv", "UDI,Product ID,Machine failure\n1,A,0\n")
        entry = downloader.load_catalog()["ai4i"]
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(downloader, "urlopen", return_value=FakeResponse(data.getvalue(), entry["download_url"])):
                location = downloader.download_dataset("ai4i", entry, Path(temp))
                self.assertIn("Machine failure", location.read_text())
                self.assertFalse((location.parent / "download.bin").exists())

    def test_corrupt_response_leaves_no_partial_final_file(self):
        entry = downloader.load_catalog()["maintie-gold"]
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(downloader, "urlopen", return_value=FakeResponse(b"this is not json" * 10, entry["download_url"])):
                with self.assertRaises(json.JSONDecodeError):
                    downloader.download_dataset("maintie-gold", entry, Path(temp))
            self.assertFalse((Path(temp) / "maintie-gold" / "gold_release.json").exists())


    def test_catalog_records_verified_snapshots(self):
        """M0-20: the committed snapshot is the only public record of a verified download."""
        items = downloader.load_catalog()
        for key in ("maintie-gold", "ai4i"):
            with self.subTest(key=key):
                snapshot = items[key].get("verified_snapshot")
                self.assertIsInstance(snapshot, dict)
                self.assertRegex(snapshot["sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(snapshot["checked_on"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(snapshot["downloaded_at_utc"].endswith("+00:00"))
                self.assertGreater(snapshot["bytes"], 0)
                self.assertGreater(snapshot["records"] if "records" in snapshot else snapshot["rows"], 0)
                self.assertEqual(snapshot["file_name"], downloader.OUTPUT_NAMES[key])
                self.assertFalse(items[key]["may_be_merged_into_abb_corpus"])

    def test_unverified_catalog_entries_claim_no_snapshot(self):
        items = downloader.load_catalog()
        for key in ("maintie-silver", "metropt3"):
            self.assertNotIn("verified_snapshot", items[key], key)


if __name__ == "__main__":
    unittest.main()
