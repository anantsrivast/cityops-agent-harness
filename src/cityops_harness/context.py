"""Pure decision logic for context engineering (notebook 03).

Side-effect free: the notebook supplies SQL, the LLM calls, and the chart.

The review's critique of the original 8.1/8.2b is that both were measured by
size - a card that forgot everything scores best on a character count, and
"the bytes are recoverable" says nothing about whether the model went and got
them. The helpers here exist so the notebook can assert *fidelity*: which
planted facts survived compaction (`card_fidelity`), and whether the agent
actually resolved an offload reference it was handed (`parse_blob_references`).
"""

from __future__ import annotations

import json
import re
import secrets

BLOB_PREFIX = "/tool_out/blob/"
_REFERENCE_RE = re.compile(r"(?<!\w)harness://blob/([0-9a-f]{12})\b")
_CARD_SECTIONS = ("facts", "decisions", "open_questions")


def compaction_due(transcript_chars: int, budget_chars: int = 12_000) -> bool:
    """Compact at the budget, not once it has already been blown through."""
    return transcript_chars >= budget_chars


def offload_decision(result_chars: int, max_inline_chars: int = 2_000) -> str:
    """Large tool results go to a blob and come back as a reference."""
    return "offload" if result_chars >= max_inline_chars else "inline"


def new_blob_id() -> str:
    return secrets.token_hex(6)


def blob_reference(blob_id: str) -> str:
    """The one form the model ever sees - the parser accepts nothing else."""
    return f"harness://blob/{blob_id}"


def parse_blob_references(text: str) -> list[str]:
    """Blob ids the model named, in order, without duplicates.

    Used to prove the agent closed the loop itself: the id it fetched has to
    have come from the reference it was shown, not from anywhere else.
    """
    seen: list[str] = []
    for blob_id in _REFERENCE_RE.findall(text or ""):
        if blob_id not in seen:
            seen.append(blob_id)
    return seen


def blob_path(blob_id: str) -> str:
    return f"{BLOB_PREFIX}{blob_id}.json"


def is_offloaded_blob(path: str) -> bool:
    """Offloaded payloads are never promotion candidates.

    Today `/tool_out/` already falls outside notebook 02's `/inbox/` opt-in, so
    the exclusion is incidental. Naming it here makes it intentional: changing
    the opt-in prefix cannot silently start graduating tool dumps.
    """
    return path.startswith(BLOB_PREFIX)


def render_card(card: dict) -> str:
    return json.dumps(card, indent=2, sort_keys=False)


def parse_card(text: str) -> dict:
    """Fixed top-level keys keep the fidelity probe a set operation."""
    card = json.loads(text)
    for section in _CARD_SECTIONS:
        if section not in card:
            raise ValueError(f"card missing {section!r} section")
    return card


def merge_card(card: dict, update: dict) -> dict:
    """Fold a compaction result into the running card.

    Additive by construction: a later fact with the same id corrects the
    earlier one, but nothing already in the card is dropped just because the
    model failed to repeat it. Lossy summarisation forgets open questions
    first, and that loss should be a measured outcome, not a silent one.
    """
    facts: dict[str, dict] = {f["id"]: f for f in card.get("facts", [])}
    for fact in update.get("facts", []):
        facts[fact["id"]] = fact

    merged = {"facts": list(facts.values())}
    for section in ("decisions", "open_questions"):
        combined: list = []
        for item in list(card.get(section, [])) + list(update.get(section, [])):
            if item not in combined:
                combined.append(item)
        merged[section] = combined
    return merged


def fact_strength(
    reinforcements: int, turns_since_reference: int, half_life_turns: float = 8.0
) -> float:
    """How firmly a fact is held: reinforcement raises it, disuse decays it.

    `strength = (1 + reinforcements) * 0.5 ** (turns_since_reference / half_life)`.
    Same half-life shape as `promote.rerank_by_recency`, deliberately, so the
    codebase carries one decay model. This is the piece TTL eviction gets wrong:
    survival tracks *retrieval strength*, not arrival time, so a fact referenced
    again and again outlives a newer one nobody ever needed.
    """
    return (1 + reinforcements) * 0.5 ** (turns_since_reference / half_life_turns)


def select_for_eviction(
    card: dict,
    current_turn: int,
    ceiling_chars: int = 4_000,
    floor_facts: int = 3,
    half_life_turns: float = 8.0,
) -> tuple[dict, list[dict]]:
    """Trim a card back under its size ceiling by evicting the weakest facts.

    Returns `(kept_card, evicted_facts)`. A card only compresses if something
    forces it to; this is that force. Facts leave weakest-first by
    `fact_strength` (ties broken oldest-first, then by id, so the result is
    deterministic), and never below `floor_facts` however over-budget the card
    is. The caller consolidates the evicted facts into `gist` rather than
    dropping them outright - forgetting the specifics, keeping the shape.
    """
    kept = {**card, "facts": list(card.get("facts", []))}
    evicted: list[dict] = []

    def weakest_first(fact: dict) -> tuple[float, int, str]:
        last_seen = fact.get("last_seen", fact.get("turn", 0))
        strength = fact_strength(
            fact.get("reinforcements", 0), current_turn - last_seen, half_life_turns
        )
        return (strength, fact.get("turn", 0), str(fact.get("id", "")))

    while len(kept["facts"]) > floor_facts and len(render_card(kept)) > ceiling_chars:
        victim = min(kept["facts"], key=weakest_first)
        kept["facts"].remove(victim)
        evicted.append(victim)
    return kept, evicted


def fact_status(planted_ids: list[str], card: dict) -> dict[str, str]:
    """Classify each planted fact as verbatim / gist / lost.

    The measure a hit/miss recall cannot express: a fact consolidated into gist
    still answers "which bridge?" but no longer "which pier?". Verbatim beats
    gist beats lost when a fact somehow appears in both.
    """
    verbatim = {f["id"] for f in card.get("facts", [])}
    in_gist = {gid for entry in card.get("gist", []) for gid in entry.get("ids", [])}
    status: dict[str, str] = {}
    for pid in planted_ids:
        if pid in verbatim:
            status[pid] = "verbatim"
        elif pid in in_gist:
            status[pid] = "gist"
        else:
            status[pid] = "lost"
    return status


def card_fidelity(planted_ids: list[str], card: dict) -> tuple[list[str], list[str], float]:
    """Did the card still hold the planted facts when they were finally needed?

    This is the measurement the review found missing: recall over facts planted
    many turns earlier, rather than the card's character count.
    """
    present = {f["id"] for f in card.get("facts", [])}
    hits = [pid for pid in planted_ids if pid in present]
    misses = [pid for pid in planted_ids if pid not in present]
    recall = 1.0 if not planted_ids else len(hits) / len(planted_ids)
    return hits, misses, recall
