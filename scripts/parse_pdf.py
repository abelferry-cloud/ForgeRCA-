"""Parse a pinned ABB PDF page range into the ignored processed-data directory."""

import argparse
import json
from pathlib import Path

from app.ingestion.pdf import parse_pdf
from scripts.download_sources import verify_file

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    sources = json.loads((ROOT / "data/sources/manifest.json").read_text(encoding="utf-8"))["sources"]
    sources = {source["id"]: source for source in sources}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=sources)
    parser.add_argument("--pages", required=True, type=int, nargs=2, metavar=("START", "END"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    source = sources[args.source]
    start, end = args.pages
    if not 1 <= start <= end <= source["pages"]:
        parser.error(f"Pages must satisfy 1 <= start <= end <= {source['pages']}")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "data/processed").resolve()) or output.suffix != ".json":
        parser.error("Output must be a .json file inside data/processed/")
    if output.exists():
        parser.error("Output already exists; choose a new filename")
    path = ROOT / source["local_path"]
    verify_file(path, source)
    result = parse_pdf(path, (start, end))
    result["source"] = {"source_id": source["id"], "sha256": source["sha256"]}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    print(f"Parsed {source['id']} pages {start}-{end}: {output}")


if __name__ == "__main__":
    main()
