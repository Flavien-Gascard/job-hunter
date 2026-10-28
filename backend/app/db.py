"""SQLite storage for jobs, match scores and tailored resumes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,   -- dedupe key, stable across sources
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    location    TEXT,
    remote      INTEGER NOT NULL DEFAULT 0,
    url         TEXT,
    description TEXT,
    salary      TEXT,
    posted_at   TEXT,
    sources     TEXT NOT NULL,      -- JSON list of {source, source_id, url}
    status      TEXT NOT NULL DEFAULT 'new',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
-- AI results are keyed by resume hash so editing the resume invalidates them.
CREATE TABLE IF NOT EXISTS scores (
    job_id      TEXT NOT NULL,
    resume_hash TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (job_id, resume_hash)
);
CREATE TABLE IF NOT EXISTS tailored (
    job_id      TEXT NOT NULL,
    resume_hash TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (job_id, resume_hash)
);
"""

STATUSES = ("new", "saved", "applied", "interview", "offer", "rejected", "hidden")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # --- jobs ---

    def upsert_job(self, key: str, job: Job, links: list[dict]) -> bool:
        """Insert or refresh a posting. Returns True when it is new."""
        ts = now()
        with self.conn() as c:
            row = c.execute("SELECT sources FROM jobs WHERE id = ?", (key,)).fetchone()
            if row is None:
                c.execute(
                    """INSERT INTO jobs (id, title, company, location, remote, url, description,
                       salary, posted_at, sources, first_seen, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (key, job.title, job.company, job.location, int(job.remote), job.url,
                     job.description, job.salary, job.posted_at, json.dumps(links), ts, ts),
                )
                return True
            known = {(s["source"], s["source_id"]): s for s in json.loads(row["sources"])}
            for link in links:
                known[(link["source"], link["source_id"])] = link
            c.execute(
                """UPDATE jobs SET title = ?, location = ?, url = ?, salary = COALESCE(NULLIF(?, ''), salary),
                   description = CASE WHEN length(?) > length(COALESCE(description, '')) THEN ? ELSE description END,
                   sources = ?, last_seen = ? WHERE id = ?""",
                (job.title, job.location, job.url, job.salary, job.description, job.description,
                 json.dumps(list(known.values())), ts, key),
            )
            return False

    def list_jobs(self, resume_hash: str, q: str = "", remote: bool | None = None,
                  status: str | None = None, limit: int = 200) -> list[dict]:
        sql = """SELECT j.*, s.payload AS score FROM jobs j
                 LEFT JOIN scores s ON s.job_id = j.id AND s.resume_hash = ?
                 WHERE 1 = 1"""
        args: list = [resume_hash]
        if q:
            sql += " AND (j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)"
            args += [f"%{q}%"] * 3
        if remote is not None:
            sql += " AND j.remote = ?"
            args.append(int(remote))
        if status:
            sql += " AND j.status = ?"
            args.append(status)
        else:
            sql += " AND j.status != 'hidden'"
        sql += """ ORDER BY CASE WHEN s.payload IS NULL THEN 1 ELSE 0 END,
                   json_extract(s.payload, '$.score') DESC, j.posted_at DESC LIMIT ?"""
        args.append(limit)
        with self.conn() as c:
            return [_job_row(r) for r in c.execute(sql, args)]

    def get_job(self, job_id: str, resume_hash: str) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                """SELECT j.*, s.payload AS score FROM jobs j
                   LEFT JOIN scores s ON s.job_id = j.id AND s.resume_hash = ?
                   WHERE j.id = ?""",
                (resume_hash, job_id),
            ).fetchone()
        return _job_row(row) if row else None

    def set_status(self, job_id: str, status: str) -> bool:
        with self.conn() as c:
            return c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)).rowcount > 0

    def unscored_ids(self, resume_hash: str, limit: int) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                """SELECT j.id FROM jobs j LEFT JOIN scores s
                   ON s.job_id = j.id AND s.resume_hash = ?
                   WHERE s.job_id IS NULL AND j.status != 'hidden'
                   ORDER BY j.posted_at DESC LIMIT ?""",
                (resume_hash, limit),
            ).fetchall()
        return [r["id"] for r in rows]

    # --- AI results ---

    def save_result(self, table: str, job_id: str, resume_hash: str, payload: dict) -> None:
        assert table in ("scores", "tailored")
        with self.conn() as c:
            c.execute(
                f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?, ?)",
                (job_id, resume_hash, json.dumps(payload), now()),
            )

    def get_result(self, table: str, job_id: str, resume_hash: str) -> dict | None:
        assert table in ("scores", "tailored")
        with self.conn() as c:
            row = c.execute(
                f"SELECT payload FROM {table} WHERE job_id = ? AND resume_hash = ?",
                (job_id, resume_hash),
            ).fetchone()
        return json.loads(row["payload"]) if row else None


def _job_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["remote"] = bool(d["remote"])
    d["sources"] = json.loads(d["sources"])
    d["score"] = json.loads(d["score"]) if d.get("score") else None
    return d
