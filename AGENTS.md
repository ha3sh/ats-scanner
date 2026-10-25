# AGENTS.md

## Commands (repo root, Windows PowerShell; no bash-only syntax)
- Install: `uv sync`
- Before every commit: `uv run poe check` (ruff + mypy + pytest; must pass)
- One test: `uv run pytest tests/test_architecture.py::test_core_imports_no_fastapi_parsers_or_http_clients -v`
- Frontend commands are added when web/ is built.

## Read first
- docs/PRODUCT_PLAN.md (what and why), docs/SPEC.md (behaviour), docs/ARCHITECTURE.md (structure), docs/ROADMAP.md (order of work).
- If code and docs disagree, ask me. Don't pick silently.

## Architecture (dependencies point inward)
- src/ats_scanner/core/: pure Python. Models, scoring, matching. No file I/O, no FastAPI, no pdfplumber/python-docx. Dictionary data is loaded by the wiring and passed in.
- src/ats_scanner/adapters/: PDF/DOCX extraction implementing the Protocols in core/ports.py.
- src/ats_scanner/api.py and main.py: transport and wiring only. No business logic.
- src/ats_scanner/static/: generated frontend output. Never hand-edit.
- web/: frontend source.
- tests/fixtures/: synthetic resumes and job descriptions only. Never real personal data.

## Rules
- Test first: write a failing test, show it failing, then implement.
- core/ never imports api, adapters or main. Today the guard test enforces third-party purity (no fastapi, pdfplumber, python-docx, or HTTP clients); extending it to forbid core importing api/adapters/main is done together with the first real core modules.
- Fully typed; mypy strict must pass. Pydantic v2 models at every boundary.
- Resume and job description text is never written to disk and never logged. Logs hold filename, size, duration and error codes only.
- No network calls at runtime or in tests.
- Wording: no vendor names (any ATS or resume tool) in UI text, findings or docs. The headline metric is "JD term coverage", never an "ATS score". The row/column views are captioned "possible extractor outputs".
- Every finding and score component links to evidence.
- Don't add a dependency without asking; say what it's for.
- Don't hand-edit uv.lock or src/ats_scanner/static. Never run the frontend build while the server is running.
- One prompt is one small change. Stay inside its scope. Don't start the next roadmap day on your own.

## Commits
Conventional Commits (feat(core): ...). Small commits.
