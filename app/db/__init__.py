"""Persistence: connection handling, schema migrations and repositories.

PostgreSQL is the authoritative store for document/chunk metadata, ingest
runs and diagnosis runs. It is not a second vector store. OpenSearch and
Neo4j access lives with the code that uses it, not here.

This package must not import ``app.api``, ``app.ingestion`` or
``app.retrieval``.
"""
