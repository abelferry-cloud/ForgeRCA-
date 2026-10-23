"""Fetch and hash the small upstream artifacts named in versions.lock.json.

Explicit network check; no installation, model weights or filesystem writes.
"""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))
    artifacts = [(name, package["url"], package["sha256"]) for name, package in lock["packages"].items()]
    model = lock["embedding"]
    base = f"https://huggingface.co/{model['model_id']}/resolve/{model['revision']}"
    artifacts += [(name, f"{base}/{name}", digest) for name, digest in model["configuration_files"].items()]
    for name, url, expected in artifacts:
        with urlopen(url, timeout=45) as response:
            actual = hashlib.sha256(response.read()).hexdigest()
        if actual != expected:
            raise SystemExit(f"SHA-256 mismatch: {name}: expected {expected}, got {actual}")
        print(f"OK {name}: {actual}")
    print(f"Verified {len(artifacts)} artifacts; no packages installed or weights downloaded")


if __name__ == "__main__":
    main()
