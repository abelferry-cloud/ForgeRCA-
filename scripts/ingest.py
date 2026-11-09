"""Import a verified snapshot or seed events, explicitly replace pages or retire a manual."""

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.ingestion.chunking import chunk_document
from app.ingestion.evidence import identify_chunk
from app.ingestion.incremental import validate_snapshot
from app.ingestion.metadata import locate_chunk
from app.ingestion.quality import validate_document_quality
from app.schemas.document import document_keys, parse_key
from app.schemas.events import EVENT_FILES, validate_seed_events
from scripts.corpus_allowlist import assert_indexable
from scripts.download_sources import verify_file

ROOT = Path(__file__).resolve().parents[1]


def load_snapshot(path, root=ROOT):
    root = Path(root).resolve()
    path = (root / path).resolve()
    if not path.is_relative_to((root / "data/processed").resolve()) or path.suffix != ".json":
        raise ValueError("Input must be one .json file inside data/processed/")
    raw = path.read_bytes()
    result = json.loads(raw)
    try:
        validate_snapshot(result)
        sources = json.loads((root / "data/sources/manifest.json").read_text(encoding="utf-8"))["sources"]
        keys = document_keys(sources)
        key = keys[result["source"]["document_key"]]
        source = next(source for source in sources
                      if source["id"] == key.source_id and source["revision"] == key.revision)
        expected_source = {"document_key": key.value, **asdict(key)}
        if "printed_page_map" in source:
            expected_source["printed_page_map"] = source["printed_page_map"]
        if result["source"] != expected_source:
            raise ValueError("Snapshot source metadata differs from the registered manifest")
        start, end = result["parser"]["page_range"]
        if not 1 <= start <= end <= source["pages"]:
            raise ValueError("Snapshot page range exceeds the source")
        models = source["models"]
        if not isinstance(models, list) or not models or any(not isinstance(m, str) or not m.strip() for m in models):
            raise ValueError("Source requires explicit models")
        pdf = (root / source["local_path"]).resolve()
        if not pdf.is_relative_to((root / "data/raw/abb").resolve()):
            raise ValueError("Registered PDF must stay inside data/raw/abb/")
        verify_file(pdf, source)
        validate_document_quality(result["document"])
        rebuilt = [locate_chunk(identify_chunk(result["document"], chunk), source)
                   for chunk in chunk_document(result["document"], key.value)]
        if sorted(rebuilt, key=lambda c: c["evidence_id"]) != sorted(result["chunks"], key=lambda c: c["evidence_id"]):
            raise ValueError("Chunks differ from the current parser contract; reparse the snapshot")
        chunks = [{**{field: chunk[field] for field in (
            "document_key", "evidence_id", "chunk_type", "text", "evidence_locator", "locations",
            "section", "source_refs", "heading_refs", "table_row", "safety_labels",
        )}, "fault_codes": chunk.get("fault_codes", [])} for chunk in rebuilt]
        doc = {"document_key": key.value, **asdict(key), "models": models, "source_metadata": source,
               "accessed_at": date.fromisoformat(key.accessed_at)}
        return {"document": doc, "chunks": chunks, "parser": result["parser"],
                "input_path": path.relative_to(root).as_posix(), "input_sha256": hashlib.sha256(raw).hexdigest()}
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise ValueError("Incomplete or unregistered parse snapshot") from error


def load_seed_events(root=ROOT):
    corpus = {}
    for kind, path in EVENT_FILES.items():
        relative = assert_indexable(path, root)
        corpus[kind] = [json.loads(line) for line in (root / relative).read_text(encoding="utf-8").splitlines()
                        if line.strip()]
    validate_seed_events(corpus)
    return corpus


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--snapshot", type=Path)
    mode.add_argument("--seed-events", action="store_true")
    mode.add_argument("--retire-document", metavar="DOCUMENT_KEY")
    parser.add_argument("--replace", action="store_true", help="Explicitly replace the verified snapshot's page range")
    args = parser.parse_args(argv)
    if args.replace and not args.snapshot:
        parser.error("--replace requires --snapshot")
    try:
        if args.retire_document:
            parse_key(args.retire_document)
        else:
            prepared = load_snapshot(args.snapshot) if args.snapshot else load_seed_events()
        from sqlalchemy.exc import SQLAlchemyError

        from app.db.connection import create_db_engine
        from app.ingestion.importer import import_seed_events, import_snapshot, retire_document

        engine = create_db_engine()
        try:
            if args.retire_document:
                report = retire_document(engine, args.retire_document)
            elif args.snapshot:
                report = import_snapshot(engine, prepared, replace=args.replace)
            else:
                report = import_seed_events(engine, prepared)
        except SQLAlchemyError as error:
            # Driver diagnostics can contain parameters or rejected row text.
            raise ValueError("Database import failed; rolled back; check migration and connection") from error
        finally:
            engine.dispose()
        print(json.dumps(report, ensure_ascii=False))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Import failed: {error}\n")


if __name__ == "__main__":
    main()
