"""Resolve retrieval hits against their authorized sources before publishing citations."""

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import asdict
from datetime import date

from app.ingestion.metadata import locate_chunk
from app.retrieval.corpus import (
    ROOT,
    load_file_corpus,
    load_manual_rows,
    project_manual,
    project_record,
    validate_records,
)
from app.retrieval.index_schema import index_record_id
from app.schemas.document import DocumentKey, printed_page_labels


class CitationError(ValueError):
    """A source could not be verified; no partial citations should be published."""


def _source(source):
    key = DocumentKey.from_source(source)
    return {"document_key": key.value, **asdict(key)}


def _page_url(source, page):
    return source["url"].split("#", 1)[0] + f"#page={page}"


def _manual_citation(row):
    source = row["source_metadata"]
    identity = _source(source)
    for field, expected in identity.items():
        actual = row[field]
        if field == "accessed_at" and isinstance(actual, date):
            actual = actual.isoformat()
        if actual != expected:
            raise ValueError("Stored document identity differs from its source metadata")
    locator = row["evidence_locator"]
    if set(locator) != {"version", "source_id", "sha256", "elements"} or type(locator["version"]) is not int:
        raise ValueError("Invalid evidence locator")
    encoded = json.dumps(locator, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if locator["version"] != 1 or "ev1:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest() != row["evidence_id"]:
        raise ValueError("Evidence locator fingerprint mismatch")
    expected_locations = locate_chunk(row, source)["locations"]
    if row["locations"] != expected_locations:
        raise ValueError("Stored display locations differ from the physical evidence")
    return {"source": identity, "locator": {
        "evidence_locator": deepcopy(locator),
        "locations": [{**location, "url": _page_url(source, location["pdf_page"])}
                      for location in expected_locations],
        "section": deepcopy(row["section"]), "table_row": deepcopy(row["table_row"]),
    }}


def _file_citation(record, sources):
    locator = deepcopy(record["locator"])
    if record["synthetic"]:
        return {"source": None, "locator": locator}
    source = sources[locator["source_id"]]
    # A project note is not a parsed manufacturer chunk. Its printed label must
    # agree with the fingerprint-bound manifest map, rather than an inferred offset.
    if (set(locator) != {"source_id", "pdf_page", "printed_page", "section"}
            or printed_page_labels(source).get(locator["pdf_page"]) != locator["printed_page"]):
        raise ValueError("Note page label is not verified by the source manifest")
    return {"source": _source(source), "locator": {**locator, "url": _page_url(source, locator["pdf_page"])}}


def _read_manuals(identities, engine):
    from sqlalchemy.exc import SQLAlchemyError

    from app.db.connection import create_db_engine

    owned = engine is None
    try:
        if owned:
            engine = create_db_engine()
        return load_manual_rows(engine, identities)
    except SQLAlchemyError:
        raise CitationError("Citation database read failed; no verified result is available") from None
    finally:
        if owned and engine is not None:
            engine.dispose()


def resolve_hits(hits, *, root=ROOT, engine=None):
    """Return ordered copies with source/locator, or fail the whole result.

    Only manual hits require PostgreSQL. An injected engine remains caller-owned.
    Historical manual revisions use the imported source snapshot, not today's manifest.
    """
    try:
        if not isinstance(hits, list):
            raise ValueError("Hits must be a list")
        if not hits:
            return []
        records = [{key: value for key, value in hit.items() if key not in {"rank", "score", "index_id"}}
                   for hit in hits]
        validate_records(records)
        for rank, (hit, record) in enumerate(zip(hits, records, strict=True), 1):
            if (type(hit["rank"]) is not int or hit["rank"] != rank or hit["index_id"] != index_record_id(record)
                    or type(hit["score"]) not in (int, float) or not math.isfinite(hit["score"]) or hit["score"] < 0):
                raise ValueError("Invalid retrieval identity or ranking")
        identities = [(hit["document_key"], hit["evidence_id"]) for hit in hits
                      if hit["record_kind"] == "manual_chunk"]
        manuals = {}
        if identities:
            for row in _read_manuals(identities, engine):
                key = (row["document_key"], row["evidence_id"])
                if key in manuals:
                    raise ValueError("Ambiguous manual identity")
                manuals[key] = row
        sources, files = load_file_corpus(root) if len(identities) != len(hits) else ({}, {})
        resolved = []
        for hit, record in zip(hits, records, strict=True):
            if hit["record_kind"] == "manual_chunk":
                row = manuals[(hit["document_key"], hit["evidence_id"])]
                expected, citation = project_manual(row), _manual_citation(row)
            else:
                original = files[hit["evidence_id"]]
                expected, citation = project_record(original), _file_citation(original, sources)
            if record != expected:
                raise ValueError("Indexed evidence differs from its authoritative source; rebuild the index")
            resolved.append({**deepcopy(hit), **citation})
        return resolved
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise CitationError("Citation verification failed; no partial result was published") from None
