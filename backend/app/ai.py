"""The three Claude calls: import a resume, score a job, tailor the resume to a job.

Each call uses structured outputs (messages.parse with a Pydantic model), so the
response is validated JSON rather than text we have to scrape.
"""

from functools import lru_cache

import anthropic
from pydantic import BaseModel

from .config import settings
from .models import MatchScore, Resume, TailorResult

# Opt into server-side fallback: if a safety classifier declines a request, the
# API retries it on a fallback model instead of returning a refusal.
_FALLBACK = {
    "extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
    "extra_body": {"fallbacks": "default"},
}


class AIError(RuntimeError):
    """A Claude call failed in a way the UI should show to the user."""


@lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _parse[T: BaseModel](system: str, prompt: str, schema: type[T], effort: str) -> T:
    try:
        resp = _client().messages.parse(
            model=settings.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            **_FALLBACK,
        )
    except anthropic.AuthenticationError as e:
        raise AIError("Claude API key is missing or invalid (set ANTHROPIC_API_KEY).") from e
    except anthropic.RateLimitError as e:
        raise AIError("Claude API rate limit hit; try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AIError("Could not reach the Claude API.") from e
    except anthropic.AnthropicError as e:  # e.g. no credentials configured at all
        raise AIError(str(e)) from e

    if resp.stop_reason == "refusal":
        raise AIError("Claude declined this request.")
    if resp.stop_reason == "max_tokens":
        raise AIError("Claude's answer was cut off; try again.")
    if resp.parsed_output is None:
        raise AIError("Claude returned an answer that did not match the expected format.")
    return resp.parsed_output


def resume_to_text(resume: Resume) -> str:
    """Render the resume with ids so Claude can point edits at exact bullets."""
    lines = [f"NAME: {resume.name}", f"[profile] {resume.profile}", "", "SKILLS"]
    lines += [f"[skills:{g.name}] {' | '.join(g.items)}" for g in resume.skills]
    lines.append("\nEXPERIENCE")
    for role in resume.experience:
        lines.append(f"({role.id}) {role.title} | {role.company} | {role.start} – {role.end}")
        for b in role.bullets:
            text = f"{b.label}: {b.text}" if b.label else b.text
            lines.append(f"  [{b.id}] {text}")
    if resume.certifications:
        lines.append("\nCERTIFICATIONS\n" + "\n".join(resume.certifications))
    if resume.education:
        lines.append("\nEDUCATION\n" + "\n".join(resume.education))
    return "\n".join(lines)


def job_to_text(job: dict) -> str:
    return (
        f"TITLE: {job['title']}\nCOMPANY: {job['company']}\nLOCATION: {job['location']}"
        f"{' (remote)' if job['remote'] else ''}\nSALARY: {job.get('salary') or 'not listed'}\n\n"
        f"DESCRIPTION:\n{job['description'] or '(no description provided)'}"
    )


IMPORT_SYSTEM = """You convert resumes into structured data. Copy the candidate's \
wording exactly; do not summarize, improve or correct anything. When a bullet \
starts with a short bold lead-in followed by a colon, put the lead-in in `label` \
and the rest in `text`. Leave every `id` field empty."""


def import_resume(text: str) -> Resume:
    return _parse(IMPORT_SYSTEM, f"Resume text:\n\n{text}", Resume, effort="low")


SCORE_SYSTEM = """You are an experienced technical recruiter. Score how well the \
candidate fits the job on a 0-100 scale: 90+ means a near-perfect match a \
recruiter would call today, 70-89 a strong match, 50-69 a stretch, below 50 a \
poor fit. Weigh required skills and seniority most, then domain, then nice-to-\
haves. Base the score only on what the resume shows. Keep strengths and gaps to \
at most four short items each."""


def score_job(resume: Resume, job: dict) -> MatchScore:
    prompt = f"<resume>\n{resume_to_text(resume)}\n</resume>\n\n<job>\n{job_to_text(job)}\n</job>"
    result = _parse(SCORE_SYSTEM, prompt, MatchScore, effort="low")
    result.score = max(0, min(100, result.score))
    return result


TAILOR_SYSTEM = """You tailor a candidate's resume to one job posting. The \
candidate will review every change before sending it, and anything untrue \
would hurt them in an interview, so:

- Work only with experience already on the resume. Never add a skill, tool, \
employer, responsibility or number the resume does not already contain. You \
may reword, emphasize, shorten, reorder, or remove.
- Mirror the job's vocabulary where the resume already supports it (e.g. if \
the job says "data platform" and a bullet describes one, use that phrase).
- Rewrite the profile so its first sentence speaks to this role.
- Propose removing bullets that are irrelevant to this job when the resume is \
long; never remove more than a third of a role's bullets.
- A skills edit may only reorder or drop items from that group.
- Keep each bullet's "Label: text" shape when it has a label.

Each edit's `target` is an id shown in square brackets: `profile`, a bullet id \
like `r0b3`, or `skills:<group name>`. Give a one-line `reason` tied to the job \
for each edit. Suggest a bullet order per role only when it helps, listing all \
of that role's bullet ids. Aim for the 5-12 edits that matter most."""


def tailor(resume: Resume, job: dict) -> TailorResult:
    prompt = f"<resume>\n{resume_to_text(resume)}\n</resume>\n\n<job>\n{job_to_text(job)}\n</job>"
    return _parse(TAILOR_SYSTEM, prompt, TailorResult, effort="high")
