"""Transactional inserts for validated inputs from scripts.ingest; no overwrites."""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.db import schema as db
from app.schemas.events import event_time, validate_seed_events


def _insert_immutable(connection, table, values):
    keys = list(table.primary_key.columns)
    inserted = connection.execute(insert(table).values(**values).on_conflict_do_nothing(
        index_elements=keys).returning(keys[0])).first() is not None
    row = connection.execute(sa.select(table).where(
        *(column == values[column.name] for column in keys)).with_for_update()).mappings().one()
    if any(row[key] != value for key, value in values.items()):
        raise ValueError(f"Existing {table.name} identity has different content; refusing to overwrite")
    return inserted


def import_snapshot(engine, prepared):
    """Consume a verified snapshot, serializing writers on its parent document row."""
    doc, chunks = prepared["document"], prepared["chunks"]
    key = doc["document_key"]
    with engine.begin() as connection:
        _insert_immutable(connection, db.document, doc)
        prior = connection.execute(sa.select(db.ingest_run).where(
            db.ingest_run.c.document_key == key, db.ingest_run.c.run_status == "succeeded",
        )).mappings().all()
        for run in prior:
            if run["input_sha256"] == prepared["input_sha256"]:
                return {"ingest_run_id": str(run["ingest_run_id"]), "inserted_chunks": 0, "reused": True}
        existing = {row["evidence_id"]: row for row in connection.execute(
            sa.select(db.chunk).where(db.chunk.c.document_key == key)).mappings()}
        ranges = [run["parser"]["page_range"] for run in prior]
        for chunk in chunks:
            old = existing.get(chunk["evidence_id"])
            if old is not None:
                if any(old[field] != value for field, value in chunk.items()):
                    raise ValueError("Existing evidence has different content; reparse replacement is not enabled")
            elif any(start <= location["pdf_page"] <= end
                     for start, end in ranges for location in chunk["locations"]):
                raise ValueError("New evidence overlaps imported pages; reparse replacement is not enabled")
        run_id = uuid4()
        connection.execute(db.ingest_run.insert().values(
            ingest_run_id=run_id, document_key=key, input_path=prepared["input_path"],
            input_sha256=prepared["input_sha256"], parser=prepared["parser"],
        ))
        count = 0
        for chunk in chunks:
            if chunk["evidence_id"] not in existing:
                connection.execute(db.chunk.insert().values(**chunk, ingest_run_id=run_id))
                count += 1
        connection.execute(db.ingest_run.update().where(db.ingest_run.c.ingest_run_id == run_id).values(
            run_status="succeeded", finished_at=sa.func.clock_timestamp(),
        ))
        return {"ingest_run_id": str(run_id), "inserted_chunks": count, "reused": False}


def import_seed_events(engine, corpus):
    """Insert an entire validated seed batch atomically, preserving synthetic identity."""
    validate_seed_events(corpus)
    assets = {record["asset_id"]: {key: record[key] for key in ("asset_id", "model", "synthetic")}
              for records in corpus.values() for record in records}
    counts = {"asset": 0, "work_order": 0, "alarm": 0}
    with engine.begin() as connection:
        # Stable order prevents concurrent identical batches locking assets in opposite orders.
        for asset_id in sorted(assets):
            counts["asset"] += _insert_immutable(connection, db.asset, assets[asset_id])
        for kind, table in (("work_order", db.work_order), ("alarm", db.alarm)):
            for record in sorted(corpus[kind], key=lambda row: row["id"]):
                values = {key: value for key, value in record.items() if key not in {"id", "kind"}}
                values[f"{kind}_id"] = record["id"]
                for field in ("opened_at", "closed_at", "available_at", "occurred_at"):
                    if field in values:
                        values[field] = event_time(values[field])
                counts[kind] += _insert_immutable(connection, table, values)
    return counts
