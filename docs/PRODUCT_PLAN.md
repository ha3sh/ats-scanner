# Product plan

The vision in three sentences: ats-scanner is a local document lab, not a scoring
widget — you see exactly what a plain-text extractor could pull from your file and
why each number in the report exists. Every count is auditable: every term,
finding, and suggestion links to evidence (the exact text span or JD sentence it
came from). It runs entirely on your machine, never writes your resume or job
description to disk, and never presents a made-up number as "the ATS score".

## Non-negotiables

- Runs fully on the user's machine; resume and JD are never written to disk or
  logged.
- Scoring is deterministic and explainable; every result links to evidence.
- The headline metric is never presented as "the ATS score" (see wording rule).
- A local LLM may only be proposed as an opt-in plugin behind a Protocol,
  disclosed in the UI, and off by default.
- Ideas come from other tools, not their code. Licenses noted in the landscape
  research: Resume Matcher (MIT), OpenResume (MIT).

## Wording rule

No vendor names (Workday, Greenhouse, Lever, iCIMS, Ashby, SmartRecruiters, or
any other ATS or tool) anywhere in the UI or in findings. The headline metric is
never called an "ATS score" — it is weighted JD term coverage. The generic word
"ATS" may appear where factual: in the product name and in the "What the ATS
sees" tab. Under that tab, the caption reads:

> Plain-text extraction, the way many parsers read a file. Real systems differ.

The row-order and column-order views are captioned "possible extractor outputs"
and are framed as what a text extractor could produce, never what a specific
system does.

## Tier 1 — one resume + one pasted JD, v1 (~10 working days)

Each day's feature is visible in the UI the same day (vertical slices). Fixtures
and eval-harness work is test-first and grows daily from Day 2. Day 1 is in
progress: only the bullet "skeleton and tooling" below is done.

| Day | Feature | One line | Effort |
| --- | --- | --- | --- |
| 1 (in progress) | Launcher, shell, health, error envelope, CI | DONE: uv skeleton, deps, poe tasks, pre-commit, guard test, MCP/skills config. REMAINS: `/api/health`, unified error envelope, the `ats` launcher (bind 127.0.0.1, open browser), minimal frontend shell served from `src/ats_scanner/static`, and the CI workflow (GitHub Actions, ubuntu-latest and windows-latest, Python 3.12, `uv run poe check` on push and PRs) | M |
| 2 | Extraction + "What the ATS sees" | In-memory PDF/DOCX extraction with signature/page validation; raw extracted text on screen under the ATS tab; first synthetic fixtures (hand-made, exported from a word processor) — nothing more | M |
| 3 | Paper/ink design tokens + row/column order views | Design tokens (paper `#F7F5F0`, ink, vermilion/teal accents) land no later than Day 3; the page rendered in document row order and column-clustered order, each captioned "possible extractor outputs" | M |
| 4 | Sections & contact + eval harness skeleton | Section/contact/page-paragraph mapping visible in the report; eval harness skeleton runs the pipeline over fixtures and compares to expected results; `tests/fixtures/report.sample.json` validates | M |
| 5 | JD-cleaning diff + terms | JD shown before/after boilerplate strip, so the denominator is auditable; term extraction + `dictionary.json` with a load-and-validate test | M |
| 6 | Weighted coverage + near-misses + alignment | Deterministic weighted coverage with exposed numerator/denominator; near-misses shown, never counted; title/seniority and experience alignment as informational findings outside the score | M |
| 7 | Format findings | Columns-suspected, tables, text boxes, headers/footers, icon-only contact, ambiguous/abbreviated date formats, heading degeneration — all generic, all with evidence + repair text | M |
| 8 | Evidence ledger + suggestions + clipboard | Click-to-highlight span on every count; 3–5 template fixes tied to finding ids; copy-report action (clipboard JSON); schema freeze; `web/src/api/types.ts` regenerated | M |
| 9 | Accessibility & polish pass | Keyboard-only, reduced-motion, 320 px + 1440 px, all designed error states — the UI has existed every day; this day is the polish pass, not first build | M |
| 10 | Proofs & release | Final pass: complete synthetic fixtures (12–15 labeled cases) against the harness, network and no-user-content-file proof tests, determinism hash (byte-identical rerun test plus small footer line, no re-run button), README per SPEC §8, release zip, a friend runs it | M |

## Tier 2 and Tier 3

- **Tier 2 (~10 days after v1):** profile-field simulation ("what the
  extractor could interleave, mapped as structured fields"), layout-fragility
  score with a published formula, dictionary browser, deeper findings — each
  independently shippable and additive to the report schema.
- **Tier 3 (beyond):** local-LLM `SuggestionProvider` adapter (opt-in,
  disclosed, off by default), public evaluation harness, and per-ATS findings
  behind a "labs" toggle worded "community reports, unverified", linking to
  sources — only after the deterministic core is battle-tested.

## Decisions and why

- **Profile-field simulation deferred to Tier 2.** The dual-order view delivers
  the core insight (what extraction can scramble); the simulated structured
  fields are additive value, not the v1 hook.
- **No per-ATS failure tags in Tier 1.** Vendor-internal parsing behavior cannot
  be verified from outside; encoding it as fact risks overclaiming. Revisit in
  Tier 3 behind a labs toggle that labels every item as "community reports,
  unverified" with a source link.
- **No local-LLM stub in Tier 1.** The `TermExtractor`/`SuggestionProvider`
  protocols and the core-purity guard test are already the seam; the plugin
  lands in Tier 3 as a real adapter, not a TODO.
- **No Hypothesis.** Tokenizer/coverage edge cases are enumerable; a
  parametrized test set plus labeled fixtures covers them deterministically
  without a new dev dependency. Revisit in Tier 2 only if a bug slip proves the
  need.
- **Determinism hash as test + footer, not a re-run button.** The guarantee is
  verified in CI and surfaced as a version/hash footer line; a re-run control
  adds UI surface for no added guarantee.

## Locked decisions (user, recorded)

- **DOCX column representation.** Table-cell-aware reading order; section and
  text-box breaks are the column signal. If a DOCX has no tables, text boxes,
  or section columns, show one order with the note "Same order for this file"
  instead of two identical-looking panels.
- **CI.** GitHub Actions on ubuntu-latest and windows-latest, Python 3.12,
  running `uv run poe check` on push and pull requests; scheduled at the end of
  Day 1.
- **Eval fixtures.** A `*.expected.json` beside each fixture asserts a defined
  subset (section names found, finding ids, coverage numerator/denominator),
  never the whole report. Fixtures are synthetic; hand-made fixtures exported
  from a word processor are preferred over adding a PDF-generation dependency.
  No generator dependency is added unless proposed and explicitly approved.
- **Clipboard export.** JSON only in Tier 1 — the plain Pydantic dump, no
  second serializer.
- **Frontend stack.** React + TypeScript (strict) + Vite, Tailwind,
  shadcn/ui restyled. Versions are not pinned in these docs; the Day 2 prompt
  chooses current stable versions via context7 or the npm registry. Constraint:
  the stack must work with Node 22.12; if anything needs a newer Node, it is
  flagged before changing anything.
