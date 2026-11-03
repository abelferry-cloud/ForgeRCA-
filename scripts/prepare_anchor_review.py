"""Prepare a text-free inventory and a local HTML packet for human anchor review."""

import argparse
import hashlib
import html
import json
from dataclasses import asdict
from pathlib import Path

from app.ingestion.incremental import compare_parses
from app.ingestion.metadata import locate_chunk
from app.schemas.document import document_keys
from scripts.download_sources import verify_file

ROOT = Path(__file__).resolve().parents[1]


def _inside(path, folder, suffix):
    path = path.resolve()
    if not path.is_relative_to((ROOT / folder).resolve()) or path.suffix != suffix:
        raise ValueError(f"Expected a {suffix} file inside {folder}/")
    return path


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def build_review(paths):
    """Include every unique chunk from explicit snapshots; never fill human decisions."""
    paths = sorted(_inside(path, "data/processed", ".json") for path in paths)
    if len(set(paths)) != len(paths):
        raise ValueError("Repeated input snapshot")
    manifest_bytes = (ROOT / "data/sources/manifest.json").read_bytes()
    sources = json.loads(manifest_bytes)["sources"]
    keys = document_keys(sources)
    sources = {key: source for key, source in zip(keys, sources, strict=True)}
    inventory = {
        "review_version": 1, "selection": "all_chunks_from_explicit_snapshots",
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "inputs": [], "items": [],
    }
    cards, seen = [], set()
    for input_index, path in enumerate(paths):
        raw = path.read_bytes()
        result = json.loads(raw)
        comparison = compare_parses(result, result)
        key = result["source"]["document_key"]
        if key not in keys or any(result["source"].get(field) != value
                                  for field, value in asdict(keys[key]).items()):
            raise ValueError("Snapshot source differs from the registered source")
        source = sources[key]
        pdf_path = _inside(ROOT / source["local_path"], "data/raw", ".pdf")
        verify_file(pdf_path, source)
        inventory["inputs"].append({
            "path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
            "document_key": key, "source_id": source["id"],
            "pdf_path": pdf_path.relative_to(ROOT).as_posix(), "pdf_sha256": source["sha256"],
            "page_range": result["parser"]["page_range"],
            "parser_fingerprint": comparison["parser_fingerprint_before"],
        })
        for chunk_index, chunk in enumerate(result["chunks"]):
            evidence_id = chunk["evidence_id"]
            if evidence_id in seen:
                raise ValueError(f"Repeated evidence ID across snapshots: {evidence_id}")
            seen.add(evidence_id)
            located = locate_chunk(chunk, source)
            if any(field not in chunk or chunk[field] != located[field] for field in ("locations", "table_row")):
                raise ValueError("Missing or stale display locations; reparse the snapshot")
            if chunk["chunk_type"] not in {"section", "fault_rows", "table_rows", "table"}:
                raise ValueError("Unsupported chunk type for review")
            item = {
                "sample_id": f"A{len(seen):03}", "input_index": input_index, "chunk_index": chunk_index,
                "evidence_id": evidence_id, "chunk_type": chunk["chunk_type"],
                "locations": chunk["locations"], "table_row": chunk["table_row"],
                "reviewer": None, "review_date": None, "decision": "pending", "notes": None,
            }
            inventory["items"].append(item)
            links = " · ".join(
                f'<a href="{html.escape(pdf_path.as_uri())}#page={location["pdf_page"]}">'
                f'PDF 物理页 {location["pdf_page"]}</a>' for location in item["locations"]
            )
            details = {"sample": item, "document_key": key, "section": chunk["section"],
                       "source_refs": chunk["source_refs"], "heading_refs": chunk.get("heading_refs", []),
                       "evidence_locator": chunk["evidence_locator"]}
            cards.append(
                f'<article id="{item["sample_id"]}"><h2>{item["sample_id"]} · 待人工核对</h2>'
                f'<p>{links} · <a href="{html.escape(path.as_uri())}">解析快照</a></p>'
                f'<pre>{html.escape(chunk["text"])}</pre>'
                f'<details><summary>定位、原始引用与空白审核字段</summary>'
                f'<pre>{html.escape(_json(details))}</pre></details></article>'
            )
    if len(seen) < 30:
        raise ValueError(f"Human review preparation requires at least 30 unique anchors; got {len(seen)}")
    header = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M1-15 证据锚点审核包</title>'
        '<style>body{max-width:1000px;margin:32px auto;padding:0 20px;font:16px/1.7 sans-serif;'
        'color:#202c38;background:#f7f8fa}article{background:white;padding:24px;margin:24px 0;'
        'border:1px solid #ccd4dc}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#125aa0}</style>'
        f'<h1>M1-15 · {len(seen)} 个待人工核对锚点</h1>'
        '<p>此材料由脚本整理，所有审核结论均未填写。请对照原 PDF 检查页码、边界框、文本、'
        '表行与章节/安全上下文；将真实审核人、日期、决策和问题记录填入公开清单。'
        '此 HTML 是只读阅读材料，不保存审核操作，也不代表审核通过。</p>'
        '<p>请在本机打开；PDF 链接定位物理页。若阅读器忽略页码片段，请手动跳页。'
        '含厂商原文，仅保存在忽略目录，不发布、不加入检索。</p>'
        f'<details><summary>输入快照及指纹</summary><pre>{html.escape(_json(inventory["inputs"]))}</pre></details>'
    )
    return inventory, header + "\n".join(cards) + "</html>\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, nargs="+", type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    inventory_path = _inside(args.inventory, "docs/reviews", ".json")
    output = _inside(args.output, "artifacts", ".html")
    if inventory_path.exists() or output.exists():
        parser.error("Choose new output filenames; existing review records must not be overwritten")
    inventory, packet = build_review(args.inputs)
    serialized = _json(inventory) + "\n"
    for path, content in ((inventory_path, serialized), (output, packet)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    print(f"Prepared {len(inventory['items'])} unique anchors; all pending human review: {output}")


if __name__ == "__main__":
    main()
