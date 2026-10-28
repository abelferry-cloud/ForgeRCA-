"""Versioned evidence IDs from physical PDF locations, never parser indices."""

import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal

from app.schemas.document import parse_key


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("Evidence coordinates must be finite numbers")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Evidence coordinates must be finite numbers")
    return result


def _page_number(value):
    if type(value) is not int or value < 1:
        raise ValueError("Evidence requires a positive physical page number")
    return value


def _box(document, page_no, box):
    pages = document["pages"]
    page = pages.get(str(page_no), pages.get(page_no))
    if page is None or page["page_no"] != page_no:
        raise ValueError("Evidence page is missing from the parsed document")
    width, height = (_number(page["size"][key]) for key in ("width", "height"))
    left, top, right, bottom = (_number(box[key]) for key in ("l", "t", "r", "b"))
    if box["coord_origin"] == "BOTTOMLEFT":
        top, bottom = height - top, height - bottom
    elif box["coord_origin"] != "TOPLEFT":
        raise ValueError("Unknown evidence coordinate origin")
    if not (width > 0 and height > 0 and 0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Evidence box must have positive area inside its page")
    values = [int((value * 1000).to_integral_value(rounding=ROUND_HALF_UP))
              for value in (left, top, right, bottom)]
    if values[0] >= values[2] or values[1] >= values[3]:
        raise ValueError("Evidence box is smaller than the coordinate precision")
    return values


def _provenance(node):
    values = node.get("prov")
    if not isinstance(values, list) or not values:
        raise ValueError("Evidence requires nonempty provenance")
    return values


def _elements(document, ref):
    match = re.fullmatch(r"#/(texts|pictures)/([0-9]+)", ref)
    if match:
        collection, index = match.groups()
        node = document[collection][int(index)]
        for item in _provenance(node):
            page = _page_number(item["page_no"])
            element = {"kind": "text" if collection == "texts" else "picture", "pdf_page": page,
                       "bbox_milli": _box(document, page, item["bbox"])}
            if collection == "texts":
                span = item["charspan"]
                if (not isinstance(span, (list, tuple)) or len(span) != 2
                        or any(type(value) is not int for value in span) or not 0 <= span[0] <= span[1]):
                    raise ValueError("Invalid evidence character span")
                element["charspan"] = list(span)
            yield element
        return
    match = re.fullmatch(r"#/tables/([0-9]+)/data/table_cells/([0-9]+)", ref)
    if not match:
        raise ValueError(f"Unsupported evidence reference: {ref}")
    table_index, cell_index = map(int, match.groups())
    table = document["tables"][table_index]
    pages = {_page_number(item["page_no"]) for item in _provenance(table)}
    if len(pages) != 1:
        raise ValueError("Table cell evidence requires an unambiguous single physical page")
    page = pages.pop()
    cell = table["data"]["table_cells"][cell_index]
    yield {"kind": "table_cell", "pdf_page": page, "bbox_milli": _box(document, page, cell["bbox"])}


def identify_chunk(document: dict, chunk: dict) -> dict:
    """Return a copy with a stable ID and its canonical, inspectable locator.

    Inherited headings, rendered text, row numbers and reference strings are
    excluded. Equal physical coverage produces equal IDs even after reordering.
    """
    key = parse_key(chunk.get("document_key"))
    refs = chunk.get("source_refs")
    if not isinstance(refs, list) or not refs:
        raise ValueError("A chunk needs source references for evidence identity")
    try:
        elements = {_canonical(element): element for ref in refs for element in _elements(document, ref)}
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Incomplete or unresolvable evidence location") from error
    locator = {"version": 1, "source_id": key.source_id, "sha256": key.sha256,
               "elements": [elements[value] for value in sorted(elements)]}
    digest = hashlib.sha256(_canonical(locator).encode("utf-8")).hexdigest()
    return {**chunk, "evidence_id": f"ev1:{digest}", "evidence_locator": locator}
