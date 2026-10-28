"""Remotive remote-jobs API, searched by keyword. No key needed.

Docs: https://remotive.com/api-documentation (asks for a link back and light polling).
"""

import httpx

from ..models import Job
from .base import html_to_text

URL = "https://remotive.com/api/remote-jobs"


def parse(payload: dict) -> list[Job]:
    return [
        Job(
            source="remotive",
            source_id=str(item["id"]),
            title=item.get("title", "").strip(),
            company=item.get("company_name", ""),
            location=item.get("candidate_required_location") or "Remote",
            remote=True,
            url=item.get("url", ""),
            description=html_to_text(item.get("description", "")),
            salary=item.get("salary", ""),
            posted_at=item.get("publication_date", ""),
        )
        for item in payload.get("jobs", [])
    ]


def fetch(client: httpx.Client, searches: list[str], limit: int = 50) -> list[Job]:
    jobs = []
    for term in searches:
        resp = client.get(URL, params={"search": term, "limit": limit})
        resp.raise_for_status()
        jobs.extend(parse(resp.json()))
    return jobs
