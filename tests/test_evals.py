import math

from cityops_harness.evals import (
    classification_metrics,
    cost_per_correct,
    mean_stdev,
    summarize_trials,
)


def test_perfect_classifier():
    m = classification_metrics({"a", "b"}, {"a", "b"})
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert (m["tp"], m["fp"], m["fn"]) == (2, 0, 0)


def test_admitting_junk_hurts_precision_not_recall():
    # predicted everything; positives are only the two signal notes
    m = classification_metrics({"a", "b", "junk1", "junk2"}, {"a", "b"})
    assert m["recall"] == 1.0
    assert m["precision"] == 0.5
    assert m["fp"] == 2 and m["fn"] == 0


def test_missing_a_signal_hurts_recall():
    m = classification_metrics({"a"}, {"a", "b"})
    assert m["precision"] == 1.0
    assert m["recall"] == 0.5
    assert m["fn"] == 1


def test_empty_predicted_is_zero_not_a_crash():
    m = classification_metrics(set(), {"a", "b"})
    assert m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0


def test_vacuous_when_both_empty():
    m = classification_metrics(set(), set())
    assert m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0


def test_mean_stdev_sample():
    mean, stdev = mean_stdev([2, 4, 4, 4, 5, 5, 7, 9])
    assert mean == 5.0
    # sample (n-1) standard deviation
    assert abs(stdev - math.sqrt(32 / 7)) < 1e-9


def test_mean_stdev_single_value_has_zero_spread():
    assert mean_stdev([3]) == (3.0, 0.0)


def test_mean_stdev_empty():
    assert mean_stdev([]) == (0.0, 0.0)


def test_cost_per_correct():
    assert cost_per_correct([1, 2, 3], [True, False, True]) == 3.0  # 6 spent / 2 correct


def test_cost_per_correct_none_when_nothing_correct():
    assert cost_per_correct([1, 2], [False, False]) is None


def test_summarize_trials():
    s = summarize_trials([10, 20, 30], [True, False, True])
    assert s["n"] == 3
    assert s["accuracy"] == 2 / 3
    assert s["cost_per_correct"] == 60 / 2
    assert s["mean_cost"] == 20.0
    assert abs(s["stdev_cost"] - math.sqrt(((10 - 20) ** 2 + (30 - 20) ** 2) / 2)) < 1e-9


def test_summarize_trials_all_wrong_has_no_cost_per_correct():
    s = summarize_trials([5, 5], [False, False])
    assert s["accuracy"] == 0.0
    assert s["cost_per_correct"] is None
