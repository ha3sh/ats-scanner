# ATS Resume Scanner — v1 Architecture

Project: `ats-scanner`. Python package: `ats_scanner` (src layout). Console
scripts: `ats`, `ats-build`, `ats-dev`.

Status: plan of record. Nothing implemented yet.

## Folder tree

```
pyproject.toml                 uv project, runtime + dev dependencies, scripts
README.md
AGENTS.md
opencode.json                  context7 and playwright MCP servers
docs/
  SPEC.md
  ARCHITECTURE.md
  ROADMAP.md
src/
  ats_scanner/
    __main__.py                launcher: bind 127.0.0.1, open browser
    main.py                    FastAPI app, static mount, startup wiring
    api.py                     routes, request validation, error envelope
    config.py                  limits, versions, paths
    adapters/
      extract.py               Extractor implementations (pdfplumber, python-docx)
    core/
      ports.py                 Extractor, TermExtractor, SuggestionProvider
      documents.py             extracted-document model shared with adapters
      sections.py              section and contact detection
      terms.py                 JD cleaning, term extraction, matching
      score.py                 weights and weighted coverage only
      alignment.py             title/seniority and experience alignment
      checks.py                format and parse findings
      suggestions.py           suggestion templates
      report.py                Pydantic report models
    data/
      dictionary.json          hand-curated software/tech skills + aliases
    static/                    built frontend, single source of truth (committed)
web/
  index.html
  package.json
  vite.config.ts               build.outDir -> ../src/ats_scanner/static
  src/
    api/types.ts               generated from OpenAPI
    routes/
    components/
tests/
  fixtures/                    synthetic resumes and JDs, no real personal data
  test_*.py
```

There is no `web/dist` and no top-level `app/`. The frontend build writes
directly into `src/ats_scanner/static`, which is the only location FastAPI
serves and the only location that is committed. The Vite build empties that
directory first so stale assets cannot accumulate.

## Layers and dependency direction

```
web/ (React, TypeScript, Tailwind, shadcn/ui)
        │  HTTP + JSON
        ▼
src/ats_scanner/api.py  ──────────►  src/ats_scanner/core/  (pure)
        ▲                                 ▲
        │                                 │ implements core/ports.py
src/ats_scanner/main.py (wiring) ──►  adapters/extract.py
        │                                 │
        │                                 └── pdfplumber, python-docx
        └── loads data/dictionary.json once, validates it,
            passes the data into core as an argument
```

- `src/ats_scanner/core/` is pure: no FastAPI, no pdfplumber, no python-docx, no
  I/O of uploaded bytes, no file I/O at all, no network. It operates on
  already-extracted text, the validated dictionary data passed in as an
  argument, and plain data. Pydantic models are allowed because they are the
  contract.
- `src/ats_scanner/adapters/` owns all document parsing. It depends on
  `core/ports.py` and `core/documents.py`, and on third-party parsers, never the
  reverse.
- `src/ats_scanner/main.py` constructs adapters, loads
  `src/ats_scanner/data/dictionary.json` once, validates it with a Pydantic
  model, and injects both into the core pipeline. This is the only place wiring
  lives.
- `src/ats_scanner/api.py` handles transport: multipart, limits, error mapping,
  headers.
- `web/` knows only the HTTP contract in `web/src/api/types.ts`.

A guard test asserts that `core/` imports no HTTP client, no FastAPI, no
pdfplumber, and no python-docx, that a `core` import works without the adapter
modules loaded, and that `core/` performs no file I/O. A required test loads
`src/ats_scanner/data/dictionary.json` and validates it against its Pydantic
model.

## Protocols

All three live in `core/ports.py`. `core/documents.py` defines the
extracted-document model used by the `Extractor` protocol; adapters import it
from core. v1 ships exactly one implementation of each protocol. Adding an LLM
provider later means one adapter plus a config flag — and it would deliberately
break the no-network guarantee, so it must be opt-in and disclosed in the UI.

| Protocol | Input | Output | v1 implementation |
| --- | --- | --- | --- |
| `Extractor` | file bytes, filename, content type | `core/documents.py` model: pages of plain text, page boundaries, paragraph/block order, layout warnings (columns suspected, tables, text boxes, headers/footers), character count | `adapters/extract.py`: pdfplumber with word coordinates and x-clustering; python-docx including tables, headers/footers, and `w:txbxContent` |
| `TermExtractor` | cleaned JD text, validated dictionary data | weighted, canonicalized terms with JD context spans | `core/terms.py`: rule-based n-grams plus the injected dictionary |
| `SuggestionProvider` | finished report | 3–5 prioritized suggestions tied to finding ids | `core/suggestions.py`: templates driven by findings |

The `Extractor` protocol is the reason `core/` stays free of document libraries.
Everything downstream — sections, terms, score, alignment, checks, the ATS view
— consumes the normalized extracted document, not a PDF or DOCX object.

The future LLM seam is `TermExtractor` or `SuggestionProvider`; the core pipeline
does not change either way. Not built in v1.

## One-command run and build

Runtime, for anyone who clones the repo:

```
uv run ats
```

`uv run` syncs the Python environment (internet required once), then the
launcher:

1. Checks that `src/ats_scanner/static/index.html` exists. If not, it prints the
   exact rebuild command and exits rather than serving a blank page.
2. Binds to `127.0.0.1:8000`, falling back to `8765` if the port is taken.
3. Opens the browser.

Only uv is required at runtime. Node is not, because `src/ats_scanner/static` is
committed.

Build, for development:

```
uv run ats-build
```

This runs `npm ci` (internet required once) and `npm run build` in `web/`. Vite
writes directly to `src/ats_scanner/static` (with `emptyOutDir`), and the OpenAPI
type generation step writes `web/src/api/types.ts`. No copy step exists, so
there is no second copy to drift.

Development loop:

```
uv run ats-dev      # FastAPI with reload
npm run dev         # Vite dev server, proxies /api to FastAPI
```

The committed `src/ats_scanner/static` is only produced by `uv run ats-build`.
Nothing else writes to it.

The running app makes no outbound requests. Installing dependencies (`uv sync`)
and building the frontend (`npm ci`) need internet once.

## Type flow: Pydantic to TypeScript

1. Report models live in `core/report.py` (Pydantic). They are the single source
   of truth for the API shape.
2. FastAPI derives OpenAPI from those models.
3. `uv run ats-build` runs `openapi-typescript` against the app's OpenAPI
   document and writes `web/src/api/types.ts`. The file is committed.
4. The frontend imports those types; no hand-maintained duplicate interfaces.
5. A pytest test validates fixture report JSON against the Pydantic models, so a
   schema change fails tests rather than silently breaking the UI.
6. `tests/fixtures/report.sample.json` validates against the report models and is
   the fixture UI work builds against before the pipeline is complete.

Schema changes require bumping `schema_version`. The report also carries
`engine_version` and `dictionary_version`.

## Visual direction

"Paper and ink" document lab — not SaaS gradient.

- Warm paper background (`#F7F5F0`), ink type (`#14130F`), one vermilion accent
  for problems, desaturated teal for found.
- Display serif for the hero and verdict, UI sans for chrome, mono for extracted
  text and terms.
- Hairline rules, generous whitespace, no cards-on-cards, no stock art, no
  sparkles, no gradient mesh.
- Severity conveyed by icon and label, not colour alone.
- Fonts bundled locally (OFL). CSP `default-src 'self'`; zero outbound requests.
- shadcn/ui components are restyled, not used as-is.
- The ring shows the weighted percentage and the caption
  `Required terms: X of Y · Other terms: A of B · required terms count double.`
  It is a coverage indicator, never a badge of approval.
- Motion is minimal (120–180 ms), with `prefers-reduced-motion` respected.
- Keyboard navigable, labeled controls, AA contrast, works at 320 px and 1440 px.

## Implementation notes

- `.gitignore` must explicitly un-ignore `src/ats_scanner/static/`. The directory
  is generated output and is committed so that runtime needs no Node.
- Nothing in `src/ats_scanner/static/` is ever hand-edited. Change the React
  source and rebuild.
- The Vite build clears `outDir` before writing. Never run `uv run ats-build`
  while the server is running, or the running app will 404 the assets it was
  serving.
