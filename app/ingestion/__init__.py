"""Document ingestion: parsing, chunking and stable evidence anchors.

Filled by M1-07 to M1-16. Rules that belong to this layer:

- an evidence ID is derived from ``source_id + sha256 + page + locator``,
  never from a row index or retrieval rank;
- raw PDFs stay under the ignored ``data/raw/``;
- derived chunks are written to ``data/processed/`` and are rebuildable.

This package must not import ``app.api``.
"""
