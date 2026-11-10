"""Dense build/query contracts plus opt-in real OpenSearch with synthetic vectors."""

import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app.config import Settings
from app.retrieval import dense
from app.retrieval.corpus import project_manual
from app.retrieval.index_schema import index_record_id, load_mapping
from scripts import dense as cli
from test_retrieval_corpus import manual_row

INDEX = "forgerca-dense-v3-" + "a" * 32
AT = "2026-01-01T00:00:00+08:00"


def vector(x=1.0, y=0.0):
    return [x, y] + [0.0] * 1022


def document(text="first", **changes):
    return {**project_manual(manual_row()), "text": text, **changes}


class FixtureEmbedder:
    """Deterministic geometry only; never claimed to be semantic model output."""

    configuration = deepcopy(dense.SPEC)

    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(texts)
        return {"vectors": [vector(0.0, 1.0) if text == "second" else vector() for text in texts], "batches": []}


def hit(record, score=1.0, index=INDEX):
    return {"_index": index, "_id": index_record_id(record), "_score": score,
            "_source": {**record, "embedding": vector()}}


def search_response(hits):
    return {"timed_out": False, "_shards": {"failed": 0}, "hits": {"hits": hits}}


class DenseContractsTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(prefix="forgerca-dense-v3-")
        self.encoder = FixtureEmbedder()

    def search(self, **changes):
        return dense.retrieve(self.client, INDEX, "query", model="TEST-MODEL", as_of=AT,
                              embedder=self.encoder, **changes)

    def test_build_checks_all_inputs_and_embedding_before_creating_any_index(self):
        for records in ([], [document(), document()], [document(gold_evidence_ids=["forbidden"])]):
            with self.subTest(count=len(records)), self.assertRaises(ValueError):
                dense.build_index(self.client, records, self.encoder)
        self.assertEqual(self.encoder.calls, [])
        self.client.request.assert_not_called()
        self.encoder.encode = Mock(side_effect=ValueError("model failed"))
        with self.assertRaisesRegex(ValueError, "model failed"):
            dense.build_index(self.client, [document()], self.encoder)
        self.client.request.assert_not_called()

    def test_build_publishes_only_complete_index_with_stable_ids(self):
        self.client.request.side_effect = [{"acknowledged": True},
                                           {"errors": False, "items": [{"create": {"status": 201}}]}, {"count": 1}]
        with patch.object(dense, "_read_index", return_value={
            index_record_id(document()): {**document(), "embedding": vector()},
        }):
            result = dense.build_index(self.client, [document()], self.encoder)
        self.assertRegex(result["index"], r"^forgerca-dense-v3-[a-f0-9]{32}$")
        self.assertEqual(result["records"], 1)
        self.assertEqual(self.encoder.calls, [["first"]])
        bulk = self.client.request.call_args_list[1]
        self.assertTrue(bulk.args[1].endswith("/_bulk?refresh=true"))
        lines = bulk.args[2].decode().splitlines()
        self.assertEqual(json.loads(lines[0]), {"create": {"_id": index_record_id(document())}})
        self.assertEqual(json.loads(lines[1])["embedding"], vector())
        result["embedding_configuration"]["model_id"] = "changed"
        self.assertEqual(dense.SPEC["model_id"], "text-embedding-v4")

    def test_failed_create_never_deletes_an_index(self):
        for value in (search_failure(), {"acknowledged": False}):
            self.client.reset_mock()
            self.client.request.side_effect = [value]
            with self.assertRaises(dense.SearchError):
                dense.build_index(self.client, [document()], self.encoder)
            self.assertEqual([call.args[0] for call in self.client.request.call_args_list], ["PUT"])

    def test_partial_bulk_bad_count_and_transport_failure_remove_only_new_index(self):
        failures = [{"errors": True, "items": [{"create": {"status": 400}}]},
                    {"errors": False, "items": []}, search_failure()]
        for failure in failures:
            self.client.reset_mock()
            self.client.request.side_effect = [{"acknowledged": True}, failure, {"acknowledged": True}]
            with self.subTest(failure=type(failure).__name__), self.assertRaisesRegex(dense.SearchError, "removed"):
                dense.build_index(self.client, [document()], self.encoder)
            created = self.client.request.call_args_list[0].args[1]
            self.assertEqual(self.client.request.call_args_list[-1].args, ("DELETE", created))
        self.client.request.side_effect = [{"acknowledged": True},
                                           {"errors": False, "items": [{"create": {"status": 201}}]},
                                           {"count": 0}, {"acknowledged": True}]
        with self.assertRaisesRegex(dense.SearchError, "removed"):
            dense.build_index(self.client, [document()], self.encoder)

    def test_cleanup_failure_is_not_reported_as_success(self):
        for cleanup in (search_failure(), {"acknowledged": False}):
            self.client.request.side_effect = [{"acknowledged": True}, search_failure(), cleanup]
            with self.subTest(cleanup=type(cleanup).__name__), \
                    self.assertRaisesRegex(dense.SearchError, "cleanup failed"):
                dense.build_index(self.client, [document()], self.encoder)

    def test_query_embeds_once_filters_inside_knn_and_keeps_cross_revision_identity(self):
        first = document()
        second = {**first, "document_key": "SYNTHETIC@B:" + "c" * 64, "document_revision": "B"}
        self.client.request.return_value = search_response([hit(first, 0.8), hit(second, 0.9), hit(first, 0.7)])
        result = self.search(top_k=3)
        self.assertEqual(self.encoder.calls, [["query"]])
        self.assertEqual([item["document_revision"] for item in result["hits"]], ["B", "A"])
        self.assertEqual([item["rank"] for item in result["hits"]], [1, 2])
        self.assertNotIn("embedding", result["hits"][0])
        body = self.client.request.call_args.args[2]
        self.assertEqual(body["size"], 3)
        self.assertEqual(body["query"]["knn"]["embedding"]["k"], 3)
        self.assertEqual(body["query"]["knn"]["embedding"]["filter"], result["filters"])

    def test_invalid_parameters_and_model_mapping_fail_before_embedding(self):
        for limit in (0, 101, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.search(top_k=limit)
        for params in (("", AT, None), ("TEST", "2026-01-01", None), ("TEST", AT, "unknown")):
            with self.subTest(params=params), self.assertRaises(ValueError):
                dense.query_filter(*params)
        self.client.verify_mapping.side_effect = search_failure()
        with self.assertRaises(dense.SearchError):
            self.search()
        self.assertEqual(self.encoder.calls, [])
        self.client.request.assert_not_called()

    def test_wrong_encoder_configuration_is_rejected(self):
        self.encoder.configuration = {**dense.SPEC, "model_id": "other"}
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            self.search()
        self.assertEqual(self.encoder.calls, [])

    def test_partial_search_or_inapplicable_hits_are_errors_not_empty_success(self):
        invalid = [search_response([hit(document(model=["OTHER"]))]),
                   search_response([hit(document(available_at="2099-01-01T00:00:00Z"))]),
                   search_response([hit(document(firmware_scope="ASCKX 2.16", firmware_state="known"))]),
                   search_response([hit(document(), score=float("nan"))]),
                   search_response([hit(document(), index="other-index")]),
                   {**search_response([]), "timed_out": True},
                   {**search_response([]), "_shards": {"failed": 1}}, {}, None]
        for payload in invalid:
            self.client.request.return_value = payload
            with self.subTest(case=invalid.index(payload)), self.assertRaises(dense.SearchError):
                self.search()
        self.client.request.return_value = search_response([])
        self.assertEqual(self.search()["hits"], [])


def search_failure():
    return dense.SearchError("synthetic service failure")


class SearchTransportTests(unittest.TestCase):
    def test_scope_refuses_remote_hosts_credentials_and_wildcards(self):
        for settings in (Settings(opensearch_host="remote.example"), Settings(opensearch_user="user"),
                         Settings(opensearch_index_prefix="../bad")):
            with self.assertRaises(ValueError):
                dense.SearchClient(settings)
        client = dense.SearchClient(Settings())
        for name in ("*", "forgerca-dense-v2-" + "a" * 32, INDEX + "/_all"):
            with self.assertRaises(ValueError):
                client.check_index_name(name)

    def test_request_preserves_ndjson_and_hides_error_bodies(self):
        with patch.object(dense, "build_opener") as opener:
            client = dense.SearchClient(Settings())
        transport = opener.return_value
        transport.open.return_value = io.BytesIO(b'{"errors":false}')
        payload = b'{"create":{}}\n{}\n'
        self.assertEqual(client.request("POST", "/fixture/_bulk", payload), {"errors": False})
        request = transport.open.call_args.args[0]
        self.assertEqual(request.data, payload)
        self.assertEqual(request.get_header("Content-type"), "application/x-ndjson")
        for error in (HTTPError("http://local", 500, "private message", {}, io.BytesIO(b"private body")),
                      URLError("private network detail")):
            transport.open.side_effect = error
            with self.assertRaises(dense.SearchError) as caught:
                client.request("GET", "/fixture")
            self.assertNotIn("private", str(caught.exception))
        self.assertIsNone(dense._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test"))

    def test_mapping_must_match_pinned_model_and_schema(self):
        client = dense.SearchClient(Settings())
        for payload in (None, {}, {INDEX: None}, {INDEX: {"mappings": {"_meta": {"embedding_model": "old"}}}}):
            with patch.object(client, "request", return_value=payload), self.assertRaises(dense.SearchError):
                client.verify_mapping(INDEX)
        with patch.object(client, "request", return_value={INDEX: {"mappings": load_mapping()["mappings"]}}):
            client.verify_mapping(INDEX)


class DenseCommandTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.enterContext(patch.object(cli, "ROOT", self.root))
        self.enterContext(patch("sys.stderr", new_callable=io.StringIO))

    def args(self, path):
        return ["query", "--index", INDEX, "--query", "synthetic", "--model", "TEST", "--as-of", AT,
                "--output", str(path)]

    def test_output_path_validation_precedes_any_client_or_model(self):
        path = self.root / "data/evaluation/result.json"
        with patch.object(cli, "SearchClient") as client, self.assertRaises(SystemExit):
            cli.main(self.args(path))
        client.assert_not_called()

    def test_query_output_and_failure_do_not_publish_raw_errors_or_partial_results(self):
        path = self.root / "artifacts/result.json"
        with patch.object(cli, "SearchClient"), \
                patch.object(cli, "retrieve", return_value={"index": INDEX, "hits": []}), \
                patch("sys.stdout", new_callable=io.StringIO):
            cli.main(self.args(path))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["hits"], [])
        second = self.root / "artifacts/failure.json"
        with patch.object(cli, "SearchClient"), patch.object(cli, "retrieve", side_effect=ValueError("private")), \
                self.assertRaises(SystemExit):
            cli.main(self.args(second))
        self.assertFalse(second.exists())


@unittest.skipUnless(os.environ.get("FORGERCA_TEST_OPENSEARCH") == "1",
                     "Enable explicitly for disposable real OpenSearch integration")
class DenseOpenSearchTests(unittest.TestCase):
    def test_file_hits_resolve_and_generate_after_real_search(self):
        from app import generation
        from app.retrieval.citations import resolve_hits
        from app.retrieval.corpus import load_file_records

        client, encoder = dense.SearchClient(Settings()), FixtureEmbedder()
        docs = load_file_records()
        report = dense.build_index(client, docs, encoder)
        index = report["index"]
        self.addCleanup(client.request, "DELETE", f"/{index}")
        result = dense.retrieve(client, index, "synthetic query", model=docs[0]["model"][0],
                                as_of="2026-11-09T00:00:00+08:00", firmware_version=docs[0]["firmware_scope"],
                                top_k=100, embedder=encoder)
        resolved = resolve_hits(result["hits"])
        first = next(row for row in resolved if row["evidence_id"] == "K001")
        self.assertEqual(first["record_kind"], "knowledge_note")
        self.assertEqual(first["locator"]["pdf_page"], 536)
        self.assertEqual(first["source"]["revision"], first["document_revision"])
        self.assertTrue(first["locator"]["url"].endswith("#page=536"))
        generator = Mock(configuration=deepcopy(generation.SPEC))
        generator.complete.return_value = ({"status": "supported", "candidate_causes": [
            {"cause": "合成测试候选", "explanation": "这里只验证引用绑定，不测试语义生成。",
             "support": [{"index_id": first["index_id"], "quote": first["text"]}]}], "missing_evidence": []}, None)
        answer = generation.answer_question("synthetic query", result["hits"], generator=generator)["answer"]
        generator.complete.assert_called_once()
        self.assertEqual(answer["citations"][0]["locator"], first["locator"])
        self.assertEqual(answer["citations"][0]["index_id"], first["index_id"])

    def test_build_search_ranking_filters_revision_identity_and_empty_result(self):
        client, encoder = dense.SearchClient(Settings()), FixtureEmbedder()
        docs = [document(), document("second", document_key="SYNTHETIC@B:" + "c" * 64, document_revision="B"),
                document("other", evidence_id="ev1:" + "c" * 64, model=["OTHER"]),
                document("future", evidence_id="ev1:" + "d" * 64, available_at="2099-01-01T00:00:00Z"),
                document("firmware", evidence_id="ev1:" + "e" * 64,
                         firmware_scope="ASCKX 2.16", firmware_state="known"),
                document("unknown", evidence_id="WO-unknown", record_kind="work_order", chunk_type=None,
                         document_key=None, source_id=None, document_revision=None,
                         synthetic=True, firmware_state="unknown")]
        report = dense.build_index(client, docs, encoder)
        index = report["index"]
        self.addCleanup(client.request, "DELETE", f"/{index}")
        self.assertEqual(client.request("GET", f"/{index}/_count")["count"], len(docs))

        def query(**changes):
            return dense.retrieve(client, index, "query", model="TEST-MODEL", as_of=AT, embedder=encoder, **changes)

        result = query()
        self.assertEqual([record["text"] for record in result["hits"]], ["first", "second"])
        self.assertGreater(result["hits"][0]["score"], result["hits"][1]["score"])
        self.assertEqual(len({item["evidence_id"] for item in result["hits"]}), 1)
        self.assertEqual(len({item["document_key"] for item in result["hits"]}), 2)
        self.assertEqual(len(query(top_k=1)["hits"]), 1)
        self.assertEqual({record["text"] for record in query(firmware_version="ASCKX 2.16")["hits"]},
                         {"first", "second", "firmware"})
        self.assertEqual(len(query(firmware_version="ASCKX 3.00")["hits"]), 2)
        none = dense.retrieve(client, index, "query", model="test-model", as_of=AT, embedder=encoder)
        self.assertEqual(none["hits"], [])
        self.assertEqual(client.request("GET", f"/{index}/_count")["count"], len(docs))
