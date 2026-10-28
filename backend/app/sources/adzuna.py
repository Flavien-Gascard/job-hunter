"""Adzuna job search aggregator. Needs a free app id and key from developer.adzuna.com.

Docs: https://developer.adzuna.com/docs/search
"""

import httpx

from ..models import Job
from .base import looks_remote

URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"


def parse(payload: dict) -> list[Job]:
    jobs = []
    for item in payload.get("results", []):
        location = (item.get("location") or {}).get("display_name", "")
        title = item.get("title", "").strip()
        jobs.append(
            Job(
                source="adzuna",
                source_id=str(item["id"]),
                title=title,
                company=(item.get("company") or {}).get("display_name", ""),
                location=location,
                remote=looks_remote(location, title),
                url=item.get("redirect_url", ""),
                # Adzuna only returns a snippet; the full text is on the employer's page.
                description=item.get("description", ""),
                salary=_salary(item),
                posted_at=item.get("created", ""),
            )
        )
    return jobs


def _salary(item: dict) -> str:
    lo, hi = item.get("salary_min"), item.get("salary_max")
    if not lo:
        return ""
    return f"USD {int(lo):,}–{int(hi or lo):,}"


def fetch(client: httpx.Client, cfg: dict, app_id: str, app_key: str) -> list[Job]:
    jobs = []
    for what in cfg.get("what", []):
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": what,
            "results_per_page": cfg.get("results_per_page", 50),
            "max_days_old": cfg.get("max_days_old", 14),
        }
        if cfg.get("where"):
            params["where"] = cfg["where"]
            params["distance"] = cfg.get("distance_km", 50)
        resp = client.get(URL.format(country=cfg.get("country", "us")), params=params)
        resp.raise_for_status()
        jobs.extend(parse(resp.json()))
    return jobs
