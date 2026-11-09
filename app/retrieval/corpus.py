"""Project explicit corpus files and successfully imported manual chunks for search."""

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from app.retrieval.index_schema import index_record_id, load_mapping, validate_index_metadata
from app.schemas.document import parse_key
from scripts.corpus_allowlist import INDEXABLE_DATABASE_TABLES, assert_indexable, indexable_files
from scripts.validate_data import CORPUS_FILES, validate_corpus

ROOT = Path(__file__).resolve().parents[2]
NOTE_FIELDS = {"id", "kind", "model", "synthetic", "text", "available_at", "document_revision",
               "firmware_scope", "alarm_code", "locator"}


def project_record(record):
    """Keep project notes and synthetic events distinct from manufacturer chunks."""
    note = record["kind"] == "knowledge_note"
    if note and set(record) != NOTE_FIELDS:
        raise ValueError("Unexpected or missing knowledge note fields")
    firmware = record["firmware_scope" if note else "firmware_version"]
    return {
        "evidence_id": record["id"], "document_key": None,
        "source_id": record["locator"]["source_id"] if note and not record["synthetic"] else None,
        "document_revision": record["document_revision"] if note else None,
        "record_kind": record["kind"], "chunk_type": None, "model": [record["model"]],
        "firmware_scope": firmware if note else None, "firmware_version": None if note else firmware,
        "firmware_state": "known" if firmware is not None else ("unrestricted" if note else "unknown"),
        "synthetic": record["synthetic"], "available_at": record["available_at"],
        "alarm_code": [] if record["alarm_code"] is None else [record["alarm_code"]], "text": record["text"],
    }


def project_manual(row):
    # effective_date has day precision. This project projects it to midnight
    # Asia/Shanghai (+08:00); accessed_at and ingestion timestamps are not evidence availability.
    source = row["source_metadata"]
    if parse_key(row["document_key"]).sha256 != source["sha256"]:
        raise ValueError("Manual fingerprint differs from the imported source")
    effective = date.fromisoformat(source["effective_date"])
    if effective.isoformat() != source["effective_date"]:
        raise ValueError("Manual effective_date must be YYYY-MM-DD")
    for field, source_field in (("source_id", "id"), ("revision", "revision"),
                                ("models", "models"), ("firmware_scope", "firmware_scope")):
        if row[field] != source[source_field]:
            raise ValueError("Manual metadata differs from the imported source")
    return {
        "evidence_id": row["evidence_id"], "document_key": row["document_key"],
        "source_id": row["source_id"], "document_revision": row["revision"],
        "record_kind": "manual_chunk", "chunk_type": row["chunk_type"], "model": row["models"],
        "firmware_scope": row["firmware_scope"], "firmware_version": None,
        "firmware_state": "unrestricted" if row["firmware_scope"] is None else "known", "synthetic": False,
        "available_at": datetime.combine(effective, time.min, timezone(timedelta(hours=8))).isoformat(),
        "alarm_code": list(dict.fromkeys(code["raw_code"] for code in row["fault_codes"])), "text": row["text"],
    }


def load_file_corpus(root=ROOT):
    root = Path(root)
    allowed = indexable_files(root)
    corpus = {}
    for kind, path in CORPUS_FILES.items():
        relative = assert_indexable(path, root)
        if relative not in allowed:
            raise ValueError("Corpus files differ from the allowlist")
        corpus[kind] = [json.loads(line) for line in (root / relative).read_text(encoding="utf-8").splitlines()
                        if line.strip()]
    sources = json.loads((root / "data/sources/manifest.json").read_text(encoding="utf-8"))["sources"]
    sources, evidence, _, _ = validate_corpus(sources, corpus)
    records = [project_record(record) for group in corpus.values() for record in group]
    validate_records(records)
    return sources, evidence


def load_file_records(root=ROOT):
    _, evidence = load_file_corpus(root)
    return [project_record(record) for record in evidence.values()]


def load_manual_rows(engine, identities=None):
    import sqlalchemy as sa

    from app.db import schema as db

    if INDEXABLE_DATABASE_TABLES != (db.chunk.name,):
        raise ValueError("Unexpected database corpus allowlist")
    query = sa.select(db.chunk, db.document.c.source_id, db.document.c.revision, db.document.c.models,
                      db.document.c.firmware_scope, db.document.c.source_metadata, db.document.c.sha256,
                      db.document.c.document_code, db.document.c.source_url, db.document.c.accessed_at).select_from(
        db.chunk.join(db.document).join(db.ingest_run, sa.and_(
            db.chunk.c.ingest_run_id == db.ingest_run.c.ingest_run_id,
            db.chunk.c.document_key == db.ingest_run.c.document_key,
        ))).where(db.ingest_run.c.run_status == "succeeded").order_by(db.chunk.c.document_key, db.chunk.c.evidence_id)
    if identities is not None:
        query = query.where(sa.tuple_(db.chunk.c.document_key, db.chunk.c.evidence_id).in_(identities))
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def load_manual_records(engine):
    return validate_records([project_manual(row) for row in load_manual_rows(engine)])


def validate_records(records):
    mapping = load_mapping()
    identities = set()
    for record in records:
        validate_index_metadata(record, mapping)
        identity = index_record_id(record)
        if identity in identities:
            raise ValueError("Duplicate corpus identity")
        identities.add(identity)
    return records
