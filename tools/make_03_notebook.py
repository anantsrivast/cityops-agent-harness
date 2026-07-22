"""Regenerate notebooks/03_context_engineering_complete.ipynb.

Run: python tools/make_03_notebook.py
Later plan tasks append sections; keep SECTIONS ordered.
"""

import nbformat as nbf


def md(src):
    return nbf.v4.new_markdown_cell(src)


def code(src):
    return nbf.v4.new_code_cell(src)


# --------------------------------------------------------------------------
# Section: intro
# --------------------------------------------------------------------------
INTRO = [
    md(
        "# 03 - Context Engineering: measuring what survives, not what shrinks\n\n"
        "Notebooks 01 and 02 fixed how the harness *learns*. This notebook fixes how it\n"
        "*forgets* - and, more importantly, how you find out what it forgot.\n\n"
        "The design review's complaint about the original compaction and offloading\n"
        "sections was not that they were wrong, but that they measured the wrong thing:\n\n"
        "| Review gap (8.1 / 8.2b) | This notebook |\n"
        "|---|---|\n"
        "| Card judged by character count | **Fidelity probe**: is the fact from turn 4 still there at turn 40, when it is finally needed? |\n"
        "| \"The bytes are recoverable\" declared a win | **Agent in the loop**: the model must notice the reference, fetch it, and use the payload |\n"
        "| Offloading and promotion never tested together | Offloaded blobs are **barred from promotion**, and the notebook proves it |\n\n"
        "A smaller card is trivially easy to produce - throw everything away and the chart\n"
        "looks fantastic. The only interesting question is what it still knows."
    ),
]

# --------------------------------------------------------------------------
# Section: setup
# --------------------------------------------------------------------------
SETUP = [
    md(
        "## 0 · Setup\n\n"
        "Connect, verify notebook 01's artifacts, and check in on notebook 02 without\n"
        "insisting on it - this notebook needs 02's scratch table, but not its scheduler."
    ),
    code(
        "import json\n"
        "import random\n"
        "\n"
        "import matplotlib.pyplot as plt\n"
        "\n"
        "from cityops_harness.checks import ok, check\n"
        "from cityops_harness.config import load_settings\n"
        "from cityops_harness.db import get_connection\n"
        "from cityops_harness.llm import chat_model\n"
        "from cityops_harness.state import require, verify\n"
        "from cityops_harness.tracing import init_tracing\n"
        "from cityops_harness import context, promote\n"
        "\n"
        "settings = load_settings()\n"
        "conn = get_connection(settings)\n"
        "require(conn, \"01_self_improving_copilot\")\n"
        "CHAT = chat_model(settings)\n"
        "HANDLER = init_tracing(settings)\n"
        "# Langfuse is optional all the way through: every invoke passes config=CFG.\n"
        "CFG = {\"callbacks\": [HANDLER]} if HANDLER else {}\n"
        "ok(f\"connected - provider={settings.llm_provider}, langfuse={settings.langfuse_mode}\")"
    ),
    md(
        "Notebook 02's status is reported, not enforced. Its scheduler jobs need\n"
        "`CREATE JOB`, which is a database grant, not a context-engineering concept -\n"
        "failing this notebook over it would be the wrong dependency. The one thing we\n"
        "genuinely need from 02 is its scratch table, so we backfill that if it is absent."
    ),
    code(
        "for desc, passed in verify(conn, \"02_scheduled_briefings\"):\n"
        "    print(f\"  {'✓' if passed else '·'} {desc}\")\n"
        "\n"
        "\n"
        "def ddl(sql):\n"
        "    \"\"\"Idempotent DDL: ORA-00955 (name already used) is the success case.\"\"\"\n"
        "    with conn.cursor() as cur:\n"
        "        try:\n"
        "            cur.execute(sql)\n"
        "        except Exception as exc:\n"
        "            if \"ORA-00955\" not in str(exc):\n"
        "                raise\n"
        "\n"
        "\n"
        "ddl(\"\"\"CREATE TABLE HARNESS_SCRATCH (\n"
        "         PATH        VARCHAR2(400) PRIMARY KEY,\n"
        "         CONTENT     CLOB,\n"
        "         STATUS      VARCHAR2(1) DEFAULT 'N' NOT NULL,\n"
        "         CREATED_AT  TIMESTAMP DEFAULT SYSTIMESTAMP)\"\"\")\n"
        "ok(\"notebook 02 scratch store available (backfilled if it was missing)\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the simulated inspection season
# --------------------------------------------------------------------------
SEASON = [
    md(
        "## 1 · A long inspection season\n\n"
        "Compaction only gets interesting when the transcript outgrows the window, so we\n"
        "need length. Generating 40 turns with an LLM would be slow, expensive, and\n"
        "different on every run - and none of that variation would teach anything. The\n"
        "season below is built deterministically from *real* findings in\n"
        "`CITY_INSPECTION_FINDING`, seeded so every learner compacts the same conversation.\n\n"
        "Three turns carry a **planted fact**: a specific, checkable detail we will come\n"
        "back for at the very end, long after compaction has had every opportunity to\n"
        "discard it."
    ),
    code(
        "ddl(\"\"\"CREATE TABLE HARNESS_TRANSCRIPT (\n"
        "         TURN_NO          NUMBER PRIMARY KEY,\n"
        "         SPEAKER          VARCHAR2(20),\n"
        "         CONTENT          CLOB,\n"
        "         PLANTED_FACT_ID  VARCHAR2(10))\"\"\")\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"DELETE FROM HARNESS_TRANSCRIPT\")\n"
        "    cur.execute(\n"
        "        \"SELECT asset_id, category, severity, DBMS_LOB.SUBSTR(description, 400, 1)\"\n"
        "        \"  FROM CITY_INSPECTION_FINDING ORDER BY finding_id\"\n"
        "    )\n"
        "    FINDINGS = cur.fetchall()\n"
        "\n"
        "check(len(FINDINGS) > 20, f\"{len(FINDINGS)} real findings available to narrate\")"
    ),
    code(
        "# The three facts the probe will hunt for, and the turns they land on.\n"
        "PLANTED = {\n"
        "    4:  (\"f1\", \"Pier 3 bearing plate is corroded through; it is the single reason \"\n"
        "               \"Harbor Bridge was prioritised for Q3.\"),\n"
        "    11: (\"f2\", \"The Riverside Culvert inspection used the 2019 rating scale, so its \"\n"
        "               \"grades are not comparable with the rest of this season.\"),\n"
        "    19: (\"f3\", \"Inspector Okafor signed off every North District report this season, \"\n"
        "               \"so a single reviewer bias applies to all of them.\"),\n"
        "}\n"
        "\n"
        "rng = random.Random(20260722)\n"
        "TURNS = []\n"
        "for turn_no in range(1, 41):\n"
        "    if turn_no in PLANTED:\n"
        "        fact_id, text = PLANTED[turn_no]\n"
        "        TURNS.append((turn_no, \"inspector\", text, fact_id))\n"
        "        continue\n"
        "    asset, category, severity, desc = rng.choice(FINDINGS)\n"
        "    TURNS.append((\n"
        "        turn_no,\n"
        "        \"inspector\" if turn_no % 2 else \"coordinator\",\n"
        "        f\"Turn {turn_no}: on {asset}, a {severity.lower()} {category.lower()} issue - \"\n"
        "        f\"{(desc or '').strip()}\",\n"
        "        None,\n"
        "    ))\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.executemany(\n"
        "        \"INSERT INTO HARNESS_TRANSCRIPT (turn_no, speaker, content, planted_fact_id)\"\n"
        "        \" VALUES (:1, :2, :3, :4)\",\n"
        "        TURNS,\n"
        "    )\n"
        "conn.commit()\n"
        "\n"
        "check(len(TURNS) == 40, \"40-turn season written\")\n"
        "check(sum(1 for t in TURNS if t[3]) == 3, \"3 planted facts, at turns 4, 11 and 19\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the card store
# --------------------------------------------------------------------------
CARD_STORE = [
    md(
        "## 2 · Where the card lives\n\n"
        "Every compaction writes a **new version** rather than overwriting the last one.\n"
        "That is what makes the size chart and the fidelity probe possible after the fact:\n"
        "you can see not just the final card, but the moment a fact fell out of it."
    ),
    code(
        "ddl(\"\"\"CREATE TABLE HARNESS_CARD (\n"
        "         CARD_VERSION      NUMBER PRIMARY KEY,\n"
        "         CREATED_AT        TIMESTAMP DEFAULT SYSTIMESTAMP,\n"
        "         TURNS_COVERED     NUMBER,\n"
        "         CARD_JSON         CLOB,\n"
        "         TRANSCRIPT_CHARS  NUMBER,\n"
        "         CARD_CHARS        NUMBER)\"\"\")\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"DELETE FROM HARNESS_CARD\")\n"
        "conn.commit()\n"
        "\n"
        "\n"
        "def save_card(version, turns_covered, card, transcript_chars):\n"
        "    \"\"\"Persist one compaction version. Returns the rendered card text.\"\"\"\n"
        "    body = context.render_card(card)\n"
        "    # ✏️ TODO(1): insert the card version, and return `body`.\n"
        "    #   Columns: CARD_VERSION, TURNS_COVERED, CARD_JSON, TRANSCRIPT_CHARS, CARD_CHARS.\n"
        "    #   CARD_CHARS is len(body) - the size half of the measurement.\n"
        "    # TODO-SOLUTION-START\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\n"
        "            \"INSERT INTO HARNESS_CARD\"\n"
        "            \" (card_version, turns_covered, card_json, transcript_chars, card_chars)\"\n"
        "            \" VALUES (:1, :2, :3, :4, :5)\",\n"
        "            (version, turns_covered, body, transcript_chars, len(body)),\n"
        "        )\n"
        "    conn.commit()\n"
        "    # TODO-SOLUTION-END\n"
        "    return body\n"
        "\n"
        "\n"
        "def latest_card():\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\n"
        "            \"SELECT card_json FROM HARNESS_CARD\"\n"
        "            \" ORDER BY card_version DESC FETCH FIRST 1 ROWS ONLY\"\n"
        "        )\n"
        "        row = cur.fetchone()\n"
        "    return context.parse_card(row[0].read() if hasattr(row[0], \"read\") else row[0]) if row else None\n"
        "\n"
        "\n"
        "EMPTY_CARD = {\"facts\": [], \"decisions\": [], \"open_questions\": []}\n"
        "ok(\"card store ready (versioned, never overwritten)\")"
    ),
]

# --------------------------------------------------------------------------
# Section: compaction
# --------------------------------------------------------------------------
COMPACTION = [
    md(
        "## 3 · Compaction\n\n"
        "We walk the season one turn at a time. Whenever the pending transcript reaches the\n"
        "budget, the model folds it into the running card and the buffer resets.\n\n"
        "Two design choices matter more than the prompt:\n\n"
        "1. **The card has a fixed schema** (`facts`, `decisions`, `open_questions`). A\n"
        "   free-form summary cannot be probed; a structured one can be, by set membership.\n"
        "2. **The merge is additive** (`context.merge_card`). The model proposes; it does\n"
        "   not get to silently delete. A fact leaves the card only when the model\n"
        "   explicitly corrects it - which means anything that *does* go missing is a real\n"
        "   finding about compaction, not an artefact of us overwriting the card each time."
    ),
    code(
        "COMPACTION_PROMPT = (\n"
        "    \"You are maintaining a compaction card for a bridge-inspection season.\\n\"\n"
        "    \"Return ONLY JSON with keys: facts, decisions, open_questions.\\n\"\n"
        "    \"  facts: list of {{id, text, turn}} - durable, specific claims. Reuse an\\n\"\n"
        "    \"    existing id to correct it; invent a new id (f4, f5, ...) otherwise.\\n\"\n"
        "    \"  decisions: list of strings. open_questions: list of strings.\\n\"\n"
        "    \"Keep anything a colleague would need in three months.\\n\\n\"\n"
        "    \"CURRENT CARD:\\n{card}\\n\\nNEW TURNS:\\n{turns}\"\n"
        ")\n"
        "\n"
        "\n"
        "def compact(card, pending_turns):\n"
        "    \"\"\"Fold pending turns into the card. Returns the merged card.\"\"\"\n"
        "    prompt = COMPACTION_PROMPT.format(\n"
        "        card=context.render_card(card),\n"
        "        turns=\"\\n\".join(f\"[{n}] {who}: {text}\" for n, who, text, _ in pending_turns),\n"
        "    )\n"
        "    # ✏️ TODO(2): call the model, parse its card, and merge it into `card`.\n"
        "    #   Use CHAT.invoke(prompt, config=CFG), context.parse_card, context.merge_card.\n"
        "    #   Strip any ```json fence before parsing.\n"
        "    # TODO-SOLUTION-START\n"
        "    raw = CHAT.invoke(prompt, config=CFG).content.strip()\n"
        "    if raw.startswith(\"```\"):\n"
        "        raw = raw.split(\"```\")[1].removeprefix(\"json\").strip()\n"
        "    update = context.parse_card(raw)\n"
        "    card = context.merge_card(card, update)\n"
        "    # TODO-SOLUTION-END\n"
        "    return card\n"
        "\n"
        "ok(\"compaction step defined\")"
    ),
    code(
        "card = dict(EMPTY_CARD)\n"
        "pending, transcript_chars, version = [], 0, 0\n"
        "\n"
        "for turn in TURNS:\n"
        "    pending.append(turn)\n"
        "    transcript_chars += len(turn[2])\n"
        "    if context.compaction_due(sum(len(t[2]) for t in pending)):\n"
        "        version += 1\n"
        "        card = compact(card, pending)\n"
        "        save_card(version, turn[0], card, transcript_chars)\n"
        "        print(f\"  v{version}: compacted through turn {turn[0]} - \"\n"
        "              f\"{len(card['facts'])} facts, {len(context.render_card(card))} chars\")\n"
        "        pending = []\n"
        "\n"
        "if pending:  # never strand the tail of the season\n"
        "    version += 1\n"
        "    card = compact(card, pending)\n"
        "    save_card(version, TURNS[-1][0], card, transcript_chars)\n"
        "    print(f\"  v{version}: final fold through turn {TURNS[-1][0]}\")\n"
        "\n"
        "check(version >= 2, f\"{version} card versions written across the season\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the size chart, and why it is not the answer
# --------------------------------------------------------------------------
CHART = [
    code(
        "with conn.cursor() as cur:\n"
        "    cur.execute(\n"
        "        \"SELECT card_version, transcript_chars, card_chars\"\n"
        "        \"  FROM HARNESS_CARD ORDER BY card_version\"\n"
        "    )\n"
        "    rows = cur.fetchall()\n"
        "\n"
        "versions = [r[0] for r in rows]\n"
        "fig, ax = plt.subplots(figsize=(7, 4))\n"
        "ax.plot(versions, [r[1] for r in rows], marker=\"o\", label=\"transcript (cumulative)\")\n"
        "ax.plot(versions, [r[2] for r in rows], marker=\"o\", label=\"compaction card\")\n"
        "ax.set_yscale(\"log\")\n"
        "ax.set_xlabel(\"card version\")\n"
        "ax.set_ylabel(\"characters (log scale)\")\n"
        "ax.set_title(\"What compaction saves\")\n"
        "ax.legend()\n"
        "ax.grid(True, which=\"both\", alpha=0.3)\n"
        "plt.tight_layout()\n"
        "plt.show()\n"
        "\n"
        "ratio = rows[-1][1] / max(rows[-1][2], 1)\n"
        "ok(f\"final card is {ratio:.1f}x smaller than the transcript it stands for\")"
    ),
    md(
        "### Read that chart sceptically\n\n"
        "It is a real result and it is **not sufficient**. Every point on it would look\n"
        "*better* if compaction simply threw more away - the best possible curve belongs to\n"
        "a card that kept nothing at all. Size tells you what compaction cost you to store.\n"
        "It says nothing about what it cost you to know.\n\n"
        "So we go and ask."
    ),
]

# --------------------------------------------------------------------------
# Section: the fidelity probe
# --------------------------------------------------------------------------
PROBE = [
    md(
        "## 4 · The probe: is it still in there?\n\n"
        "Turn 4 planted a reason. Thirty-six turns later, we ask the question whose answer\n"
        "*requires* that reason - with nothing to answer from but the card.\n\n"
        "Two levels of scoring, because they can disagree in an interesting way:\n\n"
        "- **Structural**: `context.card_fidelity` asks whether the fact id survived at all.\n"
        "- **Functional**: does the model's answer actually contain the planted detail?\n\n"
        "A fact can survive structurally and still be useless if compaction blurred it into\n"
        "something too generic to answer with."
    ),
    code(
        "PROBES = {\n"
        "    \"f1\": (\"Which pier did we flag, and what single reason put Harbor Bridge\"\n"
        "           \" at the top of the Q3 list?\", \"pier 3\"),\n"
        "    \"f2\": (\"Are all of this season's grades comparable with each other? If not,\"\n"
        "           \" which inspection is the exception and why?\", \"2019\"),\n"
        "    \"f3\": (\"Whose sign-off should a reviewer be careful about, and across which\"\n"
        "           \" district?\", \"okafor\"),\n"
        "}\n"
        "\n"
        "final_card = latest_card()\n"
        "hits, misses, recall = context.card_fidelity(list(PROBES), final_card)\n"
        "print(f\"structural recall: {recall:.0%}  (kept: {hits or '-'}, lost: {misses or '-'})\")\n"
        "\n"
        "answered = []\n"
        "# ✏️ TODO(3): for each probe, ask the model using ONLY the card as context,\n"
        "#   and record whether the expected detail appears in its answer.\n"
        "# TODO-SOLUTION-START\n"
        "for fact_id, (question, needle) in PROBES.items():\n"
        "    reply = CHAT.invoke(\n"
        "        \"Answer using ONLY the inspection card below. If the card does not contain\"\n"
        "        \" the answer, say exactly: NOT IN CARD.\\n\\n\"\n"
        "        f\"CARD:\\n{context.render_card(final_card)}\\n\\nQUESTION: {question}\",\n"
        "        config=CFG,\n"
        "    ).content\n"
        "    got = needle.lower() in reply.lower()\n"
        "    answered.append(got)\n"
        "    print(f\"  {'✓' if got else '✗'} {fact_id}: {reply.strip()[:120]}\")\n"
        "# TODO-SOLUTION-END\n"
        "\n"
        "functional = sum(answered) / len(PROBES)\n"
        "print(f\"functional recall: {functional:.0%}\")\n"
        "\n"
        "# Deliberately not 100%: compaction really does lose things, and a notebook that\n"
        "# only passes when nothing is ever lost would be teaching a fiction.\n"
        "check(recall >= 2 / 3, f\"card retained {recall:.0%} of facts planted up to 36 turns earlier\")\n"
        "if misses:\n"
        "    print(f\"lost along the way: {', '.join(misses)} - look at which card version dropped it\")"
    ),
    md(
        "### What the misses tell you\n\n"
        "Facts survive compaction when the card has a **slot** for them - that is the whole\n"
        "reason the card has a fixed schema rather than being a paragraph of prose. The\n"
        "first thing lossy summarisation discards is the category with the weakest slot,\n"
        "which is almost always `open_questions`: they read as incidental, and nothing in\n"
        "the transcript ever refers back to them.\n\n"
        "If a fact went missing above, find the version where it vanished\n"
        "(`SELECT card_version, card_json FROM HARNESS_CARD ORDER BY card_version`) and look\n"
        "at what the model was folding in at that moment. That, not the character count, is\n"
        "the feedback loop that improves a compaction prompt."
    ),
]

SECTIONS = [INTRO, SETUP, SEASON, CARD_STORE, COMPACTION, CHART, PROBE]


def build() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "name": "harness",
        "display_name": "CityOps Harness",
        "language": "python",
    }
    nb["cells"] = [cell for section in SECTIONS for cell in section]
    return nb


if __name__ == "__main__":
    nbf.write(build(), "notebooks/03_context_engineering_complete.ipynb")
    print("wrote notebooks/03_context_engineering_complete.ipynb")
