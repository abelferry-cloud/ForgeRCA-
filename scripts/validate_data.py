"""Validate the seed corpus, provenance and evaluation separation offline."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CORPUS_FILES = {
    "knowledge_note": "data/corpus/knowledge.jsonl",
    "work_order": "data/corpus/work_orders.jsonl",
    "alarm": "data/corpus/alarms.jsonl",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.utcoffset() is not None, f"Timezone required: {value}")
    return result


def unique(records, label):
    result = {}
    for record in records:
        key = record["id"]
        require(isinstance(key, str) and key, f"Invalid {label} ID")
        require(key not in result, f"Duplicate {label} ID: {key}")
        result[key] = record
    return result


def load_data(root=ROOT):
    def read_json(path):
        return json.loads((root / path).read_text(encoding="utf-8"))

    def read_jsonl(path):
        return [json.loads(line) for line in (root / path).read_text(encoding="utf-8").splitlines() if line.strip()]

    return {
        "sources": read_json("data/sources/manifest.json")["sources"],
        "corpus": {kind: read_jsonl(path) for kind, path in CORPUS_FILES.items()},
        "evaluations": {split: read_jsonl(f"data/evaluation/{split}.jsonl") for split in ("dev", "demo")},
        "graph": read_json("data/graph/reference.json"),
    }


def validate(data):
    sources = unique(data["sources"], "source")
    for source in sources.values():
        require(re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), "Invalid source SHA-256")
        require(source["bytes"] > 0 and source["pages"] > 0, "Invalid source dimensions")
        require(source["redistribution"] == "not_verified", "Review source redistribution changes explicitly")
        require(source["verification"] == "downloaded_hash_and_text_checked", "Unverified source")
    records = [record for group in data["corpus"].values() for record in group]
    evidence = unique(records, "evidence")
    for kind, group in data["corpus"].items():
        require(group, f"Empty corpus: {kind}")
        for record in group:
            rid = record["id"]
            require(record["kind"] == kind, f"Wrong kind: {rid}")
            require(isinstance(record["synthetic"], bool), f"Synthetic flag required: {rid}")
            require(record["text"].strip() and record["model"], f"Empty text/model: {rid}")
            timestamp(record["available_at"])
            locator = record["locator"]
            if kind == "knowledge_note" and not record["synthetic"]:
                require(locator["source_id"] in sources, f"Unknown source: {rid}")
                source = sources[locator["source_id"]]
                require(1 <= locator["pdf_page"] <= source["pages"], f"Invalid PDF page: {rid}")
                require(locator["pdf_page"] in source["verified_pdf_pages"], f"Unverified PDF page: {rid}")
                require(locator["printed_page"] and locator["section"], f"Incomplete locator: {rid}")
                require(record["document_revision"] == source["revision"], f"Revision mismatch: {rid}")
                require(record["firmware_scope"] == source["firmware_scope"], f"Firmware scope mismatch: {rid}")
            else:
                require(record["synthetic"], f"Seed event must be synthetic: {rid}")
                require(locator == {"file": CORPUS_FILES[kind], "record_id": rid}, f"Invalid local locator: {rid}")

    work_orders = unique(data["corpus"]["work_order"], "work order")
    for order in work_orders.values():
        require(order["asset_id"].startswith("SYN-"), f"Not a synthetic asset: {order['id']}")
        require(timestamp(order["opened_at"]) <= timestamp(order["closed_at"]), "Invalid work-order interval")
        require(timestamp(order["available_at"]) == timestamp(order["closed_at"]), "Work order available before closure")
        require(order["observations"] and order["action"] and order["outcome"], "Incomplete work order")
    for alarm in data["corpus"]["alarm"]:
        require(alarm["work_order_id"] in work_orders, "Unknown alarm work order")
        order = work_orders[alarm["work_order_id"]]
        for key in ("asset_id", "model", "alarm_code", "incident_group", "firmware_version"):
            require(alarm[key] == order[key], f"Alarm/work-order mismatch: {alarm['id']} {key}")
        require(timestamp(order["opened_at"]) <= timestamp(alarm["occurred_at"]) <= timestamp(order["closed_at"]), "Alarm outside work-order interval")
        require(timestamp(alarm["available_at"]) == timestamp(alarm["occurred_at"]), "Alarm availability mismatch")

    graph = data["graph"]
    require(graph["purpose"] == "extraction_reference_not_runtime_graph", "Reference graph purpose changed")
    nodes = unique(graph["nodes"], "node")
    edges = unique(graph["edges"], "edge")
    cause_ids = {key for key, node in nodes.items() if node["type"] == "Cause"}
    edge_types = {"HAS_FAULT_CODE": ("EquipmentModel", "FaultCode"), "MAY_BE_CAUSED_BY": ("FaultCode", "Cause")}
    for edge in edges.values():
        require(edge["from"] in nodes and edge["to"] in nodes, "Dangling graph endpoint")
        require(edge["relation"] in edge_types, "Unknown relation type")
        require((nodes[edge["from"]]["type"], nodes[edge["to"]]["type"]) == edge_types[edge["relation"]], "Invalid relation endpoints")
        require(edge["evidence_id"] in evidence, "Dangling graph evidence")
        support = evidence[edge["evidence_id"]]
        require(edge["synthetic"] == support["synthetic"], "Graph provenance mismatch")
        expected_basis = "synthetic_history" if support["synthetic"] else "manufacturer_note"
        require(edge["basis"] == expected_basis, "Graph basis mismatch")
        fault = nodes[edge["to"] if edge["relation"] == "HAS_FAULT_CODE" else edge["from"]]
        require(fault["model"] == support["model"] and fault["label"] == support["alarm_code"], "Graph fault scope mismatch")
    for order in work_orders.values():
        require(order["confirmed_cause"] in cause_ids, "Unknown historical cause")

    questions = unique([q for group in data["evaluations"].values() for q in group], "question")
    groups = {}
    for split, group in data["evaluations"].items():
        require(group, f"Empty evaluation split: {split}")
        for question in group:
            qid = question["id"]
            require(question["split"] == split, f"Split mismatch: {qid}")
            require(question["synthetic"] is True, f"Question synthetic flag: {qid}")
            require(question["review_status"] == "agent_checked_pending_human", f"Review status requires explicit update: {qid}")
            require(question["query"].strip() and question["rationale"].strip(), f"Empty question/rationale: {qid}")
            incident = question["incident_group"]
            require(incident not in groups or groups[incident] == split, "Incident leaks across splits")
            groups[incident] = split
            require(not any(r.get("incident_group") == incident for r in records), "Target incident leaked into corpus")
            status = question["expected_status"]
            require(status in ("supported", "insufficient", "out_of_scope"), f"Invalid status: {qid}")
            causes = question["acceptable_cause_ids"]
            gold = question["gold_evidence_ids"]
            require(len(gold) == len(set(gold)), f"Duplicate gold evidence: {qid}")
            require(set(causes) <= cause_ids, f"Unknown expected cause: {qid}")
            require(bool(causes) == (status == "supported"), f"Cause/status mismatch: {qid}")
            if status == "supported":
                require(gold, f"Supported question without evidence: {qid}")
            else:
                require(question["required_checks"], f"Missing follow-up checks: {qid}")
            as_of = timestamp(question["as_of"])
            for eid in gold:
                require(eid in evidence, f"Unknown gold evidence: {qid} {eid}")
                support = evidence[eid]
                require(support["model"] == question["model"], f"Wrong-model gold evidence: {qid}")
                require(timestamp(support["available_at"]) <= as_of, f"Future evidence: {qid} {eid}")
                scope = support.get("firmware_scope") or support.get("firmware_version")
                if status == "supported" and scope:
                    require(question["firmware_version"] == scope, f"Unsupported firmware: {qid}")
    return {"sources": len(sources), "evidence": len(evidence), "questions": len(questions), "graph_nodes": len(nodes), "graph_edges": len(edges)}


def check_raw(sources, root=ROOT):
    for source in sources:
        path = (root / source["local_path"]).resolve()
        require(path.is_relative_to((root / "data/raw/abb").resolve()), "Unsafe raw path")
        require(path.is_file(), f"Missing PDF; run scripts/download_sources.py: {path.name}")
        require(path.stat().st_size == source["bytes"], f"PDF size mismatch: {path.name}")
        with path.open("rb") as stream:
            require(stream.read(5) == b"%PDF-", f"Invalid PDF header: {path.name}")
            stream.seek(0)
            require(hashlib.file_digest(stream, "sha256").hexdigest() == source["sha256"], f"PDF hash mismatch: {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-raw", action="store_true", help="Also verify the local, ignored PDFs")
    args = parser.parse_args()
    try:
        data = load_data()
        counts = validate(data)
        if args.check_raw:
            check_raw(data["sources"])
        print("OK: " + json.dumps(counts, ensure_ascii=False))
        print("Raw PDFs: verified" if args.check_raw else "Raw PDFs: not checked (offline corpus validation only)")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"Validation failed: {error}") from error
