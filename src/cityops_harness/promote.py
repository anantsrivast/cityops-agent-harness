"""Pure decision logic for the curated promotion pipeline (notebook 02).

Side-effect free: the notebook supplies SQL, the SDK, and LLM calls.
"""

from __future__ import annotations

import hashlib


def note_revision(content: str) -> str:
    """Content fingerprint stored as provenance with every promoted note."""
    return hashlib.sha256(content.encode()).hexdigest()


def triage_allowed(path: str, allowed_prefix: str = "/inbox/") -> bool:
    """Opt-in promotion: only notes filed under the inbox are ever candidates."""
    return path.startswith(allowed_prefix)


def queue_health(
    pending: int,
    oldest_age_minutes: float | None,
    warn_pending: int = 10,
    stall_minutes: int = 120,
) -> str:
    """A stalled pipeline must be visible, not silent (the review's Path-1 #2)."""
    if pending > 0 and oldest_age_minutes is not None and oldest_age_minutes >= stall_minutes:
        return "stalled"
    if pending >= warn_pending:
        return "warn"
    return "ok"


def rerank_by_recency(
    rows: list[dict],
    half_life_days: float = 90.0,
    base_key: str = "base",
    age_key: str = "days_ago",
) -> list[dict]:
    """Recency-weighted recall: equal relevance decays with a half-life, so a
    fresh repair note outranks the stale defect it superseded."""
    for row in rows:
        row["score"] = row[base_key] * 0.5 ** (row[age_key] / half_life_days)
    return sorted(rows, key=lambda r: r["score"], reverse=True)
