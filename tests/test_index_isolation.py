"""Audit actual indexing and generation payloads against forbidden-source canaries."""

import io
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from app import generation
from app.config import Settings
from app.retrieval import corpus, dense
from app.retrieval.index_schema import index_record_id, load_mapping
from scripts import dense as cli
from scripts.corpus_allowlist import INDEXABLE_CORPUS_FILES
from test_citations import hit
from test_dense import FixtureEmbedder, document
from test_dense_sync import MemorySearch
from test_generation import api_response

FORBIDDEN_FIELDS = {"gold_evidence_ids", "acceptable_cause_ids", "expected_status", "rationale",
                    "review_status", "nodes", "edges"}
CONTEXT_FIELDS = {"index_id", "text", "record_kind", "synthetic", "model", "document_revision",
                  "firmware_scope", "firmware_version"}


class IndexIsolationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for relative in (*INDEXABLE_CORPUS_FILES, "data/sources/manifest.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((corpus.ROOT / relative).read_bytes())
        self.canaries = {}
        # Include a valid corpus-shaped decoy, so a recursive loader cannot evade
        # this test merely by ignoring evaluation-shaped records.
        example = json.loads((self.root / INDEXABLE_CORPUS_FILES[0]).read_text(encoding="utf-8").splitlines()[0])
        for number, relative in enumerate(("data/evaluation/dev.jsonl", "data/evaluation/demo.jsonl",
                                           "data/graph/reference.json", "docs/reviews/canary.jsonl",
                                           "data/processed/canary.jsonl", "artifacts/answers.jsonl",
                                           "data/corpus/not-allowlisted.jsonl")):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            marker = f"FORBIDDEN_SOURCE_CANARY_{number}"
            decoy = {**example, "text": marker}
            if "not-allowlisted" not in relative:
                decoy.update(gold_evidence_ids=[marker], nodes=[marker])
            path.write_text(json.dumps(decoy), encoding="utf-8")
            self.canaries[path.resolve()] = marker
        self.manuals = [document("Synthetic authorized manual"),
                        document("Synthetic removed manual", evidence_id="ev1:" + "c" * 64)]

    def guard_reads(self):
        original = Path.open

        def guarded(path, mode="r", *args, **kwargs):
            if "r" in mode:
                self.assertNotIn(path.resolve(), self.canaries, "Forbidden source was opened")
            return original(path, mode, *args, **kwargs)

        return patch.object(Path, "open", guarded)

    def assert_clean(self, payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        for marker in self.canaries.values():
            self.assertNotIn(marker, serialized)

    def assert_sources(self, sources, expected):
        self.assert_clean(sources)
        self.assertEqual(len(sources), len(expected))
        for source in sources:
            self.assertEqual(set(source), set(load_mapping()["mappings"]["properties"]))
            self.assertFalse(FORBIDDEN_FIELDS & set(source))
        actual = {index_record_id(row): {key: value for key, value in row.items() if key != "embedding"}
                  for row in sources}
        self.assertEqual(actual, {index_record_id(row): row for row in expected})

    def exercise_indexing(self, client, *, through_cli=False):
        encoder = FixtureEmbedder()
        transport = client.request
        writes = []

        def capture(method, path, payload=None):
            if "_bulk" in path:
                lines = payload.decode("utf-8").splitlines()
                sources = [json.loads(line) for line in lines[1::2]]
                self.assertEqual([json.loads(line) for line in lines[::2]],
                                 [{"create": {"_id": index_record_id(row)}} for row in sources])
                writes.append(sources)
            return transport(method, path, payload)

        def run(command, previous=None):
            if through_cli:
                path = self.root / "artifacts" / f"{command}-{len(writes)}.json"
                args = [command, "--output", str(path)]
                if previous is not None:
                    args += ["--index", previous]
                cli.main(args)
                return json.loads(path.read_text(encoding="utf-8"))
            records = corpus.load_file_records(self.root) + self.manuals
            return dense.build_index(client, records, encoder) if previous is None else dense.sync_index(
                client, previous, records, encoder)

        with self.guard_reads(), patch.object(client, "request", side_effect=capture), \
                patch.object(dense, "DenseEmbedder", return_value=encoder):
            first = run("index")["index"]
            self.addCleanup(transport, "DELETE", f"/{first}")
            expected = corpus.load_file_records(self.root) + self.manuals
            self.assert_sources(writes[-1], expected)
            self.assert_sources(list(dense._read_index(client, first).values()), expected)
            self.assertEqual(encoder.calls, [[row["text"] for row in expected]])
            self.manuals = [{**self.manuals[0], "text": "Authorized revised manual"},
                            document("Authorized new revision", document_key="SYNTHETIC@B:" + "a" * 64,
                                     document_revision="B")]
            updated = run("sync", first)
            new = updated["index"]
            self.addCleanup(transport, "DELETE", f"/{new}")
            expected = corpus.load_file_records(self.root) + self.manuals
            self.assert_sources(writes[-1], expected)
            self.assert_sources(list(dense._read_index(client, new).values()), expected)
            self.assertEqual(encoder.calls[-1], [row["text"] for row in self.manuals])
            self.assertEqual((updated["added"], updated["removed"], updated["modified"]), (1, 1, 1))
            self.assertTrue(run("sync", new)["no_op"])
            self.assertEqual(len(writes), 2)
            self.assertEqual(len(encoder.calls), 2)
            self.assert_clean(encoder.calls)

    def test_production_build_and_sync_wire_payloads_and_full_readback(self):
        self.exercise_indexing(MemorySearch([]))

    def test_cli_uses_real_build_and_sync_with_only_authoritative_loaders(self):
        try:
            from app.db.connection import create_db_engine  # noqa: F401
        except ImportError:
            self.skipTest("CLI requires locked database dependencies")
        client = MemorySearch([])
        with patch.object(cli, "ROOT", self.root), patch.object(cli, "SearchClient", return_value=client), \
                patch.object(cli, "load_file_records", side_effect=lambda: corpus.load_file_records(self.root)), \
                patch.object(cli, "load_manual_records", side_effect=lambda engine: self.manuals), \
                patch("app.db.connection.create_db_engine"), patch("sys.stdout", new_callable=io.StringIO):
            self.exercise_indexing(client, through_cli=True)

    @unittest.skipUnless(os.environ.get("FORGERCA_TEST_OPENSEARCH") == "1", "Requires disposable OpenSearch")
    def test_real_opensearch_contains_only_the_authoritative_records(self):
        self.exercise_indexing(dense.SearchClient(Settings()))

    def test_extra_gold_graph_and_review_fields_fail_before_embedding_or_writes(self):
        records = corpus.load_file_records(self.root)
        for field in FORBIDDEN_FIELDS:
            leaked = [{**records[0], field: "FORBIDDEN_LABEL"}]
            for operation in ("index", "sync"):
                client, encoder = Mock(), FixtureEmbedder()
                with self.subTest(field=field, operation=operation), self.assertRaises(ValueError):
                    if operation == "index":
                        dense.build_index(client, leaked, encoder)
                    else:
                        dense.sync_index(client, "old-index", leaked, encoder)
                self.assertEqual(encoder.calls, [])
                client.request.assert_not_called()

    def test_generation_http_body_contains_only_verified_evidence_context(self):
        records = corpus.load_file_records(self.root)
        selected = [hit(next(row for row in records if row["evidence_id"] == identity), rank)
                    for rank, identity in enumerate(("K001", "K009"), 1)]
        with patch.object(generation, "build_opener") as opener:
            generator = generation.Generator(Settings.from_env({"DASHSCOPE_API_KEY": "synthetic-test-only"}))
        response = api_response({"status": "insufficient", "candidate_causes": [],
                                 "missing_evidence": ["合成测试缺口"]})
        opener.return_value.open.return_value = io.BytesIO(json.dumps(response).encode("utf-8"))
        with self.guard_reads():
            generation.answer_question("Synthetic question", selected, generator=generator, root=self.root)
        payload = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assert_clean(payload)
        context = json.loads(payload["messages"][1]["content"])
        self.assertEqual(set(context), {"question", "evidence"})
        self.assertEqual(context["evidence"], [{key: row[key] for key in CONTEXT_FIELDS} for row in selected])
        for item in context["evidence"]:
            self.assertEqual(set(item), CONTEXT_FIELDS)
            self.assertFalse(FORBIDDEN_FIELDS & set(item))
        # A label attached to a hit must fail citation validation before another API request.
        for field in FORBIDDEN_FIELDS:
            contaminated = deepcopy(selected)
            contaminated[0][field] = "FORBIDDEN_LABEL"
            with self.subTest(field=field), self.assertRaises(ValueError):
                generation.answer_question("Synthetic question", contaminated, generator=generator, root=self.root)
        opener.return_value.open.assert_called_once()
