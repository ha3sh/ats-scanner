# ATS Resume Scanner — v1 Specification

Project: `ats-scanner`. Python package: `ats_scanner` (src layout). Console
scripts: `ats`, `ats-build`, `ats-dev`.

Status: plan of record. Nothing implemented yet.

v1 is a local-only tool that compares one resume against one job description and
reports transparent, deterministic findings. It does not claim to reproduce any
employer's applicant tracking system.

## 1. Scope

### In scope

- One resume, PDF or DOCX, uploaded by the job seeker.
- One pasted plain-text job description.
- Single-user, single-page local web app.
- English only.
- **Software/tech roles only.** The skills dictionary is scoped to software and
  tech job families (languages, frameworks, infrastructure, data, tooling,
  practices, and common role titles). Other domains are out of scope for v1.
- Deterministic scoring: the same resume and JD always produce the same report.

### Out of scope

- OCR for scanned or image-only PDFs.
- Fetching a JD from a URL, LinkedIn import, or any network retrieval.
- Accounts, history, saved reports, database, analytics, PDF export, charts.
- LLM-based scoring or suggestions. The seam exists; the implementation does not.
- Bulk/recruiter mode, candidate ranking, multi-resume comparison.
- Internationalization, non-English resumes and JDs.
- Hosted deployment. If the tool is ever hosted, the privacy guarantees in
  section 6 must be revisited first.
- Non-tech occupations and their skill vocabularies.

## 2. User flow

1. The user runs `uv run ats`. The launcher binds to `127.0.0.1` and opens the
   browser.
2. Upload screen: a drop zone for one PDF or DOCX, a textarea for the JD, the
   privacy note, and the limits (5 MB, 10 pages, 20k JD characters).
3. The user submits. While the request is in flight the UI shows an
   indeterminate "Analyzing locally…" state with an elapsed timer. No staged or
   fake progress.
4. The report screen appears with the layout described below.
5. A "What the ATS sees" tab shows the plain extracted text.
6. Refreshing the page drops the report. There is no history and nothing to
   delete.

### Report screen contents

Left rail, sticky:

- One-line verdict and which resume/JD the report is based on.
- Headline metric as a ring showing the **weighted coverage percentage**, with
  the definition visible on the same screen. The caption under the ring reads:
  `Required terms: X of Y · Other terms: A of B · required terms count double.`
  There is no standalone fraction such as "31 of 41 terms".
- The top 3–5 prioritized fixes, each tied to a finding.

Main column:

- Matched terms, with the resume context where each was found.
- Missing terms, each with the JD sentence it came from.
- Section detection summary.
- Format and parse findings grouped by severity, each with evidence and a fix.
- Title/seniority and experience alignment as **informational findings**,
  visually separate from the headline. They never change the score.

Full width: the "What the ATS sees" tab.

Footer: the "what this cannot tell you" block.

### Designed error states

Each error is a real screen, not a stack trace: unsupported file type, file too
large, too many pages, encrypted PDF, no extractable text, malformed DOCX, JD
too short, JD too long, invalid request. The message says what happened and what
to do next.

## 3. Scoring

The headline is **"JD term coverage"**, displayed as a ring showing the weighted
percentage. It is never labeled "ATS score" anywhere in the UI.

The headline is weighted term coverage only. Title/seniority and experience
alignment are informational findings, reported separately in `report.alignment`,
and are not part of the score.

### Pipeline

1. **Clean the JD.** Strip EEO/legal, benefits, and company-boilerplate sections
   by heading and cue detection, so "dental insurance" and "equal opportunity
   employer" do not enter the denominator.
2. **Extract candidate terms.** Tokenize, lowercase, strip punctuation, collapse
   hyphen/space variants, apply simple plural and gerund normalization. Take
   1–3-grams, drop stopwords, dedupe by maximal munch so "machine learning" does
   not also count as "learning". Cap at about 60 terms, prioritizing weight then
   frequency.
3. **Canonicalize.** Merge terms through a hand-curated
   `src/ats_scanner/data/dictionary.json` of roughly 250–350 software/tech skills
   with aliases (`postgres → postgresql`, `k8s → kubernetes`). The dictionary is
   versioned and inspectable. It is loaded once in the app wiring, validated with
   a Pydantic model, and passed into core functions as an argument. `core/` does
   no file I/O.
4. **Classify required vs other.**
   - A term is **required** if it sits under a requirements-type heading
     (Requirements, Qualifications, Must have) or appears in a sentence
     containing a required cue ("required", "must", "minimum", "proficiency in").
   - A **Preferred**, **Nice to have**, or **Bonus** heading means **other**,
     even if the sentence also contains a cue.
   - Known edge case: negation. "X is not required" contains the cue "required"
     and is classified as required by v1's literal matching. There is no
     negation parsing; this is documented as a known limitation.
5. **Weight.** 2.0 for required terms, 1.0 for other terms.
6. **Match.** Exact normalized tokens, alias map, singular/plural equivalence,
   hyphen/space equivalence.
7. **Score.**

### Formula

```
coverage = Σ weight(matched terms) / Σ weight(all terms)
```

The ring shows the weighted percentage from this formula. The report exposes the
numerator, the denominator, the integer percentage, and per-class counts:

- `score.pct` — weighted coverage percentage
- `score.covered_weight`, `score.total_weight`
- `score.required.covered`, `score.required.total`
- `score.other.covered`, `score.other.total`
- `score.definition` — the formula itself, always visible next to the ring

The UI caption is always
`Required terms: X of Y · Other terms: A of B · required terms count double.`

### Near matches

Near misses (edit distance 1, term length ≥ 6) are shown as "possible match —
not counted". They never enter the score. This is the anti-flattery mechanism.

### Alignment checks

These live in `src/ats_scanner/core/alignment.py` and are informational only.
`score.py` computes coverage and nothing else. The report keeps `alignment`
separate from `score`.

- **Title/seniority.** Compare JD title tokens against the resume headline and
  most recent titles; ladder intern → junior → mid → senior → lead → principal.
  Mismatches are informational findings, not score.
- **Experience.** Parse "X+ years" from the JD and estimate total months from
  resume date ranges; report `~6 yrs detected vs 5+ requested`. Informational
  only, clearly labeled an estimate.

### Determinism

No randomness, no network, no model inference. The dictionary version and engine
version are returned with every report so two reports can be compared honestly.

## 4. Findings

Every finding carries an id, severity (`critical`, `warning`, `info`), title,
detail, evidence snippet, location (page, paragraph, or section), and a
suggested fix. No vibes, no unsupported claims.

1. No email detected.
2. No phone detected.
3. Contact information only in a header or footer.
4. Multi-column layout suspected (PDF) or column section breaks (DOCX).
5. Tables present.
6. Text boxes or shapes present.
7. Ambiguous dates ("Summer 2023") or missing dates in experience entries.
8. Non-standard section headings.
9. Decorative glyphs, emoji, arrows, or ligatures.
10. Very long resume (more than 2 pages) — informational, low severity.

Image-only or no-extractable-text documents are a hard error, not a finding.

Alignment checks are reported under `alignment`, not mixed into the format
findings list.

### Sections detected

Contact, summary, experience, education, skills, projects, certifications. Each
is reported as found or not found, with the heading text that triggered it.

### "What the ATS sees"

A first-class tab showing the plain extracted text with page markers, character
count, extraction method, and warnings (for example "column order suspected on
page 1"). A toggle highlights matched terms. Matched spans are returned as
code-point offsets in the extracted text; the frontend converts via
`Array.from` so emoji and other non-BMP characters cannot shift highlights.

This view is the ground truth: whenever layout detection is uncertain, the text
order shown here is what the report reasons about.

## 5. API

All endpoints are local. The server binds to `127.0.0.1` only.

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/health` | GET | Version, engine version, dictionary version, limits |
| `/api/analyze` | POST | Multipart `resume` file plus form field `job_description`; returns the report |

### File validation

- Check the **file signature**, not just extension or content type. PDF must
  begin with the PDF header; DOCX must be a ZIP (`PK` signature) containing a
  valid OOXML package.
- Cap the **uncompressed size** of a DOCX. Beyond the cap, return `bad_docx`.
- Check the **page count before extracting text**, so an oversized PDF fails
  fast with `too_many_pages`.
- A signature or structure mismatch is rejected even when the extension and
  content type claim otherwise.

### Report shape

- `schema_version`, `engine_version`, `dictionary_version`
- `meta`: filename, size, pages, extraction method, duration, warnings
- `verdict`: one-line sentence
- `score`: weighted percentage, covered weight, total weight, required
  {covered, total}, other {covered, total}, definition
- `terms.matched[]`: term, canonical form, weight, JD context, resume context,
  resume span
- `terms.missing[]`: term, weight, JD context
- `terms.near_misses[]`: term, found variant, distance, counted = false
- `sections[]`: name, found, heading text
- `findings[]`: id, severity, title, detail, evidence, location, fix
- `suggestions[]`: finding id, text
- `alignment`: title, seniority, experience — informational, separate from
  `score`
- `extracted_text`: pages with text, character count, method, warnings
- `disclaimers`

### Error codes

| Code | HTTP | When |
| --- | --- | --- |
| `unsupported_type` | 415 | Not PDF or DOCX, or signature does not match |
| `too_large` | 413 | Over 5 MB |
| `too_many_pages` | 422 | Over 10 pages |
| `encrypted_pdf` | 422 | Password-protected |
| `no_extractable_text` | 422 | Scanned or empty document |
| `bad_docx` | 422 | Malformed DOCX, invalid ZIP/OOXML, or uncompressed size over the cap |
| `jd_too_short` | 422 | JD under the minimum length |
| `jd_too_long` | 422 | JD over 20k characters |
| `invalid_request` | 422 | Missing or malformed request fields |

Each error response carries the code and one human sentence. FastAPI's own
request-validation errors are mapped into the same error envelope, so the client
sees one error shape regardless of where validation failed. No document text in
error messages or logs.

### Limits

5 MB per file, 10 pages, 20k characters of JD text.

### Headers

`Cache-Control: no-store` on analyze responses. No `X-Powered-By`.

## 6. Privacy guarantees

**Your resume and job description are never written to disk by this app.**

- Uploads are held in memory (`BytesIO`) for the duration of the request.
- No temp files, no database, no cache directory, no history.
- Python may write `.pyc` files and uv may write its cache. Neither contains
  user content, and the app does not write user content anywhere.
- The running app makes no outbound requests and binds to `127.0.0.1` only.
- Installing dependencies (`uv sync`) and building the frontend (`npm ci`) need
  internet once. Once installed, analysis runs entirely offline.
- Logs contain filename, size, duration, and error codes only — never document
  text, JD text, or contact details.
- No accounts, no telemetry, no third-party scripts. Fonts and all assets are
  bundled locally; CSP is `default-src 'self'`.
- Tests assert the claim: during an analysis, patch socket connect calls to
  raise and assert none occur. A separate trace asserts no user-content files
  are created under the working directory or the temp directory.

## 7. What this cannot tell you

> This report has no access to any real ATS and no recruiter judgment. It is
> heuristic keyword coverage, not a guarantee. It cannot tell you how a specific
> employer's system is configured, which keywords that system weights, or
> whether you will be interviewed. Use it to find gaps and parsing risks, not as
> a verdict on your application.

## 8. README outline

The README must state:

- What the tool does, and that v1 targets software/tech roles and English only.
- Requirements: uv at runtime; Node only for rebuilding the frontend.
- Install: `uv sync` (internet required once).
- Build, for developers: `uv run ats-build` (internet required once for
  `npm ci`).
- Run: `uv run ats`.
- Privacy: "Your resume and job description are never written to disk by this
  app." The running app makes no outbound requests and binds to `127.0.0.1`
  only. Python may write `.pyc` files and uv its cache; neither contains user
  content.
- Limits: 5 MB, 10 pages, 20k JD characters.
- How the score is computed, including that required terms count double, and
  that alignment is informational and outside the score.
- What the tool cannot tell you.
- Dev commands: `uv run ats-dev`, `npm run dev`, `uv run check`.
