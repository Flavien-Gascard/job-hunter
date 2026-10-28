"""FastAPI app: the REST API for the React front end, plus a background refresh loop."""

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, tailoring
from .config import ROOT, Settings, settings as default_settings
from .db import STATUSES, Database
from .export import docx_to_text, resume_to_docx
from .ingest import run_ingest
from .models import Resume, assign_ids

log = logging.getLogger(__name__)
EXAMPLE_RESUME = ROOT / "config" / "resume.example.json"


class StatusUpdate(BaseModel):
    status: str


class ExportRequest(BaseModel):
    accepted: list[int] = []   # indexes into the tailored edits
    use_order: bool = True     # apply the suggested bullet order


def create_app(settings: Settings = default_settings) -> FastAPI:
    db = Database(settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if settings.refresh_hours > 0:
            task = asyncio.create_task(_refresh_loop(settings, db))
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Job Hunter", lifespan=lifespan)

    # --- resume ---

    def load_resume() -> Resume:
        path = settings.resume_path if settings.resume_path.exists() else EXAMPLE_RESUME
        return assign_ids(Resume.model_validate_json(path.read_text()))

    def save_resume(resume: Resume) -> Resume:
        resume = assign_ids(resume)
        settings.resume_path.parent.mkdir(parents=True, exist_ok=True)
        settings.resume_path.write_text(resume.model_dump_json(indent=2))
        return resume

    @app.get("/api/health")
    def health():
        return {
            "ai_configured": settings.ai_configured,
            "model": settings.model,
            "resume_loaded": settings.resume_path.exists(),
            "adzuna_configured": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        }

    @app.get("/api/resume")
    def get_resume():
        return load_resume()

    @app.put("/api/resume")
    def put_resume(resume: Resume):
        return save_resume(resume)

    @app.post("/api/resume/import")
    async def import_resume(file: UploadFile):
        if not (file.filename or "").lower().endswith(".docx"):
            raise HTTPException(400, "Upload a .docx file.")
        text = docx_to_text(await file.read())
        try:
            resume = await asyncio.to_thread(ai.import_resume, text)
        except ai.AIError as e:
            raise HTTPException(502, str(e))
        return save_resume(resume)

    # --- jobs ---

    @app.get("/api/jobs")
    def list_jobs(q: str = "", remote: bool | None = None, status: str | None = None):
        return db.list_jobs(tailoring.resume_hash(load_resume()), q=q, remote=remote, status=status)

    def job_or_404(job_id: str, resume: Resume) -> dict:
        job = db.get_job(job_id, tailoring.resume_hash(resume))
        if not job:
            raise HTTPException(404, "Job not found.")
        return job

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        resume = load_resume()
        job = job_or_404(job_id, resume)
        job["tailored"] = db.get_result("tailored", job_id, tailoring.resume_hash(resume))
        return job

    @app.patch("/api/jobs/{job_id}")
    def update_job(job_id: str, body: StatusUpdate):
        if body.status not in STATUSES:
            raise HTTPException(400, f"status must be one of {STATUSES}")
        if not db.set_status(job_id, body.status):
            raise HTTPException(404, "Job not found.")
        return {"id": job_id, "status": body.status}

    @app.post("/api/jobs/refresh")
    async def refresh():
        return await asyncio.to_thread(run_ingest, settings, db)

    @app.post("/api/jobs/{job_id}/score")
    async def score(job_id: str):
        resume = load_resume()
        job = job_or_404(job_id, resume)
        try:
            result = await asyncio.to_thread(ai.score_job, resume, job)
        except ai.AIError as e:
            raise HTTPException(502, str(e))
        db.save_result("scores", job_id, tailoring.resume_hash(resume), result.model_dump())
        return result

    @app.post("/api/jobs/score-batch")
    async def score_batch(limit: int = 10):
        """Score the newest unscored jobs. Capped so one click can't run up a big bill."""
        resume = load_resume()
        rhash = tailoring.resume_hash(resume)
        ids = db.unscored_ids(rhash, min(limit, 25))
        done, errors = 0, []
        for job_id in ids:
            try:
                result = await asyncio.to_thread(ai.score_job, resume, db.get_job(job_id, rhash))
                db.save_result("scores", job_id, rhash, result.model_dump())
                done += 1
            except ai.AIError as e:
                errors.append(str(e))
                break  # the same error (bad key, rate limit) would hit every job
        return {"scored": done, "errors": errors}

    @app.post("/api/jobs/{job_id}/tailor")
    async def tailor(job_id: str):
        resume = load_resume()
        job = job_or_404(job_id, resume)
        try:
            raw = await asyncio.to_thread(ai.tailor, resume, job)
        except ai.AIError as e:
            raise HTTPException(502, str(e))
        checked = tailoring.check(resume, raw)
        db.save_result("tailored", job_id, tailoring.resume_hash(resume), checked)
        return checked

    @app.post("/api/jobs/{job_id}/export")
    def export(job_id: str, body: ExportRequest):
        resume = load_resume()
        job = job_or_404(job_id, resume)
        tailored = db.get_result("tailored", job_id, tailoring.resume_hash(resume))
        if tailored is None:
            raise HTTPException(409, "Tailor the resume for this job first.")
        edits = [tailored["edits"][i] for i in body.accepted if 0 <= i < len(tailored["edits"])]
        order = tailored["bullet_order"] if body.use_order else []
        final = tailoring.apply(resume, edits, order)
        filename = _slug(f"{resume.name} {job['company']} {job['title']}") + ".docx"
        return Response(
            resume_to_docx(final),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Serve the built front end (npm run build) when it exists.
    if settings.frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            return FileResponse(settings.frontend_dist / "index.html")

    return app


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:120]


async def _refresh_loop(settings: Settings, db: Database) -> None:
    while True:
        try:
            summary = await asyncio.to_thread(run_ingest, settings, db)
            log.info("refresh: %s", summary)
        except Exception:
            log.exception("refresh failed")
        await asyncio.sleep(settings.refresh_hours * 3600)


app = create_app()
