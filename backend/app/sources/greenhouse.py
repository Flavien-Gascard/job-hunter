"""Greenhouse public job board API: one feed per company, no key needed.

Docs: https://developers.greenhouse.io/job-board.html
"""

import httpx

from ..models import Job
from .base import html_to_text, looks_remote

URL = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"


def parse(board: str, payload: dict) -> list[Job]:
    company = payload.get("meta", {}).get("company_name") or board.replace("-", " ").title()
    jobs = []
    for item in payload.get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        jobs.append(
            Job(
                source="greenhouse",
                source_id=f"{board}:{item['id']}",
                title=item.get("title", "").strip(),
                company=item.get("company_name") or company,
                location=location,
                remote=looks_remote(location, item.get("title", "")),
                url=item.get("absolute_url", ""),
                description=html_to_text(item.get("content", "")),
                posted_at=item.get("first_published") or item.get("updated_at", ""),
            )
        )
    return jobs


def fetch(client: httpx.Client, boards: list[str]) -> list[Job]:
    jobs = []
    for board in boards:
        resp = client.get(URL.format(board=board), params={"content": "true"})
        resp.raise_for_status()
        jobs.extend(parse(board, resp.json()))
    return jobs
