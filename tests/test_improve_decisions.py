from cityops_harness.improve import (
    compute_schema_sha,
    filter_by_distance,
    harvest_ready,
    lifecycle_transition,
    merge_decision,
)


def test_merge_decision_bands():
    assert merge_decision(0.05) == "merge"
    assert merge_decision(0.15) == "ask"      # boundary joins the gray band
    assert merge_decision(0.30) == "ask"
    assert merge_decision(0.40) == "ask"      # boundary still gray
    assert merge_decision(0.41) == "new"


def test_lifecycle_promotes_provisional_after_clean_verified_uses():
    assert lifecycle_transition("provisional", 2, 0) == "approved"
    assert lifecycle_transition("provisional", 1, 0) == "provisional"


def test_lifecycle_never_promotes_with_failures():
    assert lifecycle_transition("provisional", 5, 1) == "provisional"


def test_lifecycle_retires_on_failures_from_either_status():
    assert lifecycle_transition("provisional", 0, 2) == "retired"
    assert lifecycle_transition("approved", 9, 2) == "retired"


def test_lifecycle_retired_is_terminal():
    assert lifecycle_transition("retired", 10, 0) == "retired"


def test_harvest_ready_requires_recurrence_and_verified_majority():
    assert harvest_ready(3, 2, 0) is True
    assert harvest_ready(2, 2, 0) is False    # not recurrent enough
    assert harvest_ready(5, 1, 0) is False    # not enough verified successes
    assert harvest_ready(5, 2, 2) is False    # not a verified majority


def test_filter_by_distance():
    rows = [{"name": "a", "distance": 0.2}, {"name": "b", "distance": 0.9}]
    assert filter_by_distance(rows, 0.5) == [{"name": "a", "distance": 0.2}]
    assert filter_by_distance(rows, 0.1) == []


def test_compute_schema_sha_order_independent():
    a = compute_schema_sha([("T1", "C1", "VARCHAR2"), ("T2", "C2", "NUMBER")])
    b = compute_schema_sha([("T2", "C2", "NUMBER"), ("T1", "C1", "VARCHAR2")])
    assert a == b and len(a) == 64


def test_compute_schema_sha_changes_with_schema():
    a = compute_schema_sha([("T1", "C1", "VARCHAR2")])
    b = compute_schema_sha([("T1", "C1", "CLOB")])
    assert a != b
