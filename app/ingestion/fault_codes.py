"""Recognize primary codes in explicitly labelled ABB fault-table columns."""

from dataclasses import asdict

from app.schemas.fault_code import FaultCode


def _header_text(cell):
    return "".join(cell["text"].split()).lower()


def extract_fault_codes(document: dict) -> list[dict]:
    """Add no guesses from prose, auxiliary columns or unlabelled continuations.

    ``cell_ref`` is a pointer into this Docling JSON, not a stable evidence ID.
    Nonmatching cells remain available in the unchanged source document.
    """
    found = []
    for table in document.get("tables", []):
        cells = table["data"]["table_cells"]
        headers = [
            cell for cell in cells
            if cell["column_header"] and _header_text(cell) in {"编码（hex）", "编码(hex)"}
            and cell["end_col_offset_idx"] == cell["start_col_offset_idx"] + 1
            and any(
                other["column_header"] and _header_text(other) == "故障/辅助代码"
                and other["start_row_offset_idx"] == cell["start_row_offset_idx"]
                and other["start_col_offset_idx"] == cell["end_col_offset_idx"]
                for other in cells
            )
        ]
        for index, cell in enumerate(cells):
            if cell["column_header"] or not any(
                cell["start_col_offset_idx"] == header["start_col_offset_idx"]
                and cell["end_col_offset_idx"] == header["end_col_offset_idx"]
                and cell["start_row_offset_idx"] >= header["end_row_offset_idx"]
                for header in headers
            ):
                continue
            try:
                code = FaultCode.from_raw(cell["text"])
            except ValueError:
                continue
            found.append({**asdict(code), "cell_ref": f"{table['self_ref']}/data/table_cells/{index}"})
    return found
