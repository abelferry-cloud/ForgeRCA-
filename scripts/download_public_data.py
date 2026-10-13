#!/usr/bin/env python3
"""Download optional public research datasets without mixing into the ABB corpus.

Uses only the Python standard library. All downloaded third-party files are
written to data/raw/public/, which is already ignored by the repository.

Examples:
    python scripts/download_public_data.py --list
    python scripts/download_public_data.py --dataset maintie-gold
    python scripts/download_public_data.py --dataset ai4i
    python scripts/download_public_data.py --dataset metropt3 --allow-large
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "sources" / "public-datasets.json"
DEFAULT_DIR = ROOT / "data" / "raw" / "public"
ALLOWED_HOSTS = {"raw.githubusercontent.com", "archive.ics.uci.edu"}
LIMITS = {
    "maintie-gold": 25 * 1024 * 1024,
    "maintie-silver": 125 * 1024 * 1024,
    "ai4i": 12 * 1024 * 1024,
    "metropt3": 350 * 1024 * 1024,
}
OUTPUT_NAMES = {
    "maintie-gold": "gold_release.json",
    "maintie-silver": "silver_release.json",
    "ai4i": "ai4i2020.csv",
    "metropt3": "metropt+3+dataset.zip",
}


def load_catalog(path: Path = CATALOG) -> dict[str, dict]:
    content = json.loads(path.read_text(encoding="utf-8"))
    return {item["key"]: item for item in content["datasets"]}


def ensure_allowlisted_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Refusing an unapproved source URL: {url}")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError(f"Refusing unusual URL authority: {url}")


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transfer(url: str, output: Path, max_bytes: int) -> int:
    """Write a remote response to output; fail safely if the payload is too large."""
    ensure_allowlisted_url(url)
    request = Request(url, headers={"User-Agent": "ForgeRCA-research-dataset-downloader/0.1"})
    size = 0
    with urlopen(request, timeout=45) as response, output.open("wb") as dest:
        final_url = response.geturl()
        ensure_allowlisted_url(final_url)
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > max_bytes:
                raise ValueError(f"Download exceeds safety limit: {max_bytes} bytes")
            dest.write(block)
    if size < 50:
        raise ValueError("Downloaded payload is unexpectedly small")
    return size


def validate_maintie(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("MaintIE JSON must be a non-empty list")
    for row in data:
        if not isinstance(row, dict) or not {"text", "tokens", "entities", "relations"} <= row.keys():
            raise ValueError("MaintIE item is missing required IE fields")
    return {"records": len(data)}


def extract_ai4i_csv(archive: Path, target: Path) -> dict:
    """Extract one expected file by reading its contents, never extract arbitrary ZIP paths."""
    with ZipFile(archive) as bundle:
        matches = [
            entry for entry in bundle.infolist()
            if Path(entry.filename).name.lower() == "ai4i2020.csv" and not entry.is_dir()
        ]
        if len(matches) != 1:
            raise ValueError("AI4I ZIP does not contain exactly one ai4i2020.csv")
        entry = matches[0]
        if entry.file_size > 5 * 1024 * 1024:
            raise ValueError("Uncompressed CSV is unexpectedly large")
        with bundle.open(entry) as source, target.open("wb") as dest:
            shutil.copyfileobj(source, dest)
    with target.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        header = next(reader, [])
    if "UDI" not in header or "Machine failure" not in header:
        raise ValueError("Unexpected AI4I CSV columns")
    return {"columns": header}


def download_dataset(
    key: str,
    entry: dict,
    base_dir: Path = DEFAULT_DIR,
    *,
    allow_large: bool = False,
    force: bool = False,
) -> Path:
    if key not in OUTPUT_NAMES:
        raise ValueError(f"Unknown dataset key: {key}")
    if key == "metropt3" and not allow_large:
        raise ValueError("MetroPT-3 is large (~208 MB); add --allow-large to confirm")

    source_url = entry["download_url"]
    ensure_allowlisted_url(source_url)
    folder = base_dir / key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / OUTPUT_NAMES[key]
    provenance = folder / "PROVENANCE.json"
    if target.exists() and not force:
        if not provenance.exists():
            raise ValueError(f"Existing file has no PROVENANCE.json: {target}; use --force after review")
        previous = json.loads(provenance.read_text(encoding="utf-8"))
        if previous.get("file_sha256") != sha256_file(target):
            raise ValueError(f"Existing file failed recorded SHA-256 verification: {target}")
        print(f"Already verified: {target}. Use --force to redownload.")
        return target

    # Atomic promotion; intermediates and partial files are removed on failure.
    with tempfile.TemporaryDirectory(prefix="forge-public-", dir=folder) as temp_dir:
        temporary = Path(temp_dir)
        raw = temporary / "download.bin"
        size = transfer(source_url, raw, LIMITS[key])
        downloaded_sha256 = sha256_file(raw)
        metadata = {"download_bytes": size}
        prepared = temporary / OUTPUT_NAMES[key]

        if key in {"maintie-gold", "maintie-silver"}:
            shutil.copyfile(raw, prepared)
            metadata.update(validate_maintie(prepared))
        elif key == "ai4i":
            metadata.update(extract_ai4i_csv(raw, prepared))
        else:  # metropt3: preserve zip; do not materialize a potentially huge CSV
            with ZipFile(raw) as archive:
                if archive.testzip() is not None:
                    raise ValueError("MetroPT-3 ZIP failed CRC validation")
            shutil.copyfile(raw, prepared)

        provenance_record = {
            "dataset": key,
            "publisher": entry["publisher"],
            "purpose": entry["purpose"],
            "license": entry["license"],
            "landing_page": entry["landing_page"],
            "source_url": source_url,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_sha256": downloaded_sha256,
            "file_sha256": sha256_file(prepared),
            "file_name": target.name,
            "not_abb_work_order_data": True,
            **metadata,
        }
        metadata_path = temporary / "PROVENANCE.json"
        metadata_path.write_text(
            json.dumps(provenance_record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prepared.replace(target)
        metadata_path.replace(provenance)

    print(f"Saved: {target}")
    print(f"SHA-256: {provenance_record['file_sha256']}")
    print(f"Provenance: {provenance}")
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--list", action="store_true", help="show dataset choices without network calls")
    commands.add_argument("--dataset", choices=sorted(OUTPUT_NAMES), help="dataset to retrieve")
    parser.add_argument("--allow-large", action="store_true", help="allow MetroPT-3 large download")
    parser.add_argument("--force", action="store_true", help="replace a prior downloaded copy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = load_catalog()
    if args.list:
        print("Datasets (stored under data/raw/public/; not the ABB knowledge corpus):")
        for key in sorted(OUTPUT_NAMES):
            info = catalog[key]
            note = " [large: --allow-large]" if key == "metropt3" else ""
            print(f"  {key:16} {info['license']}{note}\n      {info['landing_page']}")
        return 0

    assert args.dataset is not None
    try:
        download_dataset(args.dataset, catalog[args.dataset], force=args.force, allow_large=args.allow_large)
    except (ValueError, OSError, HTTPError, URLError, BadZipFile, KeyError, json.JSONDecodeError) as exc:
        print(f"Download/validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
