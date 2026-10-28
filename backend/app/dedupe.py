"""Collapse the same posting seen on several sources into one record.

Two postings are the same job when company, title and location match after
normalization. Of the duplicates we keep the one with the fullest description
(aggregators like Adzuna only carry a snippet) and remember every source link.
"""

import hashlib
import re

from .models import Job

_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|company|plc|gmbh|group|holdings)\b\.?", re.I
)
_PAREN = re.compile(r"\([^)]*\)")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_TITLE_ALIASES = {"sr": "senior", "jr": "junior", "eng": "engineer", "mgr": "manager"}


def _squash(text: str) -> str:
    return _NON_WORD.sub(" ", text.lower()).strip()


def norm_company(name: str) -> str:
    return _squash(_COMPANY_SUFFIX.sub(" ", name))


def norm_title(title: str) -> str:
    # Drop parentheticals like "(Remote)" or "(m/f/d)" that vary between boards.
    words = _squash(_PAREN.sub(" ", title)).split()
    return " ".join(_TITLE_ALIASES.get(w, w) for w in words)


def norm_location(job: Job) -> str:
    if job.remote:
        return "remote"
    # "Wilmington, DE, United States" and "Wilmington, Delaware" -> "wilmington"
    return _squash(job.location.split(",")[0]) if job.location else ""


def dedupe_key(job: Job) -> str:
    raw = "|".join([norm_company(job.company), norm_title(job.title), norm_location(job)])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def dedupe(jobs: list[Job]) -> list[tuple[str, Job, list[dict]]]:
    """Return (key, best job, all source links) for each distinct posting."""
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault(dedupe_key(job), []).append(job)
    out = []
    for key, group in groups.items():
        best = max(group, key=lambda j: len(j.description))
        # Two searches on the same source can return the same posting; list it once.
        links = list({(j.source, j.source_id): {"source": j.source, "source_id": j.source_id, "url": j.url}
                      for j in group}.values())
        out.append((key, best, links))
    return out
