import json
from pathlib import Path

from app import tailoring
from app.models import Edit, Resume, RoleOrder, TailorResult, assign_ids

EXAMPLE = Path(__file__).parents[2] / "config" / "resume.example.json"


def resume():
    return assign_ids(Resume.model_validate(json.loads(EXAMPLE.read_text())))


def result(*edits, order=()):
    return TailorResult(edits=list(edits), bullet_order=list(order), keywords=["Kafka"])


def test_unknown_target_is_rejected():
    out = tailoring.check(resume(), result(Edit(target="r9b9", action="remove", reason="x")))
    assert out["edits"] == [] and out["rejected"][0]["why"] == "unknown target"


def test_skills_edit_cannot_add_a_skill():
    edit = Edit(target="skills:Data", action="rewrite", proposed="Kafka | Spark | Flink", reason="x")
    out = tailoring.check(resume(), result(edit))
    assert out["edits"] == [] and "Flink" in out["rejected"][0]["why"]


def test_skills_reorder_is_allowed():
    edit = Edit(target="skills:Data", action="rewrite", proposed="Kafka | Spark | Snowflake", reason="x")
    out = tailoring.check(resume(), result(edit))
    assert len(out["edits"]) == 1 and out["edits"][0]["warnings"] == []


def test_new_numbers_are_flagged_not_dropped():
    edit = Edit(target="r0b0", action="rewrite", reason="x",
                proposed="Streaming: Built a Kafka pipeline handling 90M events a day.")
    (checked,) = tailoring.check(resume(), result(edit))["edits"]
    assert "90" in checked["warnings"][0]
    assert checked["original"].startswith("Streaming: Built")


def test_reused_numbers_are_fine():
    edit = Edit(target="r0b0", action="rewrite", reason="x",
                proposed="Streaming: Kafka-to-Snowflake pipeline, 40M events a day, under 5 minutes latency.")
    (checked,) = tailoring.check(resume(), result(edit))["edits"]
    assert checked["warnings"] == []


def test_bad_bullet_order_is_ignored():
    out = tailoring.check(resume(), result(order=[RoleOrder(role_id="r0", bullet_ids=["r0b0"])]))
    assert out["bullet_order"] == []


def test_apply_rewrites_removes_and_reorders():
    r = resume()
    edits = [
        {"target": "profile", "action": "rewrite", "proposed": "Streaming data engineer."},
        {"target": "r0b1", "action": "rewrite", "proposed": "Airflow: Moved 120 cron jobs to Airflow."},
        {"target": "r0b2", "action": "remove", "proposed": ""},
        {"target": "skills:Data", "action": "rewrite", "proposed": "Kafka | Spark"},
    ]
    order = [{"role_id": "r0", "bullet_ids": ["r0b2", "r0b1", "r0b0"]}]
    out = tailoring.apply(r, edits, order)
    assert out.profile == "Streaming data engineer."
    assert [b.id for b in out.experience[0].bullets] == ["r0b1", "r0b0"]
    assert out.experience[0].bullets[0].label == "Airflow"
    assert out.experience[0].bullets[0].text == "Moved 120 cron jobs to Airflow."
    assert out.skills[1].items == ["Kafka", "Spark"]
    assert r.profile != out.profile  # the base resume is untouched
