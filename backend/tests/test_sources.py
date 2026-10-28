import json
from pathlib import Path

from app.sources import adzuna, greenhouse, lever, remotive

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text())


def test_greenhouse_parses_and_unescapes_html():
    jobs = greenhouse.parse("acme", load("greenhouse_acme.json"))
    assert len(jobs) == 2
    job = jobs[0]
    assert job.source_id == "acme:4012345"
    assert job.company == "Acme"
    assert job.remote is True
    assert job.posted_at.startswith("2026-10-18")
    assert "<" not in job.description and "Iceberg" in job.description and "Spark" in job.description


def test_lever_parses_salary_and_sections():
    (job,) = lever.parse("beta", load("lever_beta.json"))
    assert job.title == "ML Platform Engineer"
    assert job.company == "Beta"
    assert job.remote is False
    assert job.salary == "USD 150,000–190,000"
    assert "Requirements" in job.description and "Benefits" in job.description
    assert job.posted_at.startswith("2025-10-09")


def test_remotive_marks_everything_remote():
    jobs = remotive.parse(load("remotive.json"))
    assert [j.remote for j in jobs] == [True, True]
    assert jobs[0].description == "Short Remotive copy."


def test_adzuna_parses_company_and_salary():
    (job,) = adzuna.parse(load("adzuna.json"))
    assert job.company == "Delta Bank"
    assert job.salary == "USD 120,000–140,000"
    assert job.url.startswith("https://www.adzuna.com/")
