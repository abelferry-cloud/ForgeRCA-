"""Dense embeddings from Alibaba Cloud's Beijing endpoint; no local model assets."""

import json
import math
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config import ConfigError, Settings

ROOT = Path(__file__).resolve().parents[2]
SPEC = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))["embedding"]


class EmbeddingError(ValueError):
    """A safe error message without credentials, input text or raw server responses."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected destination.
        return None


class DenseEmbedder:
    def __init__(self, settings=None):
        settings = settings or Settings.from_env(required=("DASHSCOPE_API_KEY",))
        if not settings.dashscope_api_key:
            raise ConfigError("Missing required environment variables: DASHSCOPE_API_KEY")
        if settings.embedding_model != SPEC["model_id"]:
            raise ConfigError("EMBEDDING_MODEL must match versions.lock.json; rebuild the index when changing models")
        self._auth = settings.dashscope_api_key
        self._configuration = deepcopy(SPEC)
        self._opener = build_opener(_NoRedirect())

    @property
    def configuration(self):
        return deepcopy(self._configuration)

    def encode(self, texts):
        """Preserve input order; batch API calls and normalize each dense vector."""
        if (not isinstance(texts, list)
                or any(not isinstance(text, str) or not text.strip() for text in texts)):
            raise ValueError("Embedding inputs must be a list of nonempty strings")
        spec = self._configuration
        for index, text in enumerate(texts):
            if len(text.encode("utf-8")) > spec["inference"]["max_input_utf8_bytes"]:
                raise ValueError(f"Embedding input {index} exceeds the UTF-8 byte limit")
        vectors, batches = [], []
        for start in range(0, len(texts), spec["inference"]["batch_size"]):
            inputs = texts[start:start + spec["inference"]["batch_size"]]
            payload = {"model": spec["model_id"], "input": inputs, "dimensions": spec["dimension"],
                       "encoding_format": spec["inference"]["encoding_format"]}
            request = Request(spec["base_url"] + "/embeddings", method="POST",
                              data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              headers={"Content-Type": "application/json",
                                       "Authorization": "Bearer " + self._auth.reveal()})
            try:
                with self._opener.open(request, timeout=spec["inference"]["timeout_seconds"]) as response:
                    result = json.load(response)
            except HTTPError as error:
                status = error.code
                error.close()
                raise EmbeddingError(f"Embedding API returned HTTP {status}; response body withheld") from None
            except (URLError, OSError, ValueError):
                raise EmbeddingError("Embedding API transport or JSON response failure") from None
            ordered, usage = self._validate_response(result, len(inputs))
            vectors.extend(ordered)
            batches.append({"input_count": len(inputs), "total_tokens": usage})
        return {"vectors": vectors, "batches": batches}

    def _validate_response(self, result, count):
        spec = self._configuration
        invalid = "Invalid embedding API response"
        if not isinstance(result, dict) or result.get("model") != spec["model_id"]:
            raise EmbeddingError(invalid)
        data = result.get("data")
        if not isinstance(data, list) or len(data) != count:
            raise EmbeddingError(invalid)
        ordered = [None] * count
        for item in data:
            if not isinstance(item, dict):
                raise EmbeddingError(invalid)
            index, vector = item.get("index"), item.get("embedding")
            if type(index) is not int or not 0 <= index < count or ordered[index] is not None:
                raise EmbeddingError(invalid)
            if (not isinstance(vector, list) or len(vector) != spec["dimension"]
                    or any(type(value) not in (int, float) or not abs(value) <= 3.4028234663852886e38
                           for value in vector)):
                raise EmbeddingError(invalid)
            norm = math.hypot(*vector)
            if norm == 0:
                raise EmbeddingError(invalid)
            ordered[index] = [value / norm for value in vector]
        usage = result.get("usage", {})
        if not isinstance(usage, dict):
            raise EmbeddingError(invalid)
        total = usage.get("total_tokens")
        if total is not None and (type(total) is not int or total < 0):
            raise EmbeddingError(invalid)
        return ordered, total
