"""Display locations for identified chunks, separate from their stable identity."""

from app.schemas.document import DocumentKey, printed_page_labels


def locate_chunk(chunk: dict, source: dict) -> dict:
    """Preserve every physical page and the parent; unknown printed pages stay null."""
    key = DocumentKey.from_source(source)
    locator = chunk["evidence_locator"]
    if (chunk["document_key"] != key.value or locator["source_id"] != key.source_id
            or locator["sha256"] != key.sha256):
        raise ValueError("Chunk location must match its parent document")
    pages = {element["pdf_page"] for element in locator["elements"]}
    if not pages or any(type(page) is not int or not 1 <= page <= source["pages"] for page in pages):
        raise ValueError("Chunk location requires physical pages inside its source")
    labels = printed_page_labels(source)
    table_row = None
    if "table_ref" in chunk:
        table_row = {"table_ref": chunk["table_ref"], "row_range": list(chunk["row_range"])}
    return {
        **chunk,
        "locations": [{"pdf_page": page, "printed_page": labels.get(page)} for page in sorted(pages)],
        "table_row": table_row,
    }
