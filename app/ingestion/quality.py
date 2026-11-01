"""Reject explicit text corruption and inconsistent logical table cells."""

import re

# Tabs and line endings are valid layout; these markers are not repaired.
BAD_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f\ufffd]")


def _check_text(text, ref):
    if BAD_CHARACTER.search(text):
        raise ValueError(f"Invalid text character at {ref}")


def validate_document_quality(document: dict) -> None:
    """Check explicit defects, without claiming semantic accuracy or repairing text.

    Empty pages and unoccupied table slots are valid. Ambiguous cell pages and
    missing physical provenance are handled separately by evidence identity.
    """
    for index, item in enumerate(document.get("texts", [])):
        _check_text(item["text"], f"#/texts/{index}")
    for table_index, table in enumerate(document.get("tables", [])):
        ref = f"#/tables/{table_index}"
        data = table["data"]
        sizes = (data.get("num_rows"), data.get("num_cols"))
        if any(type(size) is not int or size < 0 for size in sizes):
            raise ValueError(f"Invalid table dimensions at {ref}")
        rectangles = []
        for index, cell in enumerate(data["table_cells"]):
            cell_ref = f"{ref}/data/table_cells/{index}"
            _check_text(cell["text"], cell_ref)
            bounds = []
            for axis, size in zip(("row", "col"), sizes, strict=True):
                start, end = (cell.get(f"{edge}_{axis}_offset_idx") for edge in ("start", "end"))
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= size:
                    raise ValueError(f"Invalid table cell bounds at {cell_ref}")
                span = cell.get(f"{axis}_span", end - start)
                if type(span) is not int or span != end - start:
                    raise ValueError(f"Invalid table cell span at {cell_ref}")
                bounds.extend((start, end))
            row_start, row_end, col_start, col_end = bounds
            for old_row_start, old_row_end, old_col_start, old_col_end in rectangles:
                if (row_start < old_row_end and row_end > old_row_start
                        and col_start < old_col_end and col_end > old_col_start):
                    raise ValueError(f"Overlapping table cells at {cell_ref}")
            rectangles.append(bounds)
