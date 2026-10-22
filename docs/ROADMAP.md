# ATS Resume Scanner — v1 Roadmap

Ten working days. v1 is one resume + one pasted JD, software/tech roles, English,
local only.

Tests and fixtures are written test-first alongside each day's code. Each day's
exit criterion includes its tests, so Day 10 is not the day testing starts.

## Ten days

| Day | Work | Exit criterion |
| --- | --- | --- |
| 1 | uv scaffold with `ats_scanner` src layout and `ats` / `ats-build` / `ats-dev` scripts; tooling deliverables: `AGENTS.md`, `opencode.json` with context7 and playwright MCP, the frontend-design skill, and a task runner exposing `check`; FastAPI ↔ Vite dev loop; static serving from `src/ats_scanner/static`; launcher; error envelope | `uv run ats` serves the shell; `uv run check` runs lint, types, and tests; tooling files exist and MCP servers are configured |
| 2 | In-memory PDF/DOCX extraction in `src/ats_scanner/adapters/extract.py`; signature validation, DOCX uncompressed-size cap, page count before text extraction; thin vertical slice to the ATS view | Upload → raw extracted text on screen; wrong-signature and oversized files rejected with the right codes |
| 3 | Sections, contact parsing, page/paragraph mapping; `tests/fixtures/report.sample.json` validated against the Pydantic report models | Correct sections on 6 fixtures; sample report validates, so UI work can start against it |
| 4 | Layout heuristics, format findings | Findings with evidence render |
| 5 | JD cleaning, term extraction, tech dictionary at `src/ats_scanner/data/dictionary.json` with a load-and-validate test, dedupe | Term list sane on 8 JDs; dictionary validation test passes |
| 6 | Matching, spans, near-miss, weighted coverage in `core/score.py`, alignment in `core/alignment.py` | Deterministic coverage tests pass; alignment changes affect `alignment` only, never `score` |
| 7 | Suggestions in `core/suggestions.py`, cannot-tell block, schema freeze, TypeScript type generation | Contract locked; `web/src/api/types.ts` regenerated and committed |
| 8 | Design system, upload screen, report rail, ring | Polished happy path |
| 9 | Terms/findings/sections UI, ATS tab, responsive, a11y, error states | Keyboard, 320 px, 1440 px pass |
| 10 | Privacy proofs, README, release zip, demo | Socket-patch and no-user-content-file proofs pass; README matches SPEC §8; a friend can run it |

## Cut if behind

In order, from the least damaging:

1. Near-miss matches.
2. Highlight toggle in the ATS view.
3. Experience-years estimate.
4. DOCX column detection.
5. Second display font.

Extraction quality and the results screen must not slip. Days 8–9 have no
buffer.

## Risks

- **PDF layout variance.** Worst risk. Treat column detection as "suspected" and
  always show the extracted text as ground truth.
- **Dictionary gaps.** Show uncovered JD terms and keep
  `src/ats_scanner/data/dictionary.json` inspectable and versioned. Scope is
  software/tech, so non-tech JDs will score poorly; that is a stated limitation,
  not a bug.
- **UI polish time.** The design work is real work, not decoration. Cut from the
  list above before cutting polish.
