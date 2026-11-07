"""Send explicitly supplied text to the pinned embedding API; save results locally."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.retrieval.embedding import DenseEmbedder

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", action="append", required=True, help="Repeat for multiple explicit inputs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.suffix != ".json":
        parser.error("Output must be a .json file inside artifacts/")
    if output.exists():
        parser.error("Output already exists; choose a new filename")
    if any(not text.strip() for text in args.text):
        parser.error("Text inputs must not be blank")
    embedder = DenseEmbedder()
    result = embedder.encode(args.text)
    result["created_at"] = datetime.now(UTC).isoformat()
    result["configuration"] = embedder.configuration
    canonical = json.dumps(result["configuration"], sort_keys=True, separators=(",", ":"), allow_nan=False)
    result["configuration_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    result["text_sha256"] = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in args.text]
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    print(f"Embedded {len(result['vectors'])} texts at {result['configuration']['dimension']} dimensions: {output}")


if __name__ == "__main__":
    main()
