"""Stable document keys for every parsed manual.

A key is ``{source_id}@{revision}:{sha256}``. The full digest distinguishes
file replacements even when their digest prefixes match. ``source_id`` is
the manifest ``id`` under the name already used by
``scripts/parse_pdf.py``.

The key is the parent of the evidence anchor ``source_id + sha256 + page +
locator`` defined in ``app/ingestion/__init__.py``; it must never be derived from
a row index or a retrieval rank.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

SHA256_PATTERN = r"[0-9a-f]{64}"
IDENTIFIER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
FIRMWARE_PATTERN = r"ASCKX [0-9]+\.[0-9]+"
SOURCE_URL_PATTERN = r"https?://\S+"
DOCUMENT_CODE_PATTERN = r"\S+"
KEY_SEPARATOR = "@"
DIGEST_SEPARATOR = ":"

KEY_PATTERN = (
    rf"(?P<source_id>{IDENTIFIER_PATTERN})"
    rf"{KEY_SEPARATOR}(?P<revision>{IDENTIFIER_PATTERN})"
    rf"{DIGEST_SEPARATOR}(?P<sha256>{SHA256_PATTERN})"
)

__all__ = [
    "FIRMWARE_PATTERN",
    "DocumentKey",
    "DocumentKeyConflict",
    "DocumentKeyError",
    "ParsedKey",
    "document_keys",
    "parse_key",
    "printed_page_labels",
]


class DocumentKeyError(ValueError):
    """Raised when manifest data cannot produce a trustworthy document key."""


class DocumentKeyConflict(DocumentKeyError):
    """Raised when two sources claim the same key, revision slot or digest."""


@dataclass(frozen=True)
class DocumentKey:
    """Identity of one manual revision, plus where it came from."""

    source_id: str
    document_code: str
    revision: str
    firmware_scope: str | None
    sha256: str
    source_url: str
    accessed_at: str

    @property
    def value(self) -> str:
        return f"{self.source_id}{KEY_SEPARATOR}{self.revision}{DIGEST_SEPARATOR}{self.sha256}"

    @classmethod
    def from_source(cls, source: Mapping[str, Any]) -> DocumentKey:
        """Build a key from one ``data/sources/manifest.json`` entry."""
        label = _label(source)
        return cls(
            source_id=_text(source, "id", IDENTIFIER_PATTERN, label),
            document_code=_text(source, "document_code", DOCUMENT_CODE_PATTERN, label),
            revision=_text(source, "revision", IDENTIFIER_PATTERN, label),
            firmware_scope=_firmware(source, label),
            sha256=_text(source, "sha256", SHA256_PATTERN, label),
            source_url=_text(source, "url", SOURCE_URL_PATTERN, label),
            accessed_at=_access_date(source, label),
        )


@dataclass(frozen=True)
class ParsedKey:
    """Identity encoded in a key string: source, revision and full digest.

    It deliberately does not carry the document code, firmware scope or download
    URL, so it can route a lookup but never substitute for the manifest entry.
    """

    source_id: str
    revision: str
    sha256: str


def parse_key(value: str) -> ParsedKey:
    if not isinstance(value, str):
        raise DocumentKeyError(f"Invalid document key, expected str: {type(value).__name__}")
    match = re.fullmatch(KEY_PATTERN, value)
    if match is None:
        raise DocumentKeyError(f"Invalid document key: {value}")
    return ParsedKey(
        source_id=match.group("source_id"),
        revision=match.group("revision"),
        sha256=match.group("sha256"),
    )


def document_keys(sources: Iterable[Mapping[str, Any]]) -> dict[str, DocumentKey]:
    """Return ``{key: DocumentKey}``, rejecting ambiguous manifest entries."""
    keys: dict[str, DocumentKey] = {}
    revisions: dict[tuple[str, str], DocumentKey] = {}
    digests: dict[str, DocumentKey] = {}
    for source in sources:
        key = DocumentKey.from_source(source)
        if key.value in keys:
            raise DocumentKeyConflict(f"Duplicate document key: {key.value}")
        slot = (key.source_id, key.revision)
        if slot in revisions:
            raise DocumentKeyConflict(f"Duplicate document revision: {key.source_id} {key.revision}")
        if key.sha256 in digests:
            raise DocumentKeyConflict(f"Duplicate document digest: {key.sha256}")
        keys[key.value] = key
        revisions[slot] = key
        digests[key.sha256] = key
    return keys


def printed_page_labels(source: Mapping[str, Any]) -> dict[int, str]:
    """Read only explicit, fingerprint-bound labels; never infer a page offset."""
    if "printed_page_map" not in source:
        return {}
    mapping = source["printed_page_map"]
    if not isinstance(mapping, dict) or mapping.get("sha256") != source.get("sha256"):
        raise ValueError("Printed page map must match the source SHA-256")
    reference = mapping.get("verification_ref")
    if not isinstance(reference, str) or not reference.strip() or reference != reference.strip():
        raise ValueError("Printed page map requires a verification reference")
    pages = mapping.get("pages")
    total = source.get("pages")
    verified = source.get("verified_pdf_pages", [])
    if (not isinstance(pages, dict) or type(total) is not int or total < 1
            or not isinstance(verified, list) or any(type(page) is not int for page in verified)):
        raise ValueError("Invalid printed page map or source pages")
    labels = {}
    for page, label in pages.items():
        if (not isinstance(page, str) or not re.fullmatch(r"[1-9][0-9]*", page)
                or not 1 <= int(page) <= total or int(page) not in verified
                or not isinstance(label, str) or not re.fullmatch(r"\S+", label)):
            raise ValueError("Printed page labels require verified physical pages and nonempty strings")
        labels[int(page)] = label
    return labels


def _label(source: Mapping[str, Any]) -> str:
    value = source.get("id")
    return value if isinstance(value, str) and value else "<missing id>"


def _text(source: Mapping[str, Any], field: str, pattern: str, label: str) -> str:
    value = source.get(field)
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise DocumentKeyError(f"Invalid {field}: {label}")
    return value


def _firmware(source: Mapping[str, Any], label: str) -> str | None:
    if "firmware_scope" not in source:
        raise DocumentKeyError(f"Invalid firmware_scope: {label}")
    value = source.get("firmware_scope")
    # ``null`` means "not firmware-limited", never "unknown firmware"; a document
    # revision is not a firmware version and must not be substituted for one.
    if value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(FIRMWARE_PATTERN, value) is None:
        raise DocumentKeyError(f"Invalid firmware_scope: {label}")
    return value


def _access_date(source: Mapping[str, Any], label: str) -> str:
    value = source.get("accessed_at")
    if not isinstance(value, str):
        raise DocumentKeyError(f"Invalid accessed_at: {label}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise DocumentKeyError(f"Invalid accessed_at: {label}") from error
    if parsed.isoformat() != value:
        raise DocumentKeyError(f"Invalid accessed_at: {label}")
    return value
