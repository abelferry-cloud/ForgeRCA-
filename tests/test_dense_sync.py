"""Incremental index lifecycle contracts; synthetic vectors never call a model API."""

import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import Settings
from app.retrieval import dense
from app.retrieval.index_schema import index_record_id
from scripts import dense as cli
from test_dense import AT, INDEX, FixtureEmbedder, document, hit, search_failure, search_response, vector


def scroll_page(records, index=INDEX, total=None, cursor="cursor"):
    return {**search_response([hit(record, index=index) for record in records]), "_scroll_id": cursor,
            "hits": {"hits": [hit(record, index=index) for record in records],
                     "total": {"value": len(records) if total is None else total, "relation": "eq"}}}


class MemorySearch:
    """A stateful wire fixture, allowing assertions that old index contents survive failures."""

    prefix = "forgerca-dense-v3-"

    def __init__(self, records):
        self.indexes = {INDEX: {index_record_id(record): {**record, "embedding": vector()} for record in records}}
        self.check_index_name = Mock()
        self.verify_mapping = Mock()
        self.request = Mock(side_effect=self.respond)

    def respond(self, method, path, payload=None):
        if path == "/_search/scroll" and method == "DELETE":
            return {"succeeded": True}
        index = path.split("/")[1]
        if method == "PUT":
            if index in self.indexes:
                raise search_failure()
            self.indexes[index] = {}
            return {"acknowledged": True}
        if method == "DELETE":
            del self.indexes[index]
            return {"acknowledged": True}
        if "_bulk" in path:
            lines = payload.decode().splitlines()
            for offset in range(0, len(lines), 2):
                self.indexes[index][json.loads(lines[offset])["create"]["_id"]] = json.loads(lines[offset + 1])
            return {"errors": False, "items": [{"create": {"status": 201}} for _ in range(len(lines) // 2)]}
        if path.endswith("/_count"):
            return {"count": len(self.indexes[index])}
        if "_search?scroll" in path:
            records = self.indexes[index]
            return {**scroll_page([], index=index, total=len(records)), "hits": {
                "total": {"relation": "eq", "value": len(records)},
                "hits": [{"_index": index, "_id": key, "_source": row} for key, row in records.items()],
            }}
        raise AssertionError((method, path))


class IncrementalIndexTests(unittest.TestCase):
    def setUp(self):
        self.original = [document(), document("second", evidence_id="ev1:" + "c" * 64),
                         document("removed", evidence_id="ev1:" + "d" * 64)]
        self.client = MemorySearch(self.original)
        self.client.indexes[INDEX][index_record_id(self.original[0])]["embedding"] = vector(0.6, 0.8)
        self.old = deepcopy(self.client.indexes[INDEX])
        self.encoder = FixtureEmbedder()

    def test_diff_reuses_text_vectors_but_updates_metadata_and_keeps_revisions(self):
        updated = [{**self.original[0], "model": ["NEW-MODEL"]}, {**self.original[1], "text": "changed"},
                   document("new revision", document_key="SYNTHETIC@B:" + "c" * 64, document_revision="B")]
        result = dense.sync_index(self.client, INDEX, updated, self.encoder)
        self.assertEqual(self.encoder.calls, [["changed", "new revision"]])
        self.assertEqual({key: result[key] for key in ("added", "removed", "modified", "embedded_records",
                                                      "reused_vectors", "no_op")},
                         {"added": 1, "removed": 1, "modified": 2, "embedded_records": 2,
                          "reused_vectors": 1, "no_op": False})
        self.assertEqual(self.client.indexes[INDEX], self.old)
        self.assertEqual(len(self.client.indexes[result["index"]]), 3)
        self.assertEqual(self.client.indexes[result["index"]][index_record_id(updated[0])]["embedding"],
                         vector(0.6, 0.8))
        repeated = dense.sync_index(self.client, result["index"], list(reversed(updated)))
        self.assertTrue(repeated["no_op"])
        self.assertEqual(repeated["index"], result["index"])
        self.assertEqual(len(self.client.indexes), 2)

    def test_no_change_metadata_only_deletion_and_empty_need_no_encoder_or_key(self):
        with patch.object(dense, "DenseEmbedder", side_effect=AssertionError("No API needed")):
            same = dense.sync_index(self.client, INDEX, self.original)
            self.assertTrue(same["no_op"])
            records = [{**self.original[0], "model": ["CHANGED"]}]
            changed = dense.sync_index(self.client, INDEX, records)
            self.assertEqual((changed["modified"], changed["removed"], changed["embedded_records"]), (1, 2, 0))
            empty = dense.sync_index(self.client, changed["index"], [])
            self.assertEqual(self.client.indexes[empty["index"]], {})
            self.assertEqual(empty["removed"], 1)
            self.assertTrue(dense.sync_index(self.client, empty["index"], [])["no_op"])
        self.assertEqual(self.client.indexes[INDEX], self.old)

    def test_invalid_inputs_mapping_and_embeddings_never_create_a_new_index(self):
        with self.assertRaises(ValueError):
            dense.sync_index(self.client, INDEX, self.original * 2, self.encoder)
        self.client.request.assert_not_called()
        self.client.verify_mapping.side_effect = search_failure()
        with self.assertRaises(dense.SearchError):
            dense.sync_index(self.client, INDEX, self.original, self.encoder)
        self.client.request.assert_not_called()
        self.client.verify_mapping.side_effect = None
        for encoded in (search_failure(), {"vectors": [], "batches": []},
                        {"vectors": [[float("nan")] * 1024], "batches": []}):
            self.encoder.encode = Mock(side_effect=[encoded])
            with self.subTest(encoded=type(encoded).__name__), self.assertRaises(ValueError):
                dense.sync_index(self.client, INDEX, [document("changed")], self.encoder)
            self.assertEqual(self.client.indexes, {INDEX: self.old})

    def test_partial_write_readback_mismatch_count_mapping_and_cleanup_failures(self):
        for stage in ("bulk", "count", "readback", "mapping", "cleanup", "create_lost_ack"):
            with self.subTest(stage=stage):
                client = MemorySearch(self.original)
                before = deepcopy(client.indexes[INDEX])

                def request(method, path, payload=None, client=client, stage=stage):
                    response = client.respond(method, path, payload)
                    if path.split("/")[1] == INDEX or path == "/_search/scroll":
                        return response
                    if stage == "create_lost_ack" and method == "PUT":
                        raise search_failure()
                    if stage in ("bulk", "cleanup") and "_bulk" in path:
                        raise search_failure()
                    if stage == "cleanup" and method == "DELETE":
                        return {"acknowledged": False}
                    if stage == "count" and path.endswith("/_count"):
                        return {"count": 0}
                    if stage == "readback" and "_search?scroll" in path:
                        response["hits"]["hits"][0]["_source"]["text"] = "corrupted"
                    return response

                client.request.side_effect = request
                if stage == "mapping":
                    client.verify_mapping.side_effect = [None, search_failure()]
                with self.assertRaises(dense.SearchError) as caught:
                    dense.sync_index(client, INDEX, [document("changed")], self.encoder)
                self.assertEqual(client.indexes[INDEX], before)
                if stage == "cleanup":
                    self.assertIn("cleanup failed", str(caught.exception))
                elif stage == "create_lost_ack":
                    self.assertEqual(len(client.indexes), 2)
                    self.assertFalse(any(call.args[0] == "DELETE" and call.args[1] != "/_search/scroll"
                                         for call in client.request.call_args_list))
                    client.request.side_effect = client.respond
                    retry = dense.sync_index(client, INDEX, [document("changed")], self.encoder)
                    self.assertFalse(retry["no_op"])
                    self.assertEqual(len(client.indexes), 3)
                else:
                    self.assertEqual(client.indexes, {INDEX: before})


class ScrollSnapshotTests(unittest.TestCase):
    def test_pagination_uses_latest_cursor_and_clears_only_its_context(self):
        first, second = document(), document(evidence_id="ev1:" + "c" * 64)
        client = Mock()
        client.request.side_effect = [scroll_page([first], total=2), scroll_page([second], total=2, cursor="next"),
                                      {"succeeded": True}]
        self.assertEqual(len(dense._read_index(client, INDEX)), 2)
        self.assertEqual(client.request.call_args_list[1].args,
                         ("POST", "/_search/scroll", {"scroll": "1m", "scroll_id": "cursor"}))
        self.assertEqual(client.request.call_args.args, ("DELETE", "/_search/scroll", {"scroll_id": ["next"]}))

    def test_incomplete_or_corrupt_pages_fail_before_any_index_write(self):
        invalid = [None, {}, search_failure(), scroll_page([], total=1),
                   {**scroll_page([document()]), "timed_out": True},
                   {**scroll_page([document()]), "_shards": {"failed": 1}},
                   scroll_page([document(), document()]), scroll_page([document()], index="wrong-index"),
                   scroll_page([document()], total=0)]
        for field, value in (("_id", "wrong-id"), ("_source", {**document(), "embedding": [0.0] * 1024})):
            page = scroll_page([document()])
            page["hits"]["hits"][0][field] = value
            invalid.append(page)
        for page in invalid:
            for later in (False, True):
                client = Mock()
                responses = [scroll_page([document()], total=2)] if later else []
                client.request.side_effect = responses + [page, {"succeeded": True}]
                with self.subTest(page=invalid.index(page), later=later), self.assertRaises(dense.SearchError):
                    dense.sync_index(client, INDEX, [document()], FixtureEmbedder())
                self.assertFalse(any(call.args[0] == "PUT" for call in client.request.call_args_list))

    def test_scroll_cleanup_failure_is_not_success(self):
        for cleanup in (search_failure(), {"succeeded": False}, None):
            client = Mock()
            client.request.side_effect = [scroll_page([]), cleanup]
            with self.subTest(cleanup=cleanup), self.assertRaises(dense.SearchError):
                dense._read_index(client, INDEX)


class SyncCommandTests(unittest.TestCase):
    def test_sync_reads_only_authoritative_loaders_and_publishes_only_on_success(self):
        # CLI database dependency is optional in the standard-library-only test environment.
        try:
            from app.db.connection import create_db_engine  # noqa: F401
        except ImportError:
            self.skipTest("CLI source loading requires locked database dependencies")
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "ROOT", Path(folder)), \
                patch.object(cli, "SearchClient"), patch.object(cli, "load_file_records", return_value=[]), \
                patch.object(cli, "load_manual_records", return_value=[document()]) as manual, \
                patch("app.db.connection.create_db_engine") as engine, \
                patch.object(cli, "sync_index", return_value={"index": INDEX, "no_op": True}) as sync, \
                patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            path = Path(folder) / "artifacts/sync.json"
            args = ["sync", "--index", INDEX, "--output", str(path)]
            cli.main(args)
            self.assertTrue(json.loads(path.read_text())["no_op"])
            self.assertEqual(sync.call_args.args[1:], (INDEX, [document()]))
            manual.assert_called_once_with(engine.return_value)
            engine.return_value.dispose.assert_called_once()
            sync.side_effect = search_failure()
            failed = path.with_name("failed.json")
            with self.assertRaises(SystemExit):
                cli.main([*args[:-1], str(failed)])
            self.assertFalse(failed.exists())


@unittest.skipUnless(os.environ.get("FORGERCA_TEST_OPENSEARCH") == "1", "Requires disposable OpenSearch")
class OpenSearchSyncTests(unittest.TestCase):
    def test_real_scroll_multiple_pages_reuse_delete_empty_and_failure_preserve_old_query(self):
        client, encoder = dense.SearchClient(Settings()), FixtureEmbedder()
        records = [document(f"fixture {n}", evidence_id="ev1:" + f"{n:064x}") for n in range(257)]
        old = dense.build_index(client, records, encoder)["index"]
        self.addCleanup(client.request, "DELETE", f"/{old}")
        encoder.calls.clear()
        # Same bare anchor across revisions must remain two different records.
        records = [records[0], {**records[0], "document_key": "SYNTHETIC@B:" + "c" * 64,
                               "document_revision": "B", "text": "second"}]
        result = dense.sync_index(client, old, records, encoder)
        new = result["index"]
        self.addCleanup(client.request, "DELETE", f"/{new}")
        self.assertEqual(encoder.calls, [["second"]])
        self.assertEqual((result["added"], result["removed"], result["reused_vectors"]), (1, 256, 1))
        hits = dense.retrieve(client, new, "query", model="TEST-MODEL", as_of=AT, embedder=encoder)["hits"]
        self.assertEqual({row["document_revision"] for row in hits}, {"A", "B"})
        self.assertEqual(len({row["evidence_id"] for row in hits}), 1)
        self.assertTrue(dense.sync_index(client, new, records)["no_op"])
        transport = client.request

        def partial(method, path, payload=None):
            response = transport(method, path, payload)
            if "_bulk" in path:
                raise search_failure()
            return response

        with patch.object(client, "request", side_effect=partial), self.assertRaises(dense.SearchError):
            dense.sync_index(client, new, [document("changed")], encoder)
        self.assertEqual(len(dense.retrieve(client, new, "query", model="TEST-MODEL",
                                            as_of=AT, embedder=encoder)["hits"]), 2)
        empty = dense.sync_index(client, new, [])
        self.addCleanup(client.request, "DELETE", f"/{empty['index']}")
        self.assertTrue(dense.sync_index(client, empty["index"], [])["no_op"])
        self.assertEqual(dense.retrieve(client, empty["index"], "query", model="TEST-MODEL",
                                       as_of=AT, embedder=encoder)["hits"], [])
