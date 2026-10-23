"""Parse native-text PDFs while preserving Docling's document tree and provenance."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "artifacts/docling-models"
MODEL_PINS = json.loads((ROOT / "versions.lock.json").read_text(encoding="utf-8"))["pdf_parser_models"]


def model_files():
    """Yield only the model files explicitly pinned for this parser."""
    for spec in MODEL_PINS.values():
        for filename, digest in spec["files"].items():
            path = MODELS_DIR / spec["repo_id"].replace("/", "--") / filename
            yield spec, filename, digest, path


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_models():
    for _, _, expected, path in model_files():
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"Missing or invalid parser model: {path}; run python -m scripts.download_parser_models")


def parse_pdf(source: Path, page_range: tuple[int, int]) -> dict:
    """Return native Docling JSON; page_range uses inclusive physical PDF pages."""
    if not source.is_file():
        raise ValueError(f"PDF not found: {source}")
    if not 1 <= page_range[0] <= page_range[1]:
        raise ValueError("Pages must satisfy 1 <= start <= end")
    verify_models()

    # Delay heavyweight imports so data-only tools remain usable without Docling.
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        artifacts_path=MODELS_DIR,
        do_ocr=False,
        do_table_structure=True,
        enable_remote_services=False,
        allow_external_plugins=False,
        accelerator_options=AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CPU),
    )
    options.layout_options.model_spec.revision = MODEL_PINS["layout"]["revision"]
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    result = converter.convert(source, page_range=page_range)
    if result.status != ConversionStatus.SUCCESS:
        raise RuntimeError(f"PDF conversion did not complete: {result.status}")
    if set(result.document.pages) != set(range(page_range[0], page_range[1] + 1)):
        raise RuntimeError("PDF conversion did not return every requested page")
    return {
        "schema_version": 1,
        "parser": {
            "packages": {name: version(name) for name in ("docling", "docling-core", "docling-parse")},
            "page_range": list(page_range),
            "options": {
                "device": "cpu", "num_threads": 4, "do_ocr": False,
                "do_table_structure": True, "table_mode": "accurate",
            },
            "models": MODEL_PINS,
        },
        # The body tree preserves interleaving; texts + tables concatenation does not.
        "document": result.document.export_to_dict(),
    }
