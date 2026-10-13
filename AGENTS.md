# ForgeRCA working agreement

- Before coding, state assumptions, inspect related files, and use at least one exploration subagent. Review its findings before editing. If subagents are unavailable, explicitly describe the fallback exploration.
- Use a `codex/` feature branch. Do not make substantive changes directly on `master` or `main`.
- Keep changes scoped, prefer simple implementations, and do not refactor unrelated code.
- Keep project documentation in Chinese; use English identifiers in machine-readable data and code.
- This repository is currently an initialization, not a working diagnosis application. Do not describe planned features or target metrics as implemented results.
- Preserve the distinction between manufacturer documents, project annotations, synthetic records, and evaluation labels. Never invent manufacturer page numbers, model compatibility, firmware versions, or field deployment history.
- Do not index `data/evaluation/`, `data/graph/`, or experiment answers as retrieval documents. Curated graph seeds are validation references, not extraction output.
- Do not commit credentials, third-party PDF originals, local indexes, or raw model traces. See `docs/data-spec.md` for provenance and redistribution rules.
- After data or validator changes, run `python scripts/validate_data.py` and `python -m unittest discover -s tests -v`. After source acquisition changes, also run `python scripts/validate_data.py --check-raw` when the PDFs are available.
- Read `docs/demo-and-milestones.md` before expanding scope. Add runtime dependencies only when implementing the corresponding milestone.
