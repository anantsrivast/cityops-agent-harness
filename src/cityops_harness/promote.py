"""Pure decision logic for the curated promotion pipeline (notebook 02).

Side-effect free: the notebook supplies SQL, the SDK, and LLM calls.
The curation *policy* lives here, not in a notebook, so notebook 02 (which runs
it) and notebook 04 (which grades it) cannot drift onto different copies.
"""

from __future__ import annotations

import hashlib

# Appended to the Agent Memory SDK's extraction prompt for each inbox thread.
CURATION_INSTRUCTIONS = (
    "OVERRIDE for this thread - these rules take precedence over the atomic-memory rule\n"
    "above. Each user message is ONE complete field note about a city infrastructure\n"
    "asset. For a note worth keeping, extract EXACTLY ONE record:\n"
    "  - record_type MUST be \"memory\";\n"
    "  - content MUST be the note's full text, copied verbatim - do not split it into\n"
    "    separate facts, shorten, paraphrase, merge it with other notes, or add anything.\n"
    "Keep a note only if it is a completed, factual observation or action about the asset\n"
    "(a defect, a measurement, a repair, a recommendation). Extract NOTHING from TODOs,\n"
    "open questions, half-formed drafts, abandoned queries, raw tool output, or notes that\n"
    "say work could not be completed.\n"
)

# Appended to the SDK's link-extraction prompt: when a new memory supersedes an old one.
LINK_INSTRUCTIONS = (
    "A repair or remediation note SUPERSEDES the defect note it fixes on the same\n"
    "component at the same location. Different piers or components are unrelated.\n"
    "When linking, still store the new note verbatim as its own single record - do not\n"
    "rewrite it into a consolidated memory that repeats the old note's text.\n"
)


def note_revision(content: str) -> str:
    """Content fingerprint stored as provenance with every promoted note."""
    return hashlib.sha256(content.encode()).hexdigest()


def triage_allowed(path: str, allowed_prefix: str = "/inbox/") -> bool:
    """Opt-in promotion: only notes filed under the inbox are ever candidates."""
    return path.startswith(allowed_prefix)


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
