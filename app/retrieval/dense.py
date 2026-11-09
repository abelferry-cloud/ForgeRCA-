"""Build isolated dense-v3 indexes and query them with explicit applicability filters."""

import json
import math
import re
from copy import deepcopy
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from app.config import Settings
from app.retrieval.corpus import validate_records
from app.retrieval.embedding import SPEC, DenseEmbedder
from app.retrieval.index_schema import index_record_id, load_mapping, validate_index_record
from app.schemas.document import FIRMWARE_PATTERN


class SearchError(ValueError):
    """A safe service error that does not expose requests, credentials or server bodies."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SearchClient:
    """The initial Compose service is unauthenticated and loopback-only."""

    def __init__(self, settings=None):
        settings = settings or Settings.from_env()
        if settings.opensearch_host not in ("localhost", "127.0.0.1"):
            raise ValueError("Dense baseline requires a loopback OpenSearch host")
        if settings.opensearch_user or settings.opensearch_password:
            raise ValueError("Dense baseline uses the local unauthenticated Compose service")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,60}", settings.opensearch_index_prefix):
            raise ValueError("Invalid OPENSEARCH_INDEX_PREFIX")
        self.base_url = f"http://{settings.opensearch_host}:{settings.opensearch_port}"
        self.prefix = settings.opensearch_index_prefix + "-dense-v3-"
        self._opener = build_opener(_NoRedirect())

    def check_index_name(self, index):
        if not isinstance(index, str) or not re.fullmatch(re.escape(self.prefix) + r"[0-9a-f]{32}", index):
            raise ValueError("Use the concrete dense-v3 index returned by build_index; aliases/wildcards are refused")

    def request(self, method, path, payload=None):
        body = payload if isinstance(payload, bytes) else (
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") if payload is not None else None)
        content_type = "application/x-ndjson" if isinstance(payload, bytes) else "application/json"
        request = Request(self.base_url + path, data=body, method=method, headers={"Content-Type": content_type})
        try:
            with self._opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            raise SearchError(f"OpenSearch returned HTTP {status}; response body withheld") from None
        except (URLError, OSError, ValueError):
            raise SearchError("OpenSearch transport or JSON response failure") from None

    def verify_mapping(self, index):
        self.check_index_name(index)
        response = self.request("GET", f"/{index}/_mapping")
        expected = load_mapping()["mappings"]
        actual = response.get(index) if isinstance(response, dict) else None
        if not isinstance(actual, dict) or actual.get("mappings") != expected:
            raise SearchError("Index mapping/model identity differs from the pinned configuration")


def _encoder(embedder):
    embedder = embedder or DenseEmbedder()
    if embedder.configuration != SPEC:
        raise ValueError("Embedding configuration differs from the pinned index model")
    return embedder


def build_index(client, records, embedder=None):
    """Validate and embed all inputs before creating one new, uniquely named index."""
    validate_records(records)
    if not records:
        raise ValueError("Cannot build an empty corpus index")
    mapping = load_mapping()
    encoded = _encoder(embedder).encode([record["text"] for record in records])
    vectors = encoded["vectors"]
    if len(vectors) != len(records):
        raise ValueError("Embedding count differs from corpus size")
    complete = [{**record, "embedding": vector} for record, vector in zip(records, vectors, strict=True)]
    for record in complete:
        validate_index_record(record, mapping)
    index = client.prefix + uuid4().hex
    client.check_index_name(index)
    # A successful PUT is the ownership boundary. A failed create is never followed
    # by DELETE, because an existing index may belong to another caller.
    created = client.request("PUT", f"/{index}", mapping)
    if not isinstance(created, dict) or created.get("acknowledged") is not True:
        raise SearchError("Index creation was not acknowledged; no successful index was published")
    try:
        lines = []
        for record in complete:
            lines.extend((json.dumps({"create": {"_id": index_record_id(record)}}),
                          json.dumps(record, ensure_ascii=False, allow_nan=False)))
        result = client.request("POST", f"/{index}/_bulk?refresh=true", ("\n".join(lines) + "\n").encode("utf-8"))
        if (not isinstance(result, dict) or result.get("errors") is not False
                or len(result.get("items", [])) != len(records)
                or any(item.get("create", {}).get("status") != 201 for item in result["items"])):
            raise SearchError("Bulk creation did not succeed for every record")
        client.verify_mapping(index)
        if client.request("GET", f"/{index}/_count").get("count") != len(records):
            raise SearchError("Index record count differs from the validated corpus")
    except (SearchError, ValueError, TypeError, KeyError, AttributeError):
        try:
            deleted = client.request("DELETE", f"/{index}")
            if not isinstance(deleted, dict) or deleted.get("acknowledged") is not True:
                raise SearchError("Index cleanup was not acknowledged")
        except SearchError:
            raise SearchError("Index build failed and cleanup failed; inspect the new index before retrying") from None
        raise SearchError("Index build failed; the new index was removed") from None
    return {"index": index, "records": len(records), "embedding_configuration": deepcopy(SPEC),
            "embedding_batches": encoded["batches"]}


def query_filter(model, as_of, firmware_version):
    if not isinstance(model, str) or not model or model != model.strip():
        raise ValueError("An exact nonempty model is required")
    try:
        timestamp = datetime.fromisoformat(as_of)
        if timestamp.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("as_of must be an ISO timestamp with a timezone") from None
    if firmware_version is not None and (
        not isinstance(firmware_version, str) or not re.fullmatch(FIRMWARE_PATTERN, firmware_version)
    ):
        raise ValueError("Invalid firmware_version")
    scopes = [{"term": {"firmware_state": "unrestricted"}}]
    if firmware_version is not None:
        scopes.append({"bool": {"filter": [{"term": {"firmware_state": "known"}}], "should": [
            {"term": {"firmware_scope": firmware_version}}, {"term": {"firmware_version": firmware_version}},
        ], "minimum_should_match": 1}})
    return {"bool": {"filter": [{"term": {"model": model}}, {"range": {"available_at": {"lte": as_of}}},
                                {"bool": {"should": scopes, "minimum_should_match": 1}}]}}


def retrieve(client, index, query, *, model, as_of, firmware_version=None, top_k=5, embedder=None):
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError("top_k must be an integer between 1 and 100")
    filters = query_filter(model, as_of, firmware_version)
    client.verify_mapping(index)
    encoded = _encoder(embedder).encode([query])
    result = client.request("POST", f"/{index}/_search", {
        "size": top_k, "query": {"knn": {"embedding": {
            "vector": encoded["vectors"][0], "k": top_k, "filter": filters,
        }}},
    })
    try:
        if result["timed_out"] is not False or result["_shards"]["failed"] != 0:
            raise ValueError
        mapping = load_mapping()
        unique = {}
        for hit in result["hits"]["hits"]:
            record, score = hit["_source"], hit["_score"]
            validate_index_record(record, mapping)
            identity = index_record_id(record)
            if (hit.get("_index") != index or hit["_id"] != identity or type(score) not in (int, float)
                    or not math.isfinite(score) or score < 0):
                raise ValueError
            # Recheck applicability on returned records; never trust a malformed
            # server response to bypass the filter or claim unknown firmware applies.
            known = record["firmware_scope"] or record["firmware_version"]
            if (model not in record["model"] or datetime.fromisoformat(record["available_at"]) >
                    datetime.fromisoformat(as_of) or not (record["firmware_state"] == "unrestricted" or
                    (record["firmware_state"] == "known" and firmware_version is not None
                     and known == firmware_version))):
                raise ValueError
            if identity not in unique or score > unique[identity]["score"]:
                unique[identity] = {"index_id": identity, "score": score,
                                    **{key: value for key, value in record.items() if key != "embedding"}}
        hits = sorted(unique.values(), key=lambda hit: (-hit["score"], hit["index_id"]))[:top_k]
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise SearchError("Invalid or incomplete search response") from None
    return {"index": index, "hits": [{"rank": rank, **hit} for rank, hit in enumerate(hits, 1)],
            "filters": filters, "top_k": top_k, "embedding_configuration": deepcopy(SPEC),
            "embedding_batches": encoded["batches"]}
