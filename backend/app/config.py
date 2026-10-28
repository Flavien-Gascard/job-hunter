"""Runtime settings, read from environment variables (and an optional .env file)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the app has no extra dependency for it."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("JOBHUNTER_MODEL", "claude-opus-5-5")
    db_path: Path = Path(os.getenv("JOBHUNTER_DB", ROOT / "data" / "jobhunter.db"))
    resume_path: Path = Path(os.getenv("JOBHUNTER_RESUME", ROOT / "data" / "resume.json"))
    sources_path: Path = Path(os.getenv("JOBHUNTER_SOURCES", ROOT / "config" / "sources.json"))
    refresh_hours: float = float(os.getenv("JOBHUNTER_REFRESH_HOURS", "6"))
    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")
    frontend_dist: Path = field(default=ROOT / "frontend" / "dist")

    @property
    def ai_configured(self) -> bool:
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))

    def load_sources(self) -> dict:
        if not self.sources_path.exists():
            return {}
        return json.loads(self.sources_path.read_text())


settings = Settings()
