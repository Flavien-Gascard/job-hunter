"""Lever public postings API: one feed per company, no key needed.

Docs: https://github.com/lever/postings-api
"""

import httpx

from ..models import Job
from .base import iso_from_ms, looks_remote

URL = "https://api.lever.co/v0/postings/{site}"


def parse(site: str, payload: list[dict]) -> list[Job]:
    company = site.replace("-", " ").title()
    jobs = []
    for item in payload:
        cats = item.get("categories") or {}
        location = cats.get("location", "")
        sections = [item.get("descriptionPlain", "")]
        for block in item.get("lists", []):
            sections.append(block.get("text", ""))
        sections.append(item.get("additionalPlain", ""))
        jobs.append(
            Job(
                source="lever",
                source_id=f"{site}:{item['id']}",
                title=item.get("text", "").strip(),
                company=company,
                location=location,
                remote=item.get("workplaceType") == "remote" or looks_remote(location),
                url=item.get("hostedUrl", ""),
                description="\n\n".join(s for s in sections if s).strip(),
                salary=_salary(item.get("salaryRange")),
                posted_at=iso_from_ms(item.get("createdAt")),
            )
        )
    return jobs


def _salary(rng: dict | None) -> str:
    if not rng or not rng.get("min"):
        return ""
    return f"{rng.get('currency', '')} {rng['min']:,}–{rng.get('max', rng['min']):,}".strip()


def fetch(client: httpx.Client, sites: list[str]) -> list[Job]:
    jobs = []
    for site in sites:
        resp = client.get(URL.format(site=site), params={"mode": "json"})
        resp.raise_for_status()
        jobs.extend(parse(site, resp.json()))
    return jobs
