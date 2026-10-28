from app.dedupe import dedupe, dedupe_key, norm_company, norm_title
from app.models import Job


def job(**kw):
    base = dict(source="x", source_id="1", title="Data Engineer", company="Acme", url="u")
    return Job(**{**base, **kw})


def test_normalizers():
    assert norm_company("Acme, Inc.") == "acme"
    assert norm_company("ACME Corp") == "acme"
    assert norm_title("Sr. Data Engineer (Remote)") == "senior data engineer"


def test_same_job_on_two_boards_collapses_and_keeps_longest_description():
    a = job(source="greenhouse", source_id="g1", title="Senior Data Engineer (Remote)",
            remote=True, description="full description " * 20)
    b = job(source="remotive", source_id="r1", title="Sr. Data Engineer", company="Acme Inc.",
            remote=True, description="snippet")
    (key, best, links), = dedupe([a, b])
    assert best.source == "greenhouse"
    assert {l["source"] for l in links} == {"greenhouse", "remotive"}


def test_same_posting_from_two_searches_is_linked_once():
    a = job(source="remotive", source_id="r1")
    (_, _, links), = dedupe([a, a.model_copy()])
    assert len(links) == 1


def test_different_city_is_a_different_job():
    a = job(location="Wilmington, DE")
    b = job(location="New York, NY")
    assert dedupe_key(a) != dedupe_key(b)


def test_city_spelling_variants_match():
    a = job(location="Wilmington, DE, United States")
    b = job(location="Wilmington, Delaware")
    assert dedupe_key(a) == dedupe_key(b)
