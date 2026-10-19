"""Explicit allowlist for everything that may enter a retrieval index.

`data/evaluation/`, `data/graph/` and `docs/reviews/` contain gold answers,
reference graphs and review notes. They are shaped like corpus data (JSON,
JSONL, Markdown), so a builder that walks a directory tree with
``rglob("*.jsonl")`` would silently index the answers it is supposed to be
scored against. Marking the directory as "excluded" in prose is not enough:
the exclusion has to be executable.

Rules for data builders (M1 onward):

1. Call :func:`indexable_files` instead of globbing a directory.
2. Call :func:`assert_indexable` before reading any path that came from
   configuration, a CLI argument or a manifest.
3. Never add an entry to :data:`INDEXABLE_CORPUS_FILES` for evaluation,
   graph-reference or review material. If a new corpus store is added, add it
   explicitly and update the data card.

``tests/test_corpus_isolation.py`` fails if the boundary weakens.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The only files that may become retrieval documents. Explicit and literal on
# purpose: no globs, no directory recursion, no "everything under data/".
INDEXABLE_CORPUS_FILES = (
    "data/corpus/knowledge.jsonl",
    "data/corpus/work_orders.jsonl",
    "data/corpus/alarms.jsonl",
)

# Paths that must stay out of every index even though they parse as data.
FORBIDDEN_PREFIXES = (
    "data/evaluation/",
    "data/graph/",
    "docs/reviews/",
    "data/raw/",
    "data/processed/",
    "data/indexes/",
    "artifacts/",
)


class IndexScopeError(ValueError):
    """Raised when a path is outside the indexable corpus allowlist."""


def repo_relative(path, root=None):
    """Resolve ``path`` and return it as a POSIX path relative to the repo root.

    Raises :class:`IndexScopeError` for paths that escape the repository, so a
    ``..`` segment cannot be used to reach evaluation labels indirectly.
    """
    base = Path(root or ROOT).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve().relative_to(base).as_posix()
    except ValueError as error:
        raise IndexScopeError(f"Path is outside the repository: {path}") from error


def assert_indexable(path, root=None):
    """Return the repo-relative path, or raise if it may not be indexed."""
    relative = repo_relative(path, root)
    for prefix in FORBIDDEN_PREFIXES:
        if relative.startswith(prefix):
            raise IndexScopeError(
                f"Refusing to index {relative}: reserved for evaluation, reference or review material"
            )
    if relative not in INDEXABLE_CORPUS_FILES:
        raise IndexScopeError(f"Refusing to index {relative}: not on the explicit allowlist")
    return relative


def indexable_files(root=None):
    """Return the allowlisted corpus files in a stable order.

    This never scans a directory. A missing allowlisted file is an error
    rather than a silent skip, because a builder that indexes fewer files than
    declared usually means the path convention changed.
    """
    base = Path(root or ROOT)
    resolved = []
    for relative in INDEXABLE_CORPUS_FILES:
        path = base / relative
        if not path.is_file():
            raise IndexScopeError(f"Allowlisted corpus file is missing: {relative}")
        resolved.append(assert_indexable(path, base))
    return tuple(resolved)
