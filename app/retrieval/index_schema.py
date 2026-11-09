"""Pinned index shape and record contracts; no corpus reads or model inference."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from app.schemas.document import FIRMWARE_PATTERN, parse_key

ROOT = Path(__file__).resolve().parents[2]


def load_mapping():
    lock = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))
    entry = lock["opensearch_mapping"]
    raw = (ROOT / entry["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError("OpenSearch mapping fingerprint mismatch")
    return json.loads(raw)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_index_metadata(record, mapping):
    """Validate provenance fields before spending tokens on vector generation."""
    fields = set(mapping["mappings"]["properties"]) - {"embedding"}
    _require(isinstance(record, dict) and set(record) == set(fields), "Unexpected or missing index fields")
    for field in ("evidence_id", "text"):
        _require(_text(record[field]), f"Invalid {field}")
    for field in ("model", "alarm_code"):
        values = record[field]
        _require(isinstance(values, list) and all(_text(item) for item in values), f"Invalid {field}")
        _require(len(values) == len(set(values)), f"Duplicate {field}")
    _require(bool(record["model"]), "At least one model is required")
    _require(type(record["synthetic"]) is bool, "synthetic must be an explicit boolean")
    try:
        available = datetime.fromisoformat(record["available_at"])
        _require(available.utcoffset() is not None, "available_at requires a timezone")
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid available_at; use an explicit timezone") from error
    kind = record["record_kind"]
    _require(kind in ("manual_chunk", "knowledge_note", "work_order", "alarm"), "Invalid record_kind")
    for field in ("firmware_scope", "firmware_version"):
        value = record[field]
        _require(value is None or (isinstance(value, str) and re.fullmatch(FIRMWARE_PATTERN, value)),
                 f"Invalid {field}")
    if kind in ("manual_chunk", "knowledge_note"):
        _require(record["firmware_version"] is None, "Documents use firmware_scope")
        state = "unrestricted" if record["firmware_scope"] is None else "known"
        _require(_text(record["document_revision"]), "Document revision is required")
        _require(_text(record["source_id"]) if not record["synthetic"] else record["source_id"] is None,
                 "Source identity must distinguish manufacturer references from synthetic notes")
    else:
        _require(record["firmware_scope"] is None, "Events use firmware_version")
        state = "unknown" if record["firmware_version"] is None else "known"
        _require(record["document_revision"] is None and record["source_id"] is None,
                 "Events must not claim a manufacturer document revision")
    _require(record["firmware_state"] == state, "firmware_state does not match the record's firmware semantics")
    if kind == "manual_chunk":
        key = parse_key(record["document_key"])
        _require(not record["synthetic"] and (key.source_id, key.revision) ==
                 (record["source_id"], record["document_revision"]), "Chunk parent identity mismatch")
        _require(re.fullmatch(r"ev1:[0-9a-f]{64}", record["evidence_id"]), "Invalid physical evidence ID")
        _require(record["chunk_type"] in ("section", "table", "table_rows", "fault_rows"), "Invalid chunk_type")
    else:
        _require(record["document_key"] is None and record["chunk_type"] is None,
                 "Only a parsed manufacturer chunk has a parent document key and chunk type")


def validate_index_record(record, mapping):
    """Validate record shape, not source authorization or the vector's model identity."""
    fields = mapping["mappings"]["properties"]
    _require(isinstance(record, dict) and set(record) == set(fields), "Unexpected or missing index fields")
    validate_index_metadata({key: value for key, value in record.items() if key != "embedding"}, mapping)
    vector = record["embedding"]
    dimension = fields["embedding"]["dimension"]
    _require(isinstance(vector, list) and len(vector) == dimension, "Invalid embedding dimension")
    _require(all(type(value) in (int, float) and abs(value) <= 3.4028234663852886e38 for value in vector),
             "Embedding must contain finite float32 numbers")
    _require(any(value != 0 for value in vector), "Cosine embedding must be nonzero")


def index_record_id(record):
    """Namespace validated evidence by kind and parent, including the document revision."""
    identity = [record["record_kind"], record["document_key"], record["evidence_id"]]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
