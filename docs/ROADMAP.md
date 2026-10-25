# ATS Resume Scanner — v1 Roadmap

Ten working days. v1 is one resume + one pasted JD, software/tech roles, English,
local only.

Principles: every day's feature is visible in the UI the same day (vertical
slices — the minimal frontend shell lands on Day 1 and every later feature
builds on it; design tokens land no later than Day 3, and Day 9 is an
accessibility/polish pass, not the first UI build).
Tests and fixtures are written test-first: first synthetic fixtures on Day 2,
eval-harness skeleton by Day 4, more fixtures every day, final pass on Day 10.
Wording rule: no vendor names in the UI and the headline is never called an
"ATS score" — see docs/PRODUCT_PLAN.md.

Day 1 is **in progress**: the project skeleton and tooling exist; the health
endpoint, error envelope, launcher, and minimal frontend shell remain.

## Ten days

| Day | Work | Exit criterion |
| --- | --- | --- |
| 1 (in progress) | REMAINS: `/api/health` (versions + limits), unified error envelope, the `ats` launcher (bind 127.0.0.1, open browser), minimal frontend shell served from `src/ats_scanner/static`, CI workflow moved to this day: GitHub Actions running `uv run poe check` on push and PRs | `uv run ats` serves the shell; `/api/health` answers; designed errors render in one envelope; CI green on ubuntu-latest and windows-latest (Python 3.12); `uv run poe check` passes |
| 2 | In-memory PDF/DOCX extraction in `adapters/extract.py`; signature validation, DOCX uncompressed-size cap, page count before text extraction; raw text on screen under the "What the ATS sees" tab (with its caption); first synthetic fixtures (hand-made, exported from a word processor) — nothing more | Upload → raw extracted text on screen; wrong-signature and oversized files rejected with the right codes |
| 3 | Paper/ink design tokens (paper `#F7F5F0`, ink, vermilion/teal); row-order and column-order views, each captioned "possible extractor outputs"; sections and contact parsing | Two orders render side by side from the same file; sections/contact correct on fixtures; tokens applied app-wide |
| 4 | Eval-harness skeleton (fixtures → pipeline → expected results, one `*.expected.json` beside each fixture asserting a defined subset — section names found, finding ids, coverage numerator/denominator — never the whole report); page/paragraph mapping; `tests/fixtures/report.sample.json` validated against the Pydantic report models | Harness runs and fails loudly on fixture changes; sample report validates, so the UI can keep building against it |
| 5 | JD-cleaning diff view (before/after boilerplate strip); term extraction; tech dictionary at `src/ats_scanner/data/dictionary.json` with load-and-validate test | JD diff renders; term list sane on new fixtures; dictionary test passes |
| 6 | Matching, spans, near-miss (shown, never counted), weighted coverage in `core/score.py`; title/seniority and experience alignment in `core/alignment.py` as informational-only | Deterministic coverage tests pass; alignment renders separately and never affects `score` |
| 7 | Layout heuristics and format findings (columns suspected, tables, text boxes, headers/footers, icon-only contact, abbreviated/ambiguous date formats, heading degeneration) — all generic, evidence + fix, no vendor names | Findings with evidence render; new fixtures cover each finding |
| 8 | Evidence ledger with click-to-highlight spans; template suggestions in `core/suggestions.py` (3–5 fixes tied to finding ids); copy-report action; schema freeze; TypeScript type generation | Every count navigates to its span; report copied to clipboard; contract locked; `web/src/api/types.ts` regenerated and committed |
| 9 | Accessibility, responsive, error screens pass: keyboard-only, reduced motion, 320 px and 1440 px, all designed error states | A11y and responsive checks pass; every error code has a designed screen |
| 10 | Final fixture pass (12–15 labeled synthetic cases through the harness), privacy proofs, determinism test + footer line, README per SPEC §8, release zip, demo | Socket-patch and no-user-content-file proofs pass; byte-identical rerun test passes; README matches SPEC §8; a friend can run it |

## Cut if behind

In order, from the least damaging:

1. Near-miss matches.
2. Click-to-highlight in the evidence ledger.
3. Experience-years estimate.
4. DOCX column detection (row/column redundancy on DOCX).
5. Second display font.

Extraction quality and the results screen must not slip. Days 8–10 have no
buffer; the eval-harness skeleton (Day 4) and CI (Day 2) are hard requirements,
not cuts.

## Risks

- **PDF layout variance.** Worst risk. Treat column detection as "suspected";
  always show the extracted text as ground truth, and frame row/column views as
  "possible extractor outputs" — never as what any real system does.
- **Dictionary gaps.** Show uncovered JD terms; keep `dictionary.json`
  inspectable and versioned. Scope is software/tech, so non-tech JDs will score
  poorly; that is a stated limitation, not a bug.
- **Fidelity creep.** No UI claim of reproducing any vendor's parsing; the
  wording rule exists to keep this honest.
- **UI polish time.** The design work is real work, not decoration. Cut from the
  list above before cutting polish.
