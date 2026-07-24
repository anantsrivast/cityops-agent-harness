"""Pure metric logic for the eval suite (notebook 04).

Side-effect free: the notebook supplies the datasets, the LLM/judge calls, and
the Langfuse plumbing. These helpers are what turns a pile of per-item outcomes
into the single number a `check(...)` can pass or fail on.

Each metric answers a question the design review said the original suite was
silent on: did the triage gate admit the *right* notes (precision/recall), not
just some notes; is a result stable across trials (variance), not a lucky n=1;
is a smaller context actually *cheaper per correct answer* (cost_per_correct),
not merely smaller.
"""

from __future__ import annotations

import statistics


def classification_metrics(predicted: set[str], positives: set[str]) -> dict:
    """Precision / recall / F1 for an admission decision (eval 1).

    `predicted` = the items the gate admitted; `positives` = the items that
    *should* be admitted (the signal labels). Precision punishes admitting junk;
    recall punishes dropping signal. Both are defined as 0.0 rather than raising
    when a denominator is empty, so a gate that admits nothing scores badly
    instead of crashing the notebook.
    """
    tp = len(predicted & positives)
    fp = len(predicted - positives)
    fn = len(positives - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def mean_stdev(xs: list[float]) -> tuple[float, float]:
    """Mean and *sample* (n-1) standard deviation; (0.0, 0.0) below two points.

    The review's critique of the original 8.4 was n=1 with no spread. A single
    trial has a mean but no measurable variance, so its stdev is reported as 0.0
    rather than undefined.
    """
    if not xs:
        return (0.0, 0.0)
    mean = statistics.fmean(xs)
    stdev = statistics.stdev(xs) if len(xs) > 1 else 0.0
    return (mean, stdev)


def cost_per_correct(costs: list[float], correct: list[bool]) -> float | None:
    """Total cost divided by number of correct answers; None if none are correct.

    A condition that is cheap but never right has no cost-per-correct - dividing
    would flatter it with a small numerator. None makes 'never correct' visible
    instead of hiding it behind a low cost.
    """
    n_correct = sum(1 for c in correct if c)
    if n_correct == 0:
        return None
    return sum(costs) / n_correct


def summarize_trials(costs: list[float], correct: list[bool]) -> dict:
    """Roll repeated trials of one condition into a comparable summary (eval 5)."""
    mean_cost, stdev_cost = mean_stdev(costs)
    accuracy = (sum(1 for c in correct if c) / len(correct)) if correct else 0.0
    return {
        "n": len(costs),
        "accuracy": accuracy,
        "cost_per_correct": cost_per_correct(costs, correct),
        "mean_cost": mean_cost,
        "stdev_cost": stdev_cost,
    }
