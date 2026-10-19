"""Guards that keep evaluation labels out of any future retrieval index (M0-21)."""

from __future__ import annotations

import unittest

from scripts import corpus_allowlist as allowlist
from scripts.validate_data import CORPUS_FILES


class CorpusIsolationTests(unittest.TestCase):
    def test_allowlist_is_explicit_and_present(self):
        self.assertEqual(len(allowlist.INDEXABLE_CORPUS_FILES), 3)
        self.assertEqual(allowlist.indexable_files(), allowlist.INDEXABLE_CORPUS_FILES)
        for relative in allowlist.INDEXABLE_CORPUS_FILES:
            self.assertTrue((allowlist.ROOT / relative).is_file(), relative)

    def test_validator_corpus_files_cannot_drift_from_allowlist(self):
        self.assertEqual(set(CORPUS_FILES.values()), set(allowlist.INDEXABLE_CORPUS_FILES))

    def test_allowlisted_files_are_self_consistent(self):
        for relative in allowlist.INDEXABLE_CORPUS_FILES:
            self.assertEqual(allowlist.assert_indexable(relative), relative)

    def test_evaluation_graph_and_review_files_are_refused(self):
        refused = (
            "data/evaluation/dev.jsonl",
            "data/evaluation/demo.jsonl",
            "data/graph/reference.json",
            "docs/reviews/seed-v0.2-human-review.md",
            "data/processed/public/normalized.jsonl",
            "artifacts/retrieval_ablation.csv",
        )
        for relative in refused:
            with self.subTest(relative=relative), self.assertRaises(allowlist.IndexScopeError):
                allowlist.assert_indexable(relative)

    def test_path_traversal_out_of_the_corpus_is_refused(self):
        for relative in ("data/corpus/../evaluation/dev.jsonl", "../ForgeRCA-evil/data/corpus/knowledge.jsonl"):
            with self.subTest(relative=relative), self.assertRaises(allowlist.IndexScopeError):
                allowlist.assert_indexable(relative)

    def test_unknown_corpus_file_is_refused(self):
        with self.assertRaisesRegex(allowlist.IndexScopeError, "explicit allowlist"):
            allowlist.assert_indexable("data/corpus/unreviewed_extra.jsonl")

    def test_naive_recursive_scan_would_leak_labels(self):
        """Documents why the allowlist exists instead of a recursive glob."""
        scanned = {
            path.relative_to(allowlist.ROOT).as_posix()
            for path in (allowlist.ROOT / "data").rglob("*.jsonl")
        }
        leaked = scanned - set(allowlist.INDEXABLE_CORPUS_FILES)
        self.assertIn("data/evaluation/dev.jsonl", leaked)
        self.assertIn("data/evaluation/demo.jsonl", leaked)


if __name__ == "__main__":
    unittest.main()
