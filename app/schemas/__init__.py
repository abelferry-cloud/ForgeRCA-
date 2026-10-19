"""Shared data contracts: request/response models and evidence identifiers.

Filled alongside the features that need them. Schemas must stay free of
persistence and transport code so any layer can import them: no imports from
``app.api``, ``app.db``, ``app.ingestion`` or ``app.retrieval``.
"""
