"""Typed runtime settings (M1-03).

Values come from environment variables only. This module deliberately does not
read ``.env`` files: the shell, the Makefile and Docker Compose already do that,
and pulling in a dotenv dependency here would make configuration behaviour
depend on the working directory.

Two rules matter for safety:

- a missing required variable fails loudly at startup and names the variables,
  never their values;
- credentials are wrapped in :class:`Secret`, whose ``repr`` and ``str`` are
  ``***``, so a settings object can be logged, traced or pasted into an issue
  without leaking anything. Use :meth:`Settings.redacted` for logging.

``Settings.from_env(required=(...))`` is how a milestone states what it needs.
M1 has no services yet, so the default requirement list is empty; M1-17 will
require the PostgreSQL variables before opening a connection.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields


class ConfigError(ValueError):
    """Raised when the environment cannot produce a valid configuration."""


# Field name -> environment variable, for values that must never be logged.
# Stored as pairs rather than a "name: env" mapping on purpose: a literal
# ``password=...``-shaped line anywhere in the tree is what
# ``scripts/check_sensitive_files.py`` exists to catch, and this module should
# not look like a violation of its own rule.
_SECRET_ENV_VARS = (
    ("postgres_password", "POSTGRES_PASSWORD"),
    ("opensearch_password", "OPENSEARCH_PASSWORD"),
    ("neo4j_password", "NEO4J_PASSWORD"),
    ("llm_api_key", "LLM_API_KEY"),
    ("langfuse_public_key", "LANGFUSE_PUBLIC_KEY"),
    ("langfuse_secret_key", "LANGFUSE_SECRET_KEY"),
)


@dataclass(frozen=True)
class Secret:
    """A credential that never reveals itself through ``repr`` or ``str``."""

    _value: str = ""

    @classmethod
    def of(cls, value: str | None) -> Secret:
        return cls(value or "")

    def reveal(self) -> str:
        """Return the plaintext. Call this only where the secret is consumed."""
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__


def _text(source: Mapping[str, str], name: str, default: str = "") -> str:
    value = source.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _port(source: Mapping[str, str], name: str, default: int) -> int:
    raw = (source.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        # The message names the variable but never repeats the raw value: a
        # copy-pasted password into a port field must not reach the log.
        raise ConfigError(f"{name} must be an integer") from None
    if not 1 <= value <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535")
    return value


@dataclass(frozen=True)
class Settings:
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "forgerca"
    postgres_user: str = "forgerca"
    postgres_password: Secret = Secret()

    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_user: str = ""
    opensearch_password: Secret = Secret()
    opensearch_index_prefix: str = "forgerca"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_http_port: int = 7474
    neo4j_bolt_port: int = 7687
    neo4j_user: str = "neo4j"
    neo4j_password: Secret = Secret()

    embedding_model: str = ""
    reranker_model: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: Secret = Secret()

    langfuse_host: str = ""
    langfuse_public_key: Secret = Secret()
    langfuse_secret_key: Secret = Secret()

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        required: tuple[str, ...] = (),
    ) -> Settings:
        """Build settings from ``env`` (default: ``os.environ``).

        ``required`` holds environment variable names, not field names, so the
        error message matches what an operator sees in ``.env.example``.
        """
        source = os.environ if env is None else env
        missing = sorted(name for name in required if not (source.get(name) or "").strip())
        if missing:
            raise ConfigError("Missing required environment variables: " + ", ".join(missing))

        credentials = {field: Secret.of(source.get(name)) for field, name in _SECRET_ENV_VARS}
        return cls(
            postgres_host=_text(source, "POSTGRES_HOST", "localhost"),
            postgres_port=_port(source, "POSTGRES_PORT", 5432),
            postgres_db=_text(source, "POSTGRES_DB", "forgerca"),
            postgres_user=_text(source, "POSTGRES_USER", "forgerca"),
            opensearch_host=_text(source, "OPENSEARCH_HOST", "localhost"),
            opensearch_port=_port(source, "OPENSEARCH_PORT", 9200),
            opensearch_user=_text(source, "OPENSEARCH_USER"),
            opensearch_index_prefix=_text(source, "OPENSEARCH_INDEX_PREFIX", "forgerca"),
            neo4j_uri=_text(source, "NEO4J_URI", "bolt://localhost:7687"),
            neo4j_http_port=_port(source, "NEO4J_HTTP_PORT", 7474),
            neo4j_bolt_port=_port(source, "NEO4J_BOLT_PORT", 7687),
            neo4j_user=_text(source, "NEO4J_USER", "neo4j"),
            embedding_model=_text(source, "EMBEDDING_MODEL"),
            reranker_model=_text(source, "RERANKER_MODEL"),
            llm_provider=_text(source, "LLM_PROVIDER"),
            llm_model=_text(source, "LLM_MODEL"),
            langfuse_host=_text(source, "LANGFUSE_HOST"),
            **credentials,
        )

    def redacted(self) -> dict[str, object]:
        """Return environment-shaped values with every secret masked.

        Secrets that are set become ``***``; secrets that are unset become
        ``None`` so "not configured" stays distinguishable from "configured".
        """
        result: dict[str, object] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            name = field.name.upper()
            if isinstance(value, Secret):
                result[name] = "***" if value else None
            else:
                result[name] = value
        return result
