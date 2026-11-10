"""Build a fresh corpus index, retrieve evidence or generate a constrained answer."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.retrieval.citations import resolve_hits
from app.retrieval.corpus import load_file_records, load_manual_records
from app.retrieval.dense import SearchClient, SearchError, build_index, retrieve, sync_index

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Read the file allowlist and successfully imported PostgreSQL chunks")
    sync = commands.add_parser("sync", help="Synchronize authoritative sources into a new index, reusing vectors")
    sync.add_argument("--index", required=True)
    query = commands.add_parser("query", help="Search one concrete index returned by index")
    answer = commands.add_parser("answer", help="Search, verify citations and explain evidence-supported candidates")
    for command in (index, sync, query, answer):
        command.add_argument("--output", type=Path, required=True)
    for command in (query, answer):
        command.add_argument("--index", required=True)
        command.add_argument("--query", required=True)
        command.add_argument("--model", required=True)
        command.add_argument("--as-of", required=True)
        command.add_argument("--firmware-version")
        command.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.suffix != ".json" or output.exists():
        parser.error("Output must be a new .json file inside artifacts/")
    try:
        client = SearchClient()
        if args.command in ("index", "sync"):
            if args.command == "sync":
                client.check_index_name(args.index)
            records = load_file_records()
            from sqlalchemy.exc import SQLAlchemyError

            from app.db.connection import create_db_engine

            engine = None
            try:
                engine = create_db_engine()
                records += load_manual_records(engine)
            except SQLAlchemyError:
                raise SearchError("Database corpus read failed; check the connection and migrations") from None
            finally:
                if engine is not None:
                    engine.dispose()
            result = sync_index(client, args.index, records) if args.command == "sync" else build_index(client, records)
        else:
            result = retrieve(client, args.index, args.query, model=args.model, as_of=args.as_of,
                              firmware_version=args.firmware_version, top_k=args.top_k)
            if args.command == "answer":
                from app.generation import answer_question

                result.update(answer_question(args.query, result["hits"]))
            else:
                result["hits"] = resolve_hits(result["hits"])
        result["created_at"] = datetime.now(UTC).isoformat()
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
        print(f"Dense {args.command} completed: {result['index']}; report: {output}")
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Dense command failed; verify input, configuration and service status. No report published.\n")


if __name__ == "__main__":
    main()
