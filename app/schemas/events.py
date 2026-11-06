"""Validate the two explicit synthetic history files without reading gold labels."""

import re
from datetime import datetime

EVENT_FILES = {"work_order": "data/corpus/work_orders.jsonl", "alarm": "data/corpus/alarms.jsonl"}
COMMON = {"id", "kind", "model", "firmware_version", "synthetic", "asset_id", "incident_group",
          "alarm_code", "available_at", "text", "locator"}
FIELDS = {
    "work_order": COMMON | {"opened_at", "closed_at", "observations", "confirmed_cause", "action", "outcome"},
    "alarm": COMMON | {"work_order_id", "occurred_at"},
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def event_time(value):
    result = datetime.fromisoformat(value)
    _require(result.utcoffset() is not None, "Event timestamps require a timezone")
    return result


def validate_seed_events(corpus):
    """Return work orders by ID; preserve the seed's explicit availability rules."""
    seen, assets, orders = set(), {}, {}
    try:
        _require(set(corpus) == set(EVENT_FILES), "Only the two seed event groups are allowed")
        for kind, path in EVENT_FILES.items():
            _require(isinstance(corpus[kind], list) and corpus[kind], f"Empty seed file: {kind}")
            for record in corpus[kind]:
                _require(set(record) == FIELDS[kind], f"Unexpected or missing fields: {kind}")
                rid = record["id"]
                _require(isinstance(rid, str) and rid.strip() and rid not in seen, "Invalid/duplicate event ID")
                seen.add(rid)
                _require(record["kind"] == kind and record["synthetic"] is True, "Seed event must be synthetic")
                for field in ("asset_id", "model", "incident_group", "alarm_code", "text"):
                    _require(isinstance(record[field], str) and record[field].strip(), f"Empty event field: {field}")
                _require(record["asset_id"].startswith("SYN-"), "Not a synthetic asset")
                identity = (record["model"], record["synthetic"])
                _require(assets.setdefault(record["asset_id"], identity) == identity, "Asset identity mismatch")
                version = record["firmware_version"]
                _require(version is None or (isinstance(version, str)
                                             and re.fullmatch(r"ASCKX [0-9]+\.[0-9]+", version)),
                         "Invalid event firmware")
                _require(record["locator"] == {"file": path, "record_id": rid}, "Invalid local event locator")
                available = event_time(record["available_at"])
                if kind == "work_order":
                    _require(event_time(record["opened_at"]) <= event_time(record["closed_at"]) == available,
                             "Invalid work-order interval or availability")
                    observations = record["observations"]
                    _require(isinstance(observations, list) and observations
                             and all(isinstance(item, str) and item.strip() for item in observations),
                             "Incomplete observations")
                    for field in ("confirmed_cause", "action", "outcome"):
                        _require(isinstance(record[field], str) and record[field].strip(), "Incomplete work order")
                    orders[rid] = record
                else:
                    _require(record["work_order_id"] in orders, "Unknown alarm work order")
                    order = orders[record["work_order_id"]]
                    for field in ("asset_id", "model", "alarm_code", "incident_group", "firmware_version"):
                        _require(record[field] == order[field], f"Alarm/work-order mismatch: {field}")
                    occurred = event_time(record["occurred_at"])
                    _require(event_time(order["opened_at"]) <= occurred <= event_time(order["closed_at"]),
                             "Alarm outside work-order interval")
                    _require(occurred == available, "Alarm availability mismatch")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete synthetic event records") from error
    return orders
