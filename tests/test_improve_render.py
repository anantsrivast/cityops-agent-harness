import pytest

from cityops_harness.improve import (
    parse_skill_md,
    render_skill_md,
    trajectory_to_text,
    truncate_result,
)


def _render():
    return render_skill_md(
        name="corrosion-triage",
        description="Triage a corrosion report against history and record a finding",
        tools=["find_similar_findings", "log_finding"],
        when_to_use="An inspector reports corrosion and needs it assessed and recorded.",
        steps_body="1. Search history.\n2. Grade severity.\n3. Record the finding.",
        source_workflow_id="wf-123",
        schema_sha="abc123",
    )


def test_render_roundtrips_through_parse():
    parsed = parse_skill_md(_render())
    assert parsed["name"] == "corrosion-triage"
    assert parsed["tools"] == ["find_similar_findings", "log_finding"]
    assert parsed["source_workflow"] == "wf-123"
    assert parsed["schema_sha"] == "abc123"
    assert "Search history" in parsed["steps_body"]
    assert "inspector reports corrosion" in parsed["when_to_use"]


def test_parse_rejects_missing_frontmatter():
    with pytest.raises(ValueError, match="frontmatter"):
        parse_skill_md("## Steps\n1. do it\n")


def test_parse_rejects_missing_steps():
    text = _render().split("## Steps")[0]
    with pytest.raises(ValueError, match="Steps"):
        parse_skill_md(text)


def test_truncate_result_short_passthrough():
    assert truncate_result("ok", 300) == "ok"


def test_truncate_result_long_appends_marker():
    out = truncate_result("x" * 500, 300)
    assert out.startswith("x" * 300)
    assert "truncated 200 chars" in out


def test_trajectory_to_text_orders_and_truncates():
    steps = [
        {"tool": "find_similar_findings", "args": {"description": "rust"}, "result": "y" * 400},
        {"tool": "log_finding", "args": {"severity": "high"}, "result": "fid-1"},
    ]
    text = trajectory_to_text(steps, max_result_chars=100)
    assert text.index("Step 1: find_similar_findings") < text.index("Step 2: log_finding")
    assert "truncated 300 chars" in text
    assert '"severity": "high"' in text
