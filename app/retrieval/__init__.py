"""Retrieval: query normalisation, dense/lexical search and fusion.

Filled from M1-21 (dense baseline) and M2 (BM25, RRF, reranker). Every
returned item must carry a stable evidence ID plus its source locator; the
same evidence reached through two paths counts once.

This package must not import ``app.api``.
"""
