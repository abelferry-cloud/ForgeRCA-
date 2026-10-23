"""Guard artifact identity and the model/mapping contract without network access."""

import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import call, patch
from urllib.parse import urlparse

from scripts import verify_version_artifacts

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))


class VersionLockTests(unittest.TestCase):
    def test_artifacts_have_immutable_identifiers(self):
        self.assertEqual(LOCK["schema_version"], 1)
        self.assertEqual(set(LOCK["packages"]), {"docling", "docling-slim", "alembic"})
        for name, package in LOCK["packages"].items():
            with self.subTest(package=name):
                self.assertRegex(package["version"], r"^\d+\.\d+\.\d+$")
                self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
                url = urlparse(package["url"])
                self.assertEqual((url.scheme, url.netloc), ("https", "files.pythonhosted.org"))
                filename = f"{name.replace('-', '_')}-{package['version']}-py3-none-any.whl"
                self.assertEqual(Path(url.path).name, filename)
        model = LOCK["embedding"]
        self.assertRegex(model["revision"], r"^[0-9a-f]{40}$")
        self.assertTrue(model["configuration_files"])
        for digest in model["configuration_files"].values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(set(LOCK["images"]), {"postgres", "opensearch", "neo4j"})
        for ref in LOCK["images"].values():
            self.assertRegex(ref, r"^[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}$")

    def test_mapping_bytes_and_embedding_identity_match_lock(self):
        entry = LOCK["opensearch_mapping"]
        raw = (ROOT / entry["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
        mapping = json.loads(raw)["mappings"]
        self.assertEqual(mapping["_meta"]["mapping_version"], entry["version"])
        self.assertEqual(mapping["_meta"]["embedding_model"], LOCK["embedding"]["model_id"])
        self.assertEqual(mapping["_meta"]["embedding_revision"], LOCK["embedding"]["revision"])
        self.assertEqual(mapping["properties"]["embedding"]["dimension"], LOCK["embedding"]["dimension"])

    def test_artifact_verifier_uses_the_pinned_urls(self):
        payload = b"small test artifact"
        digest = hashlib.sha256(payload).hexdigest()
        revision = "a" * 40
        manifest = {
            "packages": {"example": {"url": "https://example.org/fixed.whl", "sha256": digest}},
            "embedding": {
                "model_id": "example/model", "revision": revision,
                "configuration_files": {"config.json": digest},
            },
        }
        with (
            patch.object(Path, "read_text", return_value=json.dumps(manifest)),
            patch.object(
                verify_version_artifacts, "urlopen", side_effect=lambda *a, **kw: io.BytesIO(payload),
            ) as fetch,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            verify_version_artifacts.main()
        self.assertEqual(fetch.call_args_list, [
            call("https://example.org/fixed.whl", timeout=45),
            call(f"https://huggingface.co/example/model/resolve/{revision}/config.json", timeout=45),
        ])

    def test_artifact_verifier_stops_at_a_hash_mismatch(self):
        with patch.object(verify_version_artifacts, "urlopen", return_value=io.BytesIO(b"corrupt")) as fetch:
            with self.assertRaisesRegex(SystemExit, "SHA-256 mismatch: docling"):
                verify_version_artifacts.main()
        fetch.assert_called_once()
