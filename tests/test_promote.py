from cityops_harness.promote import (
    note_revision,
    rerank_by_recency,
    triage_allowed,
)


def test_note_revision_is_stable_sha():
    a = note_revision("bearing plates replaced")
    assert a == note_revision("bearing plates replaced")
    assert a != note_revision("bearing plates rusted")
    assert len(a) == 64


def test_triage_allowed_only_inbox():
    assert triage_allowed("/inbox/Harbor Bridge/1.md") is True
    assert triage_allowed("/work/draft.md") is False
    assert triage_allowed("/tool_out/dump.json") is False
    assert triage_allowed("/plans/briefing_plan.md") is False
    assert triage_allowed("inbox/no-leading-slash.md") is False


def test_rerank_by_recency_prefers_fresh_equally_relevant():
    rows = [
        {"id": "old", "base": 1.0, "days_ago": 180},
        {"id": "new", "base": 1.0, "days_ago": 0},
    ]
    out = rerank_by_recency(rows, half_life_days=90.0)
    assert [r["id"] for r in out] == ["new", "old"]
    assert out[0]["score"] == 1.0
    assert abs(out[1]["score"] - 0.25) < 1e-9     # two half-lives


def test_rerank_by_recency_relevance_still_matters():
    rows = [
        {"id": "fresh_weak", "base": 0.1, "days_ago": 0},
        {"id": "old_strong", "base": 1.0, "days_ago": 90},
    ]
    out = rerank_by_recency(rows, half_life_days=90.0)
    assert out[0]["id"] == "old_strong"           # 0.5 beats 0.1


def test_curation_policy_demands_one_verbatim_memory():
    # nb02 runs this text and nb04 grades it; both checks assume these rules.
    from cityops_harness.promote import CURATION_INSTRUCTIONS, LINK_INSTRUCTIONS
    assert "EXACTLY ONE record" in CURATION_INSTRUCTIONS
    assert "verbatim" in CURATION_INSTRUCTIONS
    assert "SUPERSEDES" in LINK_INSTRUCTIONS
