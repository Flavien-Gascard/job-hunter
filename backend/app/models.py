"""Data shapes shared by the API, the database layer and the Claude calls."""

from typing import Literal

from pydantic import BaseModel, Field

# --- Resume -----------------------------------------------------------------


class Bullet(BaseModel):
    id: str = ""
    label: str = Field("", description="Optional bold lead-in, e.g. 'Root cause analysis'")
    text: str


class Role(BaseModel):
    id: str = ""
    title: str
    company: str
    location: str = ""
    start: str = ""
    end: str = ""
    bullets: list[Bullet] = []


class SkillGroup(BaseModel):
    name: str
    items: list[str]


class Resume(BaseModel):
    name: str
    contact: list[str] = Field([], description="Lines like location, email, phone, LinkedIn")
    profile: str = ""
    skills: list[SkillGroup] = []
    experience: list[Role] = []
    certifications: list[str] = []
    education: list[str] = []


def assign_ids(resume: Resume) -> Resume:
    """Give every role and bullet a stable id ('r0', 'r0b3') that edits can point at."""
    for i, role in enumerate(resume.experience):
        role.id = f"r{i}"
        for j, bullet in enumerate(role.bullets):
            bullet.id = f"r{i}b{j}"
    return resume


# --- Jobs -------------------------------------------------------------------


class Job(BaseModel):
    """A posting in the shared format every source adapter converts to."""

    source: str
    source_id: str
    title: str
    company: str
    location: str = ""
    remote: bool = False
    url: str
    description: str = ""
    salary: str = ""
    posted_at: str = ""


class MatchScore(BaseModel):
    score: int = Field(description="0-100 fit between the resume and the job")
    summary: str = Field(description="One sentence verdict")
    strengths: list[str]
    gaps: list[str]


# --- Tailoring --------------------------------------------------------------


class Edit(BaseModel):
    target: str = Field(
        description="'profile', a bullet id such as 'r0b3', or 'skills:<group name>'"
    )
    action: Literal["rewrite", "remove"]
    proposed: str = Field("", description="New text; empty when action is 'remove'")
    reason: str


class RoleOrder(BaseModel):
    role_id: str
    bullet_ids: list[str]


class TailorResult(BaseModel):
    edits: list[Edit]
    bullet_order: list[RoleOrder] = Field(
        [], description="Optional new bullet order per role, most relevant first"
    )
    keywords: list[str] = Field([], description="Job keywords the tailored resume now covers")


class CheckedEdit(Edit):
    """An edit after server-side checks; warnings are shown next to it in the UI."""

    original: str = ""
    warnings: list[str] = []
