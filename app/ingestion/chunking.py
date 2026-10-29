"""Rebuildable section and fault-row chunks from Docling's reading tree."""

from app.ingestion.fault_codes import extract_fault_codes


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

    Sections have no arbitrary size cutoff. Tables interrupt prose and remain
    separate across table/page boundaries; no continuation text is guessed.
    """
    codes = {code["cell_ref"]: code for code in extract_fault_codes(document)}
    chunks = []
    headings = []
    pending = []

    def emit(chunk):
        section = [item["text"] for item in headings]
        chunks.append({
            **chunk, "document_key": document_key, "section": section,
            "heading_refs": [item["self_ref"] for item in headings],
            "text": "\n".join([*section, chunk["text"]]),
        })

    def flush():
        parts = [_item_text(item) for item in pending if item.get("text", "").strip()]
        if parts:
            emit({"chunk_type": "section", "source_refs": [item["self_ref"] for item in pending],
                  "text": "\n".join(parts)})
        pending.clear()

    for item in _walk(document, document.get("body", {})):
        label = item["label"]
        if label in {"page_header", "page_footer"}:
            continue
        if label == "section_header" and item["text"].strip().rstrip("!！:：") not in {"警告", "注意", "危险"}:
            flush()
            while headings and headings[-1].get("level", 1) >= item.get("level", 1):
                headings.pop()
            headings.append(item)
        elif label == "table":
            flush()
            for chunk in _table_chunks(item, codes):
                emit(chunk)
        elif "text" in item or label == "picture":
            pending.append(item)
    flush()
    return chunks
