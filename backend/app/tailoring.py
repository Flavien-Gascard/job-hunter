"""Server-side guardrails for Claude's resume edits, and applying the accepted ones.

Claude proposes; this module decides what is allowed. The rules:
- an edit must point at something that exists in the resume;
- a skills edit may only reorder or drop skills, never add one;
- numbers in a rewrite must already appear in the original text (a cheap,
  reliable check against invented metrics), otherwise the edit is flagged;
- a bullet order must be a permutation of that role's existing bullets.
"""

import hashlib
import re

from .models import CheckedEdit, Resume, TailorResult

_NUMBER = re.compile(r"\d[\d,.]*")


def resume_hash(resume: Resume) -> str:
    return hashlib.sha1(resume.model_dump_json().encode()).hexdigest()[:12]


def _numbers(text: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in _NUMBER.findall(text)}


def _split_skills(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[|,;\n]", text) if s.strip()]


def _bullet_text(bullet) -> str:
    return f"{bullet.label}: {bullet.text}" if bullet.label else bullet.text


def check(resume: Resume, result: TailorResult) -> dict:
    bullets = {b.id: b for role in resume.experience for b in role.bullets}
    skills = {f"skills:{g.name}": g for g in resume.skills}
    checked: list[CheckedEdit] = []
    rejected: list[dict] = []

    for edit in result.edits:
        warnings: list[str] = []
        if edit.target == "profile":
            original = resume.profile
        elif edit.target in bullets:
            original = _bullet_text(bullets[edit.target])
        elif edit.target in skills:
            group = skills[edit.target]
            original = " | ".join(group.items)
            if edit.action == "rewrite":
                known = {s.lower() for s in group.items}
                added = [s for s in _split_skills(edit.proposed) if s.lower() not in known]
                if added:
                    rejected.append({**edit.model_dump(), "why": f"adds skills not on the resume: {added}"})
                    continue
        else:
            rejected.append({**edit.model_dump(), "why": "unknown target"})
            continue

        if edit.action == "rewrite":
            if not edit.proposed.strip():
                rejected.append({**edit.model_dump(), "why": "empty rewrite"})
                continue
            new_numbers = _numbers(edit.proposed) - _numbers(original)
            if new_numbers:
                warnings.append(f"numbers not in the original: {', '.join(sorted(new_numbers))}")
        if edit.action == "remove" and edit.target == "profile":
            rejected.append({**edit.model_dump(), "why": "the profile cannot be removed"})
            continue

        checked.append(CheckedEdit(**edit.model_dump(), original=original, warnings=warnings))

    orders = []
    for order in result.bullet_order:
        role = next((r for r in resume.experience if r.id == order.role_id), None)
        if role and sorted(order.bullet_ids) == sorted(b.id for b in role.bullets):
            orders.append(order.model_dump())

    return {
        "edits": [e.model_dump() for e in checked],
        "bullet_order": orders,
        "keywords": result.keywords,
        "rejected": rejected,
    }


def apply(resume: Resume, edits: list[dict], bullet_order: list[dict]) -> Resume:
    """Return a copy of the resume with the accepted (already checked) edits applied."""
    out = resume.model_copy(deep=True)
    bullets = {b.id: b for role in out.experience for b in role.bullets}
    removed: set[str] = set()

    for edit in edits:
        target, action, proposed = edit["target"], edit["action"], edit.get("proposed", "")
        if target == "profile":
            out.profile = proposed
        elif target in bullets:
            if action == "remove":
                removed.add(target)
                continue
            bullet = bullets[target]
            label, sep, text = proposed.partition(": ")
            # Keep the bold lead-in when Claude rewrote "Label: text" as a whole.
            if bullet.label and sep and len(label) <= 40:
                bullet.label, bullet.text = label, text
            else:
                bullet.text = proposed
        elif target.startswith("skills:"):
            name = target.removeprefix("skills:")
            out.skills = [
                g if g.name != name
                else g.model_copy(update={"items": _split_skills(proposed)})
                for g in out.skills
                if not (g.name == name and action == "remove")
            ]

    orders = {o["role_id"]: o["bullet_ids"] for o in bullet_order}
    for role in out.experience:
        if role.id in orders:
            rank = {bid: i for i, bid in enumerate(orders[role.id])}
            role.bullets.sort(key=lambda b: rank.get(b.id, len(rank)))
        role.bullets = [b for b in role.bullets if b.id not in removed]
    return out
