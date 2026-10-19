"""Download only the pinned public ABB sources; no third-party dependencies."""

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def verify_file(path, source):
    if path.stat().st_size != source["bytes"]:
        raise ValueError(f"{path.name}: size mismatch")
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise ValueError(f"{path.name}: not a PDF")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != source["sha256"]:
        raise ValueError(f"{path.name}: SHA-256 mismatch; do not change the pin blindly")


def main():
    manifest = json.loads((ROOT / "data/sources/manifest.json").read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        url = urlparse(source["url"])
        if url.scheme != "https" or url.netloc != "library.e.abb.com":
            raise ValueError("Only official ABB HTTPS sources are supported")
        destination = (ROOT / source["local_path"]).resolve()
        if not destination.is_relative_to((ROOT / "data/raw/abb").resolve()):
            raise ValueError("Source destination must stay inside data/raw/abb")
        if destination.exists():
            verify_file(destination, source)
            print(f"Verified existing {source['id']}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            request = Request(source["url"], headers={"User-Agent": "ForgeRCA-source-fetch/0.1"})
            with urlopen(request, timeout=60) as response:
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as output:
                    temporary = Path(output.name)
                    while block := response.read(1024 * 1024):
                        output.write(block)
            verify_file(temporary, source)
            temporary.replace(destination)
            print(f"Downloaded and verified {source['id']}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, URLError) as error:
        raise SystemExit(f"Source acquisition failed: {error}") from error
