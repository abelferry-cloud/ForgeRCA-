"""Retrieval: query normalisation, dense/lexical search and fusion.

Index field contracts arrive in M1-19; retrieval in M1-21 and M2. Every
returned item must carry a stable evidence ID plus its source locator; the
same evidence reached through two paths counts once.

This package must not import ``app.api``.
"""
