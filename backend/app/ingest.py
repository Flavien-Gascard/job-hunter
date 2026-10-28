"""Pull jobs from every configured source, filter, dedupe and store them."""

import logging
import re

import httpx

from .config import Settings
from .db import Database
from .dedupe import dedupe
from .models import Job
from .sources import adzuna, greenhouse, lever, remotive

log = logging.getLogger(__name__)


def title_matches(job: Job, include: list[str], exclude: list[str]) -> bool:
    """Company feeds list every opening (sales, legal...); keep only relevant titles."""
    title = job.title.lower()
    if any(re.search(rf"\b{re.escape(w.lower())}\b", title) for w in exclude):
        return False
    return not include or any(re.search(rf"\b{re.escape(w.lower())}\b", title) for w in include)


def collect(settings: Settings, client: httpx.Client) -> tuple[list[Job], dict]:
    """Run each source on its own so one failing feed does not stop the rest."""
    cfg = settings.load_sources()
    runs = {
        "greenhouse": lambda: greenhouse.fetch(client, cfg.get("greenhouse", [])),
        "lever": lambda: lever.fetch(client, cfg.get("lever", [])),
        "remotive": lambda: remotive.fetch(client, cfg.get("remotive", {}).get("search", [])),
    }
    if settings.adzuna_app_id and settings.adzuna_app_key and cfg.get("adzuna"):
        runs["adzuna"] = lambda: adzuna.fetch(
            client, cfg["adzuna"], settings.adzuna_app_id, settings.adzuna_app_key
        )

    jobs: list[Job] = []
    report: dict = {}
    for name, run in runs.items():
        try:
            found = run()
            jobs.extend(found)
            report[name] = {"fetched": len(found)}
        except Exception as exc:  # network errors, bad slugs, schema changes
            log.warning("source %s failed: %s", name, exc)
            report[name] = {"error": str(exc)}
    return jobs, report


def run_ingest(settings: Settings, db: Database, client: httpx.Client | None = None) -> dict:
    own_client = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": "job-hunter/0.1"})
    try:
        jobs, report = collect(settings, client)
    finally:
        if own_client:
            client.close()

    filters = settings.load_sources().get("title_filter", {})
    kept = [j for j in jobs if title_matches(j, filters.get("include", []), filters.get("exclude", []))]
    unique = dedupe(kept)
    new = sum(db.upsert_job(key, job, links) for key, job, links in unique)
    return {
        "sources": report,
        "fetched": len(jobs),
        "after_title_filter": len(kept),
        "unique": len(unique),
        "new": new,
    }
