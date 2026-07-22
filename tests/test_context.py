import pytest

from cityops_harness.context import (
    blob_path,
    blob_reference,
    card_fidelity,
    compaction_due,
    is_offloaded_blob,
    merge_card,
    new_blob_id,
    offload_decision,
    parse_blob_references,
    parse_card,
    render_card,
)


def test_compaction_triggers_at_the_budget_not_after():
    assert compaction_due(11_999) is False
    assert compaction_due(12_000) is True
    assert compaction_due(500, budget_chars=400) is True


def test_offload_decision_keeps_small_results_inline():
    assert offload_decision(1_999) == "inline"
    assert offload_decision(2_000) == "offload"
    assert offload_decision(10, max_inline_chars=5) == "offload"


def test_blob_ids_are_opaque_and_unique():
    a, b = new_blob_id(), new_blob_id()
    assert a != b
    assert len(a) == 12 and a.isalnum()


def test_reference_round_trips_through_model_text():
    ref = blob_reference("abc123def456")
    text = f"The inspection dump is large; I stored it at {ref} for later."
    assert parse_blob_references(text) == ["abc123def456"]


def test_parser_ignores_lookalikes_and_finds_many():
    text = (
        "see harness://blob/aaaaaaaaaaaa and harness://blob/bbbbbbbbbbbb "
        "but not http://blob/cccccccccccc nor harness://skill/dddddddddddd"
    )
    assert parse_blob_references(text) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


def test_parser_deduplicates_repeated_references():
    text = "harness://blob/aaaaaaaaaaaa then again harness://blob/aaaaaaaaaaaa"
    assert parse_blob_references(text) == ["aaaaaaaaaaaa"]


def test_offloaded_blobs_are_excluded_from_promotion():
    # The Path-1 x offloading interaction the review flags as unmeasured.
    assert is_offloaded_blob(blob_path("abc123def456")) is True
    assert is_offloaded_blob("/inbox/Harbor Bridge/1.md") is False
    assert blob_path("abc123def456").startswith("/tool_out/")


def test_card_round_trips():
    card = {
        "facts": [{"id": "f1", "text": "Pier 3 bearing plate corroded", "turn": 4}],
        "decisions": ["Prioritise Harbor Bridge for Q3"],
        "open_questions": ["Is the Pier 3 repair scheduled?"],
    }
    assert parse_card(render_card(card)) == card


def test_parse_card_rejects_missing_sections():
    with pytest.raises(ValueError, match="facts"):
        parse_card('{"decisions": [], "open_questions": []}')


def test_merge_card_is_additive_and_deduplicates_by_fact_id():
    card = {"facts": [{"id": "f1", "text": "old", "turn": 1}],
            "decisions": ["d1"], "open_questions": ["q1"]}
    update = {"facts": [{"id": "f1", "text": "corrected", "turn": 9},
                        {"id": "f2", "text": "new", "turn": 9}],
              "decisions": ["d1", "d2"], "open_questions": []}
    merged = merge_card(card, update)
    assert [f["id"] for f in merged["facts"]] == ["f1", "f2"]
    assert merged["facts"][0]["text"] == "corrected"   # newer wins
    assert merged["decisions"] == ["d1", "d2"]          # no duplicates
    assert merged["open_questions"] == ["q1"]           # never silently dropped


def test_card_fidelity_reports_the_planted_fact_that_fell_out():
    card = {"facts": [{"id": "f1", "text": "kept", "turn": 2}],
            "decisions": [], "open_questions": []}
    hits, misses, recall = card_fidelity(["f1", "f2"], card)
    assert hits == ["f1"]
    assert misses == ["f2"]
    assert recall == 0.5


def test_card_fidelity_of_an_empty_plant_set_is_perfect():
    assert card_fidelity([], {"facts": [], "decisions": [], "open_questions": []})[2] == 1.0
