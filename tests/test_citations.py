"""Citation resolution rejects stale indexes and preserves source and revision identity."""

import io
import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from app.retrieval import citations, corpus
from app.retrieval.index_schema import index_record_id
from app.schemas.document import DocumentKey
from scripts import dense as cli
from scripts.corpus_allowlist import INDEXABLE_CORPUS_FILES
from scripts.ingest import load_snapshot
from test_ingest import write_snapshot


def hit(record, rank=1):
    return {**deepcopy(record), "index_id": index_record_id(record), "rank": rank, "score": 1.0}


def manual_fixture(root, revision="A"):
    path, _ = write_snapshot(root, revision=revision)
    prepared = load_snapshot(path, root)
    prepared["document"]["source_metadata"]["effective_date"] = "2024-03-30"
    return {**prepared["document"], **prepared["chunks"][0]}


class FileCitationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name in (*INDEXABLE_CORPUS_FILES, "data/sources/manifest.json"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((corpus.ROOT / name).read_bytes())
        self.hits = [hit(record, rank) for rank, record in enumerate(corpus.load_file_records(self.root), 1)]

    def test_file_citations_read_only_allowlist_and_preserve_provenance(self):
        before = deepcopy(self.hits)
        allowed = {(self.root / name).resolve() for name in
                   (*INDEXABLE_CORPUS_FILES, "data/sources/manifest.json")}
        allowed.add((corpus.ROOT / "versions.lock.json").resolve())
        read = Path.read_text

        def guarded(path, *args, **kwargs):
            self.assertIn(path.resolve(), allowed)
            return read(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded), patch.object(citations, "_read_manuals") as database:
            result = citations.resolve_hits(self.hits, root=self.root)
        database.assert_not_called()
        self.assertEqual(self.hits, before)
        self.assertEqual(len(result), 33)
        for resolved, original in zip(result, self.hits, strict=True):
            self.assertEqual({key: resolved[key] for key in original}, original)
            if resolved["synthetic"]:
                self.assertIsNone(resolved["source"])
                self.assertEqual(resolved["locator"]["record_id"], resolved["evidence_id"])
                self.assertIn(resolved["locator"]["file"], INDEXABLE_CORPUS_FILES)
            else:
                self.assertEqual(resolved["record_kind"], "knowledge_note")
                self.assertIsNone(resolved["document_key"])
                self.assertEqual(resolved["source"]["revision"], resolved["document_revision"])
                self.assertEqual(resolved["source"]["source_id"], resolved["source_id"])
                self.assertTrue(resolved["locator"]["url"].endswith(f'#page={resolved["locator"]["pdf_page"]}'))
        result[0]["model"].append("mutated result")
        self.assertEqual(self.hits, before)

    def test_empty_result_needs_no_source_or_database_access(self):
        with patch.object(citations, "load_file_corpus") as files, \
                patch.object(citations, "_read_manuals") as database:
            self.assertEqual(citations.resolve_hits([]), [])
        files.assert_not_called()
        database.assert_not_called()

    def test_stale_text_or_metadata_and_invalid_identity_fail_closed(self):
        changes = ({"text": "private stale body"}, {"model": ["OTHER"]}, {"document_revision": "OTHER"},
                   {"available_at": "2000-01-01T00:00:00Z"}, {"firmware_scope": None},
                   {"index_id": "0" * 64}, {"score": float("nan")}, {"rank": True},
                   {"gold_evidence_ids": ["private"]}, {"record_kind": "diagnosis_run"},
                   {"evidence_id": "MISSING"}, {"synthetic": True})
        for change in changes:
            row = {**self.hits[0], **change}
            if "index_id" not in change:
                row["index_id"] = index_record_id(row)
            with self.subTest(change=change), self.assertRaises(citations.CitationError) as caught:
                citations.resolve_hits([row], root=self.root)
            self.assertNotIn("private", str(caught.exception))
        for rows in (None, [None], [self.hits[0], {**self.hits[0], "rank": 2}]):
            with self.subTest(rows=type(rows)), self.assertRaises(citations.CitationError):
                citations.resolve_hits(rows, root=self.root)

    def test_changed_or_missing_file_source_and_unverified_labels_are_rejected(self):
        path = self.root / "data/corpus/knowledge.jsonl"
        original = path.read_text(encoding="utf-8")
        for field, value in (("pdf_page", 1), ("printed_page", "invented"), ("file", "data/evaluation/dev.jsonl")):
            rows = [json.loads(line) for line in original.splitlines()]
            rows[0]["locator"][field] = value
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(citations.CitationError):
                citations.resolve_hits([self.hits[0]], root=self.root)
        path.write_text(original, encoding="utf-8")
        manifest = self.root / "data/sources/manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        source = next(s for s in data["sources"] if s["id"] == self.hits[0]["source_id"])
        source["sha256"] = "a" * 64
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(citations.CitationError):
            citations.resolve_hits([self.hits[0]], root=self.root)
        manifest.unlink()
        with self.assertRaises(citations.CitationError):
            citations.resolve_hits([self.hits[0]], root=self.root)

    def test_query_command_publishes_verified_locators_or_no_report(self):
        path = self.root / "artifacts/result.json"
        args = ["query", "--index", "fixture", "--query", "synthetic", "--model", "ACS580-01",
                "--as-of", "2026-11-09T00:00:00Z", "--output", str(path)]
        self.enterContext(patch.object(cli, "ROOT", self.root))
        self.enterContext(patch.object(cli, "SearchClient"))
        self.enterContext(patch("sys.stdout", new_callable=io.StringIO))
        stderr = self.enterContext(patch("sys.stderr", new_callable=io.StringIO))
        self.enterContext(patch.object(cli, "resolve_hits", side_effect=lambda rows:
                                     citations.resolve_hits(rows, root=self.root)))
        with patch.object(cli, "retrieve", return_value={"index": "fixture", "hits": [self.hits[0]]}):
            cli.main(args)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["hits"][0]["evidence_id"], "K001")
        self.assertEqual(saved["hits"][0]["locator"]["pdf_page"], 536)
        failed = path.with_name("failed.json")
        bad = {**self.hits[1], "text": "private stale body"}
        with patch.object(cli, "retrieve", return_value={"index": "fixture", "hits": [self.hits[0], bad]}), \
                self.assertRaises(SystemExit) as caught:
            cli.main([*args[:-1], str(failed)])
        self.assertEqual(caught.exception.code, 1)
        self.assertFalse(failed.exists())
        self.assertNotIn("private", stderr.getvalue())


class ManualCitationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.row = manual_fixture(self.root)
        self.hit = hit(corpus.project_manual(self.row))

    def resolve(self, rows, hits=None):
        with patch.object(citations, "_read_manuals", return_value=rows) as read, \
                patch.object(citations, "load_file_corpus", side_effect=AssertionError("No manifest fallback")):
            result = citations.resolve_hits(hits or [self.hit], root=self.root)
        read.assert_called_once_with([(row["document_key"], row["evidence_id"]) for row in hits or [self.hit]], None)
        return result

    def test_historical_revisions_resolve_by_full_identity_and_keep_unknown_printed_page(self):
        second = manual_fixture(self.root, "B")
        hits = [self.hit, hit(corpus.project_manual(second), 2)]
        self.assertEqual(hits[0]["evidence_id"], hits[1]["evidence_id"])
        result = self.resolve([self.row, second], hits)
        self.assertEqual([r["source"]["revision"] for r in result], ["A", "B"])
        for row in result:
            self.assertEqual(row["source"]["document_key"], row["document_key"])
            self.assertEqual(row["locator"]["locations"], [
                {"pdf_page": 1, "printed_page": None, "url": "https://example.com/manual.pdf#page=1"}])
            self.assertEqual(row["locator"]["evidence_locator"], self.row["evidence_locator"])
            self.assertEqual(row["locator"]["section"], self.row["section"])
            self.assertIsNone(row["locator"]["table_row"])

    def test_missing_ambiguous_or_changed_authoritative_manual_is_rejected(self):
        rows = [[], [self.row, deepcopy(self.row)]]
        for field, value in (("text", "private changed body"), ("source_url", "https://example.com/other.pdf"),
                             ("sha256", "f" * 64), ("document_code", "OTHER"), ("models", ["OTHER"]),
                             ("revision", "B"), ("source_id", "OTHER"), ("accessed_at", "2099-01-01"),
                             ("firmware_scope", "ASCKX 2.16")):
            rows.append([{**self.row, field: value}])
        for candidates in rows:
            with self.subTest(count=len(candidates)), self.assertRaises(citations.CitationError):
                self.resolve(candidates)

    def test_multiple_physical_pages_keep_explicit_printed_labels_and_table_context(self):
        from app.ingestion.metadata import locate_chunk
        from test_location_metadata import identified_chunk, source

        metadata = {**source(), "models": ["TEST-MODEL"], "effective_date": "2024-03-30"}
        row = {**locate_chunk(identified_chunk(), metadata), **asdict(DocumentKey.from_source(metadata)),
               "source_metadata": metadata, "models": metadata["models"], "fault_codes": []}
        row["table_row"] = {"table_ref": "#/tables/0", "row_range": [2, 4]}
        result = self.resolve([row], [hit(corpus.project_manual(row))])[0]
        self.assertEqual([(p["pdf_page"], p["printed_page"]) for p in result["locator"]["locations"]],
                         [(7, "vii"), (8, "A-1")])
        self.assertEqual(result["locator"]["table_row"], row["table_row"])
        self.assertEqual(result["locator"]["section"], ["Parent", "Child"])

    def test_changed_locator_page_label_or_source_fingerprint_is_rejected(self):
        mutations = [lambda row: row["evidence_locator"].update(source_id="OTHER"),
                     lambda row: row["evidence_locator"].update(sha256="c" * 64),
                     lambda row: row["evidence_locator"].update(version=2),
                     lambda row: row["evidence_locator"]["elements"][0].update(pdf_page=2),
                     lambda row: row["evidence_locator"]["elements"][0]["bbox_milli"].__setitem__(0, 1),
                     lambda row: row["locations"][0].update(pdf_page=2),
                     lambda row: row["locations"][0].update(printed_page="invented"),
                     lambda row: row["source_metadata"].update(sha256="c" * 64),
                     lambda row: row["source_metadata"].update(effective_date="2099-01-01")]
        for mutate in mutations:
            row = deepcopy(self.row)
            mutate(row)
            with self.subTest(mutate=mutate), self.assertRaises(citations.CitationError):
                self.resolve([row])
