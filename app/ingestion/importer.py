"""Transactional appends, explicit page replacements and manual retirement."""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.db import schema as db
from app.schemas.document import parse_key
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


def import_snapshot(engine, prepared, *, replace=False):
    """Consume a verified snapshot, serializing writers on its parent document row."""
    doc, chunks = prepared["document"], prepared["chunks"]
    key = doc["document_key"]
    with engine.begin() as connection:
        created = _insert_immutable(connection, db.document, doc)
        if connection.scalar(sa.select(db.document.c.retired_at).where(db.document.c.document_key == key)):
            raise ValueError("Document is retired; import cannot reactivate it")
        if replace and created:
            raise ValueError("Replacement requires an existing document; import it first")
        prior = connection.execute(sa.select(db.ingest_run).where(
            db.ingest_run.c.document_key == key, db.ingest_run.c.run_status == "succeeded",
        ).order_by(db.ingest_run.c.finished_at.desc(), db.ingest_run.c.ingest_run_id.desc())).mappings().all()
        existing = {row["evidence_id"]: row for row in connection.execute(
            sa.select(db.chunk).where(db.chunk.c.document_key == key)).mappings()}
        start_page, end_page = prepared["parser"]["page_range"]
        if replace:
            affected = {identity: old for identity, old in existing.items() if any(
                start_page <= location["pdf_page"] <= end_page for location in old["locations"])}
            if any(not start_page <= location["pdf_page"] <= end_page
                   for old in affected.values() for location in old["locations"]):
                raise ValueError("Replacement must cover every page of an affected chunk")
            overlapping = [run for run in prior if run["parser"]["page_range"][0] <= end_page
                           and run["parser"]["page_range"][1] >= start_page]
            unchanged = (set(affected) == {chunk["evidence_id"] for chunk in chunks}
                         and all(all(affected[chunk["evidence_id"]][field] == value for field, value in chunk.items())
                                 for chunk in chunks))
            if overlapping and overlapping[0]["input_sha256"] == prepared["input_sha256"] and unchanged:
                return {"ingest_run_id": str(overlapping[0]["ingest_run_id"]), "inserted_chunks": 0,
                        "removed_chunks": 0, "reused": True}
            if affected:
                connection.execute(db.chunk.delete().where(db.chunk.c.document_key == key,
                                                           db.chunk.c.evidence_id.in_(list(affected))))
            return _write_chunks(connection, prepared, chunks, operation="replace", removed=len(affected))
        incoming_ids = {chunk["evidence_id"] for chunk in chunks}
        for evidence_id, old in existing.items():
            if evidence_id not in incoming_ids and any(
                start_page <= location["pdf_page"] <= end_page for location in old["locations"]
            ):
                raise ValueError("Snapshot omits existing evidence on these pages; replacement is not enabled")
        ranges = [run["parser"]["page_range"] for run in prior]
        for chunk in chunks:
            old = existing.get(chunk["evidence_id"])
            if old is not None:
                if any(old[field] != value for field, value in chunk.items()):
                    raise ValueError("Existing evidence has different content; reparse replacement is not enabled")
            elif any(start <= location["pdf_page"] <= end
                     for start, end in ranges for location in chunk["locations"]):
                raise ValueError("New evidence overlaps imported pages; reparse replacement is not enabled")
        # Replay must still match current rows: a historical hash is not proof
        # that its chunks remain current after an explicit replacement.
        for run in prior:
            if run["input_sha256"] == prepared["input_sha256"]:
                return {"ingest_run_id": str(run["ingest_run_id"]), "inserted_chunks": 0,
                        "removed_chunks": 0, "reused": True}
        return _write_chunks(connection, prepared, [chunk for chunk in chunks if chunk["evidence_id"] not in existing])


def _write_chunks(connection, prepared, chunks, *, operation="append", removed=0):
    run_id = uuid4()
    connection.execute(db.ingest_run.insert().values(
        ingest_run_id=run_id, document_key=prepared["document"]["document_key"], input_path=prepared["input_path"],
        input_sha256=prepared["input_sha256"], parser=prepared["parser"], operation=operation,
    ))
    for chunk in chunks:
        connection.execute(db.chunk.insert().values(**chunk, ingest_run_id=run_id))
    connection.execute(db.ingest_run.update().where(db.ingest_run.c.ingest_run_id == run_id).values(
        run_status="succeeded", finished_at=sa.func.clock_timestamp(),
    ))
    return {"ingest_run_id": str(run_id), "inserted_chunks": len(chunks), "removed_chunks": removed, "reused": False}


def retire_document(engine, document_key):
    """Retire one stored manual revision, preserving chunks and import audit rows."""
    parse_key(document_key)
    with engine.begin() as connection:
        row = connection.execute(sa.select(db.document).where(
            db.document.c.document_key == document_key).with_for_update()).mappings().one_or_none()
        if row is None:
            raise ValueError("Document does not exist")
        retired_at = row["retired_at"]
        reused = retired_at is not None
        if not reused:
            retired_at = connection.scalar(db.document.update().where(
                db.document.c.document_key == document_key).values(retired_at=sa.func.clock_timestamp()).returning(
                    db.document.c.retired_at))
        return {"document_key": document_key, "retired_at": retired_at.isoformat(), "reused": reused}


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
