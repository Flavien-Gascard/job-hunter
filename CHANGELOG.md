# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Each entry says what changed and
why; the longer reasoning behind design choices is in
[docs/decisions.md](docs/decisions.md).

## [Unreleased]

## [0.1.0] - 2026-10-28

First working version (MVP): fetch jobs, score them, tailor the resume, export.

### Added

**Job ingestion**
- Source adapters for Greenhouse and Lever public job-board feeds (per company,
  no key), Remotive (remote jobs by keyword) and Adzuna (US aggregator, free
  key). Each adapter has a pure `parse()` that maps the source's JSON to one
  shared `Job` shape, so a new source is one small file.
- HTML-to-text cleanup for descriptions, including Greenhouse's double-escaped
  HTML.
- Title include/exclude filter in `config/sources.json`, because company feeds
  list every opening (sales, legal…) and only engineering roles matter here.
- Each source runs on its own: one failing feed is reported in the refresh
  summary and the others still load.
- Background refresh loop (every 6 hours by default) plus a **Fetch jobs**
  button.

**Deduplication**
- Stable dedupe key from normalized company (drops Inc/LLC/Corp…), title
  (drops parentheticals like "(Remote)", expands "Sr." → "senior") and location
  (city only, or "remote").
- When the same job appears on several sources, the record with the fullest
  description wins (Adzuna only has snippets) and every source link is kept.
- Re-fetching updates existing jobs instead of duplicating them, and never
  replaces a long description with a shorter one.

**AI features (Claude API)**
- Resume import: upload a `.docx`, Claude converts it to structured JSON,
  copying the wording exactly.
- Match scoring: 0–100 score with a one-line verdict, strengths and gaps. Jobs
  are sorted by score. **Score 10** scores the newest unscored jobs, capped at 25
  per click to keep cost predictable; it stops at the first error rather than
  repeating a bad-key error for every job.
- Resume tailoring: Claude proposes rewrites, removals and a per-role bullet
  order for one job, using only experience already on the resume.
- All three calls use structured outputs (`messages.parse` with Pydantic
  models), so responses are validated JSON, not scraped text.
- Refusal, truncation and API errors become clear messages in the UI (HTTP 502
  with the reason). Server-side model fallback is enabled for declined
  requests.
- Scores and tailored results are cached per resume version (a hash of the
  resume), so editing or re-importing the resume invalidates them.

**Guardrails on tailoring**
- Edits must target something that exists (profile, a bullet id, a skills group).
  Anything else is rejected and listed under "blocked by the safety checks".
- A skills edit may only reorder or drop skills; adding one is rejected.
- A rewrite containing a number that isn't in the original is flagged
  ("Check this: numbers not in the original") and left unticked by default.
- A suggested bullet order is applied only if it is an exact permutation of
  that role's bullets.

**Export and tracking**
- `.docx` export of the accepted edits, US Letter, styled like the source
  resume, named `<Name>_<Company>_<Title>.docx`.
- Job status: new, saved, applied, interview, offer, rejected, hidden.

**Front end (React + TypeScript + Vite)**
- Three panels: resume, jobs (search, remote and status filters, score badges,
  source chips), tailoring (score card, before/after diff for each edit,
  checkboxes, warnings, blocked suggestions, export).
- Hovering an edit highlights the matching line in the resume panel.
- Below 1000px the panels become tabs, so it works on a phone.
- Light and dark themes follow the system setting.

**Project**
- 21 backend tests (pytest) against recorded API responses and a fake Claude:
  parsing per source, dedupe rules, guardrails, and the full HTTP flow
  fetch → score → tailor → export.
- `README.md`, `docs/decisions.md`, `.env.example`, sample resume in
  `config/resume.example.json`. Personal data (`data/`, `.env`) is git-ignored.

### Fixed (found while testing the UI before release)
- A posting returned by two searches on the same source showed that source
  twice; links are now unique per source and posting.
- The search box was cut off on desktop; it now gets its own row.
- Suggested edits showed internal ids ("Bullet r0b0"); they now show the
  company, year and bullet label.

### Known limitations
- Adzuna returns only a description snippet, so scores for Adzuna-only jobs are
  less reliable.
- Company slugs in `config/sources.json` are examples and need checking against
  each company's real job board.
- No login. It is a single-user app meant to run on your own machine.
