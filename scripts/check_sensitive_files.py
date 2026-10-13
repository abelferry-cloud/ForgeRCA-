"""Refuse to track credentials, vendor originals, raw indexes or model traces.

This is the offline half of the M0-08 CI gate. It answers one question: does
the set of files Git would publish contain anything the project promised not to
publish? It inspects tracked paths only, so it never fails because of a local
``.env`` or a downloaded PDF that is correctly ignored.

Checks performed:

1. Forbidden path prefixes (``data/raw/``, ``data/processed/``,
   ``data/indexes/``, ``artifacts/``, ``secrets/``).
2. Ignored environment files other than the secret-free ``.env.example``.
3. Forbidden suffixes (vendor PDFs, key material, database dumps, archives).
4. Oversized tracked files, which usually mean a binary slipped in by accident.
5. Credential patterns and secret-looking assignments inside text files.
6. The ignore rules themselves: local-only data must be ignored and
   ``.env.example`` must stay trackable.
"""

import argparse
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PREFIXES = (
    "data/raw/",
    "data/processed/",
    "data/indexes/",
    "artifacts/",
    "secrets/",
)

# Documented exceptions. Kept empty on purpose: nothing under the prefixes
# above is publishable, and adding an entry here needs a review decision.
ALLOWED_PATHS = frozenset()

FORBIDDEN_SUFFIXES = (
    ".pdf",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
)

# Credentials are ignored, except this documented template. See docs/data-spec.md.
ENV_TEMPLATE = ".env.example"

SECRET_PATTERNS = (
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

SECRET_NAME_RE = re.compile(
    r"(?P<name>[A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key"
    r"|access[_-]?key|private[_-]?key|credential)[A-Za-z0-9_]*)"
    # A backslash ends the value: "\n" and "\t" are escape sequences in source
    # code, not credential material, and matching across them over-reports.
    r"\s*[:=]\s*[\"']?(?P<value>[^\s\"'#\\]+)",
    re.IGNORECASE,
)

# Values that look like a secret assignment but are clearly not one.
PLACEHOLDER_RE = re.compile(
    r"^(<[^>]*>|\$\{[^}]*\}|your[-_].*|change[-_]?me|changeit|example.*"
    r"|placeholder.*|replace[-_]?me|todo.*|none|null|nil|false|true"
    r"|x{3,}|\*+|-+|_+)$",
    re.IGNORECASE,
)

MIN_SECRET_LENGTH = 16
MAX_TRACKED_BYTES = 5 * 1024 * 1024

IGNORE_EXPECTED_IGNORED = (
    ".env",
    "data/raw/abb/example.pdf",
    "data/processed/example.json",
    "data/indexes/example/segment.json",
    "artifacts/evaluations/example/config.json",
    ".venv/lib/example.py",
)

IGNORE_EXPECTED_TRACKED = (ENV_TEMPLATE,)


def posix(path):
    return Path(path).as_posix()


def check_path(path):
    """Return reasons why ``path`` must not be tracked (``path`` is repo-relative)."""
    path = posix(path)
    if path in ALLOWED_PATHS:
        return []
    reasons = []
    for prefix in FORBIDDEN_PREFIXES:
        if path.startswith(prefix):
            reasons.append(f"lives under the unpublishable prefix {prefix}")
            break
    name = path.rsplit("/", 1)[-1]
    if name == ".env" or (name.startswith(".env.") and path != ENV_TEMPLATE):
        reasons.append("environment file with local secrets")
    for suffix in FORBIDDEN_SUFFIXES:
        if name.lower().endswith(suffix):
            reasons.append(f"forbidden file type {suffix}")
            break
    return reasons


def is_placeholder(value):
    return not value or bool(PLACEHOLDER_RE.match(value))


def check_text(path, text):
    """Return reasons why the text content of ``path`` must not be published."""
    reasons = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            reasons.append(f"contains what looks like a {label}")
    for match in SECRET_NAME_RE.finditer(text):
        value = match.group("value")
        if len(value) < MIN_SECRET_LENGTH or is_placeholder(value):
            continue
        reasons.append(f"assigns a non-placeholder value to {match.group('name')}")
    return reasons


def looks_binary(raw):
    return b"\x00" in raw[:8192]


def collect_tracked_files(root=ROOT):
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def ignored_in_git(root, path):
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", path],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def check_ignore_rules(root=ROOT):
    """Verify `.gitignore` still ignores local data and still tracks the template."""
    if not (root / ".git").exists():
        return []
    issues = []
    for path in IGNORE_EXPECTED_IGNORED:
        if not ignored_in_git(root, path):
            issues.append(f"{path}: expected to be ignored by .gitignore but is not")
    for path in IGNORE_EXPECTED_TRACKED:
        if ignored_in_git(root, path):
            issues.append(f"{path}: expected to be trackable but .gitignore/ignore rules exclude it")
    return issues


def find_issues(root=ROOT, files=None, ignore_rules=True):
    """Return a list of human-readable problems, newest conventions included."""
    root = Path(root)
    if files is None:
        files = collect_tracked_files(root)
    issues = []
    for relative in files:
        reasons = check_path(relative)
        target = root / relative
        if not target.is_file():
            issues.extend(f"{relative}: {reason}" for reason in reasons)
            continue
        if target.stat().st_size > MAX_TRACKED_BYTES:
            issues.append(f"{relative}: {target.stat().st_size} bytes exceeds the {MAX_TRACKED_BYTES} byte tracked-file limit")
        if reasons:
            issues.extend(f"{relative}: {reason}" for reason in reasons)
            continue
        raw = target.read_bytes()
        if looks_binary(raw):
            continue
        issues.extend(f"{relative}: {reason}" for reason in check_text(relative, raw.decode("utf-8", errors="replace")))
    if ignore_rules:
        issues.extend(check_ignore_rules(root))
    return issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-ignore-rules", action="store_true", help="Skip verifying .gitignore coverage")
    args = parser.parse_args()
    tracked = collect_tracked_files()
    problems = find_issues(ignore_rules=not args.no_ignore_rules)
    if problems:
        print("FAIL: sensitive files would be published")
        for problem in problems:
            print("  - " + problem)
        raise SystemExit(1)
    print(f"OK: {len(tracked)} tracked files contain no credentials, vendor originals or raw indexes")
