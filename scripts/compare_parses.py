"""Compare two local parse snapshots and write an ignored, text-free change report."""

import argparse
import hashlib
import json
from pathlib import Path

from app.ingestion.incremental import compare_parses

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    paths = [args.before.resolve(), args.after.resolve()]
    output = args.output.resolve()
    if any(not path.is_relative_to((ROOT / "data/processed").resolve()) or path.suffix != ".json" for path in paths):
        parser.error("Inputs must be .json files inside data/processed/")
    if not output.is_relative_to((ROOT / "artifacts").resolve()) or output.suffix != ".json":
        parser.error("Output must be a .json file inside artifacts/")
    if output in paths or output.exists():
        parser.error("Output already exists or aliases an input; choose a new filename")
    snapshots, inputs = [], {}
    for label, path in zip(("before", "after"), paths, strict=True):
        raw = path.read_bytes()
        snapshots.append(json.loads(raw))
        inputs[label] = {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
    report = {**compare_parses(*snapshots), "inputs": inputs}
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
    print(f"Compared: {len(report['added'])} added, {len(report['removed'])} removed, "
          f"{len(report['modified'])} modified, {report['unchanged_count']} unchanged: {output}")


if __name__ == "__main__":
    main()
