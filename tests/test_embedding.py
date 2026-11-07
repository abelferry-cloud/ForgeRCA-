"""API contracts use fabricated responses, with no external requests or model assets."""

import hashlib
import io
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.config import ConfigError, Settings
from app.retrieval import embedding
from scripts import embed_text


def response(count=1):
    return {"model": "text-embedding-v4", "data": [
        {"index": index, "embedding": [3.0, 4.0] + [0.0] * 1022} for index in range(count)
    ], "usage": {"total_tokens": count * 7}}


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.private = "fixture-" + "credential-do-not-print"
        self.settings = Settings.from_env({"DASHSCOPE_API_KEY": self.private})
        self.transport = Mock()
        self.enterContext(patch.object(embedding, "build_opener", return_value=self.transport))
        self.encoder = embedding.DenseEmbedder(self.settings)

    def reply(self, payload):
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    def test_batches_keep_input_text_and_response_indices_restore_order(self):
        first, second = response(10), response()
        first["data"][0]["embedding"] = [0.0, 5.0] + [0.0] * 1022
        first["data"].reverse()
        self.transport.open.side_effect = [self.reply(first), self.reply(second)]
        texts = [f" 合成测试 {index} " for index in range(11)]
        result = self.encoder.encode(texts)
        self.assertEqual(len(result["vectors"]), 11)
        self.assertEqual(result["vectors"][0][:2], [0.0, 1.0])
        self.assertEqual(result["vectors"][1][:2], [0.6, 0.8])
        self.assertEqual(result["batches"], [{"input_count": 10, "total_tokens": 70},
                                             {"input_count": 1, "total_tokens": 7}])
        for vector in result["vectors"]:
            self.assertEqual(len(vector), 1024)
            self.assertAlmostEqual(math.hypot(*vector), 1.0)
        for index, call in enumerate(self.transport.open.call_args_list):
            request = call.args[0]
            self.assertEqual(request.full_url, "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.private)
            self.assertEqual(call.kwargs, {"timeout": 30})
            self.assertEqual(json.loads(request.data), {
                "model": "text-embedding-v4", "dimensions": 1024, "encoding_format": "float",
                "input": texts[index * 10:(index + 1) * 10],
            })

    def test_missing_credentials_and_model_drift_fail_before_network(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(ConfigError, "DASHSCOPE_API_KEY"):
            embedding.DenseEmbedder()
        with self.assertRaisesRegex(ConfigError, "DASHSCOPE_API_KEY"):
            embedding.DenseEmbedder(Settings())
        other = Settings.from_env({"DASHSCOPE_API_KEY": self.private, "EMBEDDING_MODEL": "other"})
        with self.assertRaisesRegex(ConfigError, "EMBEDDING_MODEL"):
            embedding.DenseEmbedder(other)
        self.transport.open.assert_not_called()

    def test_empty_and_invalid_input_do_not_request_or_truncate(self):
        self.assertEqual(self.encoder.encode([]), {"vectors": [], "batches": []})
        for value in ("text", None, [" "], [1], ["valid", ""]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.encoder.encode(value)
        self.transport.open.assert_not_called()

    def test_utf8_byte_limit_accepts_boundary_and_rejects_all_before_first_batch(self):
        self.transport.open.return_value = self.reply(response())
        self.encoder.encode(["a" * 4096])
        self.transport.open.reset_mock()
        for texts in (["valid"] * 10 + ["a" * 4097], ["中" * 1366]):
            with self.subTest(count=len(texts)), self.assertRaisesRegex(ValueError, "UTF-8 byte limit"):
                self.encoder.encode(texts)
        self.transport.open.assert_not_called()

    def test_bad_indices_dimensions_values_and_model_are_rejected(self):
        fixtures = [None, [], {}, {**response(), "model": "other"}, {**response(), "data": []}]
        for value in (-1, 1, True, "0", None):
            item = response()
            item["data"][0]["index"] = value
            fixtures.append(item)
        for vector in ([0.0] * 1024, [1.0] * 3, "base64", [1.0] * 1023 + [None],
                       [1.0] * 1023 + [True], [1.0] * 1023 + [float("nan")],
                       [1.0] * 1023 + [float("inf")], [1.0] * 1023 + [1e40]):
            item = response()
            item["data"][0]["embedding"] = vector
            fixtures.append(item)
        fixtures.append({**response(), "data": [None]})
        for value in (True, -1, "7"):
            fixtures.append({**response(), "usage": {"total_tokens": value}})
        fixtures.append({**response(), "usage": []})
        for index, payload in enumerate(fixtures):
            self.transport.open.return_value = self.reply(payload)
            with self.subTest(case=index), self.assertRaises(embedding.EmbeddingError):
                self.encoder.encode(["synthetic"])
        duplicate = response(2)
        duplicate["data"][1]["index"] = 0
        self.transport.open.return_value = self.reply(duplicate)
        with self.assertRaises(embedding.EmbeddingError):
            self.encoder.encode(["first", "second"])

    def test_missing_usage_is_unknown_instead_of_zero(self):
        payload = response()
        payload.pop("usage")
        self.transport.open.return_value = self.reply(payload)
        self.assertIsNone(self.encoder.encode(["synthetic"])["batches"][0]["total_tokens"])

    def test_http_network_and_json_failures_do_not_leak_or_retry(self):
        for status in (400, 401, 403, 429, 500, 302):
            with self.subTest(status=status):
                self.transport.open.reset_mock()
                self.transport.open.side_effect = HTTPError(
                    "https://example.invalid", status, self.private, {}, io.BytesIO(self.private.encode()))
                with self.assertRaisesRegex(embedding.EmbeddingError, f"HTTP {status}") as caught:
                    self.encoder.encode(["synthetic"])
                self.assertNotIn(self.private, str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(self.transport.open.call_count, 1)
        for error in (URLError(self.private), TimeoutError(self.private), ValueError(self.private)):
            self.transport.open.side_effect = error
            with self.assertRaises(embedding.EmbeddingError) as caught:
                self.encoder.encode(["synthetic"])
            self.assertNotIn(self.private, str(caught.exception))
        self.transport.open.side_effect = None
        self.transport.open.return_value = io.BytesIO(b"not json")
        with self.assertRaises(embedding.EmbeddingError):
            self.encoder.encode(["synthetic"])

    def test_redirects_are_not_followed_and_configuration_contains_no_credentials(self):
        self.assertIsNone(embedding._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))
        config = self.encoder.configuration
        original = deepcopy(config)
        config["inference"]["batch_size"] = 999
        self.assertEqual(self.encoder.configuration, original)
        self.assertNotIn(self.private, str(self.encoder.configuration))
        self.assertNotIn(self.private, repr(self.settings))


class EmbeddingCommandTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.enterContext(patch.object(embed_text, "ROOT", self.root))
        self.enterContext(patch("sys.stderr", new_callable=io.StringIO))

    def test_invalid_output_blank_input_and_overwrite_fail_before_api(self):
        existing = self.root / "artifacts/existing.json"
        existing.parent.mkdir()
        existing.write_text("unchanged", encoding="utf-8")
        for args in (["--text", "hello", "--output", str(self.root / "data/evaluation/test.json")],
                     ["--text", " ", "--output", str(self.root / "artifacts/valid.json")],
                     ["--text", "hello", "--output", str(existing)]):
            with self.subTest(args=args), patch.object(embed_text, "DenseEmbedder") as create:
                with self.assertRaises(SystemExit):
                    embed_text.main(args)
                create.assert_not_called()
        self.assertEqual(existing.read_text(encoding="utf-8"), "unchanged")

    def test_output_records_configuration_usage_and_hashes_without_copying_input(self):
        path = self.root / "artifacts/result.json"
        model = Mock()
        model.configuration = {"dimension": 2, "model_id": "synthetic/tiny"}
        model.encode.return_value = {"vectors": [[1.0, 0.0]], "batches": [{"input_count": 1, "total_tokens": 4}]}
        with patch.object(embed_text, "DenseEmbedder", return_value=model), \
                patch("sys.stdout", new_callable=io.StringIO):
            embed_text.main(["--text", "synthetic input", "--output", str(path)])
        result = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(result["text_sha256"], [hashlib.sha256(b"synthetic input").hexdigest()])
        self.assertRegex(result["configuration_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["batches"][0]["total_tokens"], 4)
        self.assertNotIn("synthetic input", path.read_text(encoding="utf-8"))

    def test_second_batch_failure_does_not_publish_partial_output(self):
        path = self.root / "artifacts/result.json"
        transport = Mock()
        transport.open.side_effect = [io.BytesIO(json.dumps(response(10)).encode()), TimeoutError("private detail")]
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": "synthetic"}), \
                patch.object(embedding, "build_opener", return_value=transport), \
                self.assertRaises(embedding.EmbeddingError):
            embed_text.main([value for _ in range(11) for value in ("--text", "synthetic")]
                            + ["--output", str(path)])
        self.assertEqual(transport.open.call_count, 2)
        self.assertFalse(path.exists())
