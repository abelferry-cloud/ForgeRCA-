"""Rebuildable section and fault-row chunks from Docling's reading tree."""

import re

from app.ingestion.fault_codes import extract_fault_codes

SAFETY_LABELS = {"警告": "warning", "注意": "caution", "危险": "danger"}
SAFETY_SIGNAL = re.compile(r"^\s*(警告|注意|危险)(?=$|[!！:：\s])", re.MULTILINE)


def _safety_labels(item):
    texts = ([cell["text"] for cell in item["data"]["table_cells"]]
             if item["label"] == "table" else [item.get("text", "")])
    return {SAFETY_LABELS[match] for value in texts for match in SAFETY_SIGNAL.findall(value)}


def _resolve(document, ref):
    node = document
    for part in ref.removeprefix("#/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _walk(document, node):
    for child in node.get("children", []):
        item = _resolve(document, child["$ref"])
        yield item
        if item["label"] != "table":
            yield from _walk(document, item)


def _item_text(item):
    value = item.get("text", "")
    marker = item.get("marker", "")
    if marker and not value.lstrip().startswith(marker):
        return f"{marker} {value}"
    return value


def _table_text(indexed_cells, start, num_cols):
    rows = {}
    for _, cell in indexed_cells:
        # Keep spanning cells once in each intersecting chunk, at its first row.
        row = cell["start_row_offset_idx"] if cell["column_header"] else max(start, cell["start_row_offset_idx"])
        key = (not cell["column_header"], row)
        rows.setdefault(key, {})[cell["start_col_offset_idx"]] = cell["text"]
    return "\n".join("\t".join(rows[key].get(col, "") for col in range(num_cols)) for key in sorted(rows))


def _table_chunks(table, codes):
    data = table["data"]
    cells = data["table_cells"]
    if not cells:
        return
    prefix = f"{table['self_ref']}/data/table_cells/"
    known = {i: codes[prefix + str(i)] for i in range(len(cells)) if prefix + str(i) in codes}
    columns = {cells[i]["start_col_offset_idx"] for i in known}
    body = [(i, cell) for i, cell in enumerate(cells) if not cell["column_header"]]
    # Even an unrecognized nonempty primary-code cell starts a new group: its
    # causes must not silently inherit the preceding valid code.
    starts = sorted({cell["start_row_offset_idx"] for _, cell in body
                     if cell["start_col_offset_idx"] in columns
                     and cell["end_col_offset_idx"] == cell["start_col_offset_idx"] + 1
                     and cell["text"].strip()})
    if starts:
        starts = sorted({min(cell["start_row_offset_idx"] for _, cell in body), *starts})
    else:
        starts = [0]
    ends = starts[1:] + [data["num_rows"]]
    for start, end in zip(starts, ends, strict=True):
        selected = [(i, cell) for i, cell in enumerate(cells)
                    if cell["column_header"] or (cell["start_row_offset_idx"] < end
                                                 and cell["end_row_offset_idx"] > start)]
        group_codes = [code for i, code in known.items() if start <= cells[i]["start_row_offset_idx"] < end]
        yield {
            "chunk_type": "fault_rows" if group_codes else ("table_rows" if known else "table"),
            "table_ref": table["self_ref"], "row_range": [start, end],
            "source_refs": [prefix + str(i) for i, _ in selected],
            "fault_codes": group_codes,
            "text": _table_text(selected, start, data["num_cols"]),
        }


def chunk_document(document: dict, document_key: str) -> list[dict]:
    """Keep source references local; evidence.identify_chunk adds stable IDs.

    Sections have no arbitrary size cutoff. Explicit safety signals keep the
    whole section together, including tables; no continuation text is guessed.
    """
    codes = {code["cell_ref"]: code for code in extract_fault_codes(document)}
    chunks = []
    headings = []
    pending = []

    def emit(chunk, labels=()):
        section = [item["text"] for item in headings]
        chunks.append({
            **chunk, "document_key": document_key, "section": section,
            "heading_refs": [item["self_ref"] for item in headings],
            "text": "\n".join([*section, chunk["text"]]),
            "safety_labels": sorted(labels),
        })

    def emit_section(items, labels=()):
        parts, refs, table_codes = [], [], []
        has_table = False
        for item in items:
            if item["label"] == "table":
                has_table = True
                data = item["data"]
                parts.append(_table_text(list(enumerate(data["table_cells"])), 0, data["num_cols"]))
                cell_refs = [f"{item['self_ref']}/data/table_cells/{i}" for i in range(len(data["table_cells"]))]
                refs.extend(cell_refs)
                table_codes.extend(codes[ref] for ref in cell_refs if ref in codes)
            else:
                refs.append(item["self_ref"])
                if item.get("text", "").strip():
                    parts.append(_item_text(item))
        if parts:
            chunk = {"chunk_type": "section", "source_refs": refs, "text": "\n".join(parts)}
            if has_table:
                chunk["fault_codes"] = table_codes
            emit(chunk, labels)

    def flush():
        labels = {label for item in pending for label in _safety_labels(item)}
        if labels:
            # Include conditions before a signal too, even across table boundaries.
            emit_section(pending, labels)
        else:
            prose = []
            for item in pending:
                if item["label"] == "table":
                    emit_section(prose)
                    prose.clear()
                    for chunk in _table_chunks(item, codes):
                        emit(chunk)
                else:
                    prose.append(item)
            emit_section(prose)
        pending.clear()

    for item in _walk(document, document.get("body", {})):
        label = item["label"]
        if label in {"page_header", "page_footer"}:
            continue
        if label == "section_header" and not _safety_labels(item):
            flush()
            while headings and headings[-1].get("level", 1) >= item.get("level", 1):
                headings.pop()
            headings.append(item)
        elif "text" in item or label in {"picture", "table"}:
            pending.append(item)
    flush()
    return chunks
