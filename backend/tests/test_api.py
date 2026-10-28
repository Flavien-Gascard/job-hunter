"""End-to-end through the HTTP API, with fake job feeds and a fake Claude."""

import io
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import ai, ingest, main
from app.config import ROOT, settings
from app.models import Edit, MatchScore, TailorResult

FIX = Path(__file__).parent / "fixtures"


def fake_feeds(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "boards-api.greenhouse.io":
        return httpx.Response(200, json=json.loads((FIX / "greenhouse_acme.json").read_text()))
    if host == "api.lever.co":
        return httpx.Response(200, json=json.loads((FIX / "lever_beta.json").read_text()))
    if host == "remotive.com":
        return httpx.Response(200, json=json.loads((FIX / "remotive.json").read_text()))
    return httpx.Response(404)


@pytest.fixture
def client(tmp_path, monkeypatch):
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps({
        "greenhouse": ["acme"],
        "lever": ["beta"],
        "remotive": {"search": ["data engineer"]},
        "title_filter": {"include": ["data", "ml", "analytics"], "exclude": ["account executive"]},
    }))
    s = replace(settings, db_path=tmp_path / "t.db", resume_path=tmp_path / "resume.json",
                sources_path=sources, refresh_hours=0, adzuna_app_id="", adzuna_app_key="",
                frontend_dist=tmp_path / "no-dist")
    real_client = httpx.Client
    monkeypatch.setattr(ingest.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(fake_feeds)))
    monkeypatch.setattr(ai, "score_job", lambda resume, job: MatchScore(
        score=81 if "Data" in job["title"] else 40, summary="ok", strengths=["Spark"], gaps=[]))
    monkeypatch.setattr(ai, "tailor", lambda resume, job: TailorResult(edits=[
        Edit(target="profile", action="rewrite", proposed="Lakehouse engineer.", reason="job"),
        Edit(target="r0b2", action="remove", reason="irrelevant"),
        Edit(target="skills:Data", action="rewrite", proposed="Spark | Pinecone", reason="bad"),
    ]))
    return TestClient(main.create_app(s))


def test_refresh_filters_dedupes_and_lists(client):
    summary = client.post("/api/jobs/refresh").json()
    # 2 greenhouse + 1 lever + 2 remotive fetched; the sales job is filtered out;
    # Acme's senior data engineer appears on Greenhouse and Remotive -> one record.
    assert summary["fetched"] == 5
    assert summary["after_title_filter"] == 4
    assert summary["unique"] == 3 and summary["new"] == 3
    jobs = client.get("/api/jobs").json()
    acme = next(j for j in jobs if j["company"] == "Acme")
    assert {s["source"] for s in acme["sources"]} == {"greenhouse", "remotive"}
    # Running again finds nothing new.
    assert client.post("/api/jobs/refresh").json()["new"] == 0


def test_score_tailor_export_flow(client):
    client.post("/api/jobs/refresh")
    assert client.post("/api/jobs/score-batch").json()["scored"] == 3
    jobs = client.get("/api/jobs").json()
    assert jobs[0]["score"]["score"] == 81  # sorted by score

    job_id = jobs[0]["id"]
    tailored = client.post(f"/api/jobs/{job_id}/tailor").json()
    assert len(tailored["edits"]) == 2 and len(tailored["rejected"]) == 1  # Pinecone blocked

    resp = client.post(f"/api/jobs/{job_id}/export", json={"accepted": [0, 1]})
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].endswith('.docx"')
    text = "\n".join(p.text for p in Document(io.BytesIO(resp.content)).paragraphs)
    assert "Lakehouse engineer." in text
    assert "Right-sized EMR" not in text  # r0b2 was removed


def test_status_and_errors(client):
    client.post("/api/jobs/refresh")
    job_id = client.get("/api/jobs").json()[0]["id"]
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "applied"}).status_code == 200
    assert client.get("/api/jobs", params={"status": "applied"}).json()[0]["id"] == job_id
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "bogus"}).status_code == 400
    assert client.post(f"/api/jobs/{job_id}/export", json={}).status_code == 409
    assert client.get("/api/jobs/nope").status_code == 404


def test_ai_errors_become_502(client, monkeypatch):
    client.post("/api/jobs/refresh")
    job_id = client.get("/api/jobs").json()[0]["id"]

    def boom(*a):
        raise ai.AIError("Claude API key is missing or invalid (set ANTHROPIC_API_KEY).")

    monkeypatch.setattr(ai, "tailor", boom)
    resp = client.post(f"/api/jobs/{job_id}/tailor")
    assert resp.status_code == 502 and "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_example_resume_served_until_one_is_saved(client):
    assert client.get("/api/resume").json()["name"] == "Alex Example"
    r = json.loads((ROOT / "config" / "resume.example.json").read_text())
    r["name"] = "Pat Saved"
    assert client.put("/api/resume", json=r).json()["experience"][0]["bullets"][0]["id"] == "r0b0"
    assert client.get("/api/resume").json()["name"] == "Pat Saved"
