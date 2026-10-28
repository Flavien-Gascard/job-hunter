# Design decisions

Short records of the choices that shaped Job Hunter: the context, what was
decided, and the trade-off. Newest at the bottom. Useful for code review, and
for explaining the project in an interview.

---

## 1. Job data from official feeds, not scraping

**Context.** LinkedIn, Indeed and Glassdoor have no public job-search API and
their terms forbid scraping. Scrapers also break whenever the HTML changes.

**Decision.** Use sources that publish data on purpose: company applicant
tracking systems (Greenhouse, Lever) through their public JSON feeds, Remotive
for remote roles, and Adzuna as a free aggregator.

**Trade-off.** Coverage depends on which companies you follow. In exchange the
data is clean, current, straight from the employer, and allowed. Paid Google
Jobs wrappers (SerpApi, JSearch) can be added later as another adapter.

## 2. One adapter per source, with a pure `parse()`

**Decision.** Every source has a `parse(payload) -> list[Job]` with no I/O and a
thin `fetch()` around it. All sources map to one `Job` model.

**Why.** Parsing is where source quirks live (Greenhouse double-escapes HTML,
Lever uses millisecond timestamps, Adzuna has snippets only). Keeping it pure
means it is tested against recorded responses without the network, and adding
a source is one file plus one fixture.

## 3. Dedupe on a normalized key, keep the richest copy

**Context.** The same posting shows up on the company board and on aggregators,
with small differences: "Sr. Data Engineer" vs "Senior Data Engineer (Remote)",
"Acme" vs "Acme, Inc.".

**Decision.** Key = hash of normalized company + title + location (or
"remote"). Among duplicates keep the longest description and record every
source link. The key is the job's primary key, so re-fetching is an upsert.

**Trade-off.** Exact matching on normalized fields misses some fuzzy duplicates
(e.g. different title wording for the same role). That was chosen over fuzzy
matching because a wrong merge hides a real job, which is worse than seeing a
duplicate.

## 4. Structured outputs for every Claude call

**Decision.** Import, score and tailor all call `messages.parse` with a Pydantic
model as the output format, so the API returns JSON that matches the schema.

**Why.** No regex over model text, no "please reply in JSON" retries. The same
models type the API, the database payloads and the front end.

## 5. Claude proposes, the server decides

**Context.** A tailored resume that claims something untrue hurts the candidate
in the interview. Prompt instructions alone are not a guarantee.

**Decision.** Claude's edits are treated as proposals and checked in
`tailoring.py` before the user sees them:
- edits must point at an existing profile, bullet id, or skills group (Claude
  sees ids like `r0b3` next to each bullet for this reason);
- skills edits may reorder or drop, never add;
- numbers in a rewrite must already exist in the original, otherwise the edit is
  flagged and left unticked;
- a new bullet order must be an exact permutation.

The user then accepts edits one by one, and only accepted edits are applied.

**Why the number check.** Metrics are the most persuasive and the easiest thing
for a model to "improve". Comparing the sets of numbers is cheap, deterministic,
and catches that whole class of problem.

## 6. AI results cached per resume version

**Decision.** Scores and tailored results are stored with a hash of the resume
they were computed from.

**Why.** Re-importing or editing the resume automatically makes old scores
stale (they simply stop matching) without any cleanup code, and switching back
to an earlier resume brings its results back for free.

## 7. Model, effort and cost controls

**Decision.** Default model `claude-opus-5-5`, configurable with
`JOBHUNTER_MODEL`. Scoring and import run at low effort (short, factual tasks);
tailoring runs at high effort (the quality matters). Batch scoring is capped at
25 jobs per click and stops at the first error. Server-side fallback is enabled
so a request a safety classifier declines is retried on a fallback model
instead of failing.

**Trade-off.** Scoring everything automatically on fetch would be more
convenient but would spend money on jobs you would never open, so scoring stays
user-triggered.

## 8. SQLite and a single process

**Decision.** One FastAPI process with SQLite and an in-process refresh loop; the
built React app is served by the same process.

**Why.** It is a single-user tool. SQLite needs no setup, the whole state is one
file, and there is no queue or scheduler to run. Moving to Postgres and a worker
is a contained change if it ever becomes multi-user.

## 9. Personal data never enters git

**Decision.** The real resume (`data/resume.json`), the database and `.env` are
git-ignored. The repository ships a fictional `config/resume.example.json` that
the app shows until you import your own.

## 10. Tests run offline and free

**Decision.** Tests use recorded responses for each source, an `httpx`
mock transport for the fetch layer, and a fake `ai` module, then drive the real
FastAPI app end to end (fetch → filter → dedupe → score → tailor → export →
open the `.docx`).

**Why.** They are fast and deterministic, need no API keys, and test the parts
most likely to break: source parsing, dedupe rules and the guardrails.
