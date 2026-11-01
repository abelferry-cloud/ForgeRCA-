"""Compare chunk snapshots of one PDF and page range, without index writes."""

import hashlib
import json

from app.ingestion.evidence import identify_chunk
from app.schemas.document import parse_key


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _payload(chunk):
    # Local references may be renumbered on every parse. Logical row ranges and
    # rendered content remain meaningful, so they are compared independently.
    ignored = {"evidence_id", "evidence_locator", "source_refs", "heading_refs", "table_ref"}
    result = {key: value for key, value in chunk.items() if key not in ignored}
    if "fault_codes" in result:
        result["fault_codes"] = sorted(
            [{key: value for key, value in code.items() if key != "cell_ref"} for code in result["fault_codes"]],
            key=_canonical,
        )
    if "locations" in result:
        result["locations"] = sorted(result["locations"], key=_canonical)
    if result.get("table_row") is not None:
        result["table_row"] = {key: value for key, value in result["table_row"].items() if key != "table_ref"}
    return result


def _snapshot(result):
    if type(result.get("schema_version")) is not int or result["schema_version"] != 1:
        raise ValueError("Unsupported parse schema; provide a complete schema_version=1 result")
    source, parser, document = (result[key] for key in ("source", "parser", "document"))
    key = parse_key(source["document_key"])
    if (key.source_id, key.revision, key.sha256) != (source["source_id"], source["revision"], source["sha256"]):
        raise ValueError("Parsed source does not match its document key")
    pages = parser["page_range"]
    if (not isinstance(pages, list) or len(pages) != 2 or any(type(page) is not int for page in pages)
            or not 1 <= pages[0] <= pages[1]):
        raise ValueError("Invalid parser page range")
    if (not isinstance(document["pages"], dict)
            or {str(page) for page in document["pages"]} != {str(page) for page in range(pages[0], pages[1] + 1)}):
        raise ValueError("Parsed document does not contain every declared page")
    if any(not isinstance(parser.get(field), dict) or not parser[field] for field in ("packages", "options", "models")):
        raise ValueError("Parser versions, options and model pins are required")
    if not isinstance(result["chunks"], list):
        raise ValueError("Comparison requires a chunks list")
    chunks = {}
    for chunk in result["chunks"]:
        if (chunk["document_key"] != source["document_key"] or not isinstance(chunk["text"], str)
                or not isinstance(chunk["section"], list) or not isinstance(chunk["chunk_type"], str)):
            raise ValueError("Invalid chunk content or parent document")
        computed = identify_chunk(document, chunk)
        evidence_id = chunk["evidence_id"]
        if (evidence_id != computed["evidence_id"]
                or _canonical(chunk["evidence_locator"]) != _canonical(computed["evidence_locator"])):
            raise ValueError("Evidence ID or locator does not match physical provenance")
        if evidence_id in chunks:
            raise ValueError(f"Duplicate evidence ID: {evidence_id}")
        chunks[evidence_id] = _payload(chunk)
    return chunks, {key: value for key, value in parser.items() if key != "page_range"}


def _changed_fields(before, after):
    return sorted(key for key in before.keys() | after.keys()
                  if key not in before or key not in after or _canonical(before[key]) != _canonical(after[key]))


def compare_parses(before: dict, after: dict) -> dict:
    """Report deterministic additions, removals and changed fields at shared anchors.

    Legacy results without evidence IDs, incomplete snapshots and duplicate IDs
    fail rather than being interpreted as empty snapshots or silently collapsed.
    """
    try:
        old, old_parser = _snapshot(before)
        new, new_parser = _snapshot(after)
        if before["source"]["document_key"] != after["source"]["document_key"]:
            raise ValueError("Comparison requires the same parent document and PDF digest")
        if before["parser"]["page_range"] != after["parser"]["page_range"]:
            raise ValueError("Comparison requires the same physical page range")
        modified = []
        shared = old.keys() & new.keys()
        for evidence_id in sorted(shared):
            fields = _changed_fields(old[evidence_id], new[evidence_id])
            if fields:
                modified.append({"evidence_id": evidence_id, "fields": fields})
        return {
            "comparison_version": 1,
            "document_key": before["source"]["document_key"],
            "page_range": list(before["parser"]["page_range"]),
            "parser_before": old_parser, "parser_after": new_parser,
            "parser_fingerprint_before": _fingerprint(old_parser),
            "parser_fingerprint_after": _fingerprint(new_parser),
            "parser_changed": _canonical(old_parser) != _canonical(new_parser),
            "source_metadata_changed": _changed_fields(before["source"], after["source"]),
            "added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "modified": modified, "unchanged_count": len(shared) - len(modified),
        }
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete parsed result; reparse legacy outputs with evidence IDs") from error
