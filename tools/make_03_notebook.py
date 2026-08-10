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
        "# Must match notebook 02's schema exactly. `ddl` swallows ORA-00955, so a\n"
        "# divergent definition here would survive as the real table and break 02's\n"
        "# inserts later - the backfill has to be the same table, not a similar one.\n"
        "ddl(\"\"\"CREATE TABLE HARNESS_SCRATCH (\n"
        "         path       VARCHAR2(512) PRIMARY KEY,\n"
        "         content    CLOB NOT NULL,\n"
        "         revision   VARCHAR2(64) NOT NULL,\n"
        "         status     VARCHAR2(1) DEFAULT 'N'\n"
        "                    CHECK (status IN ('N','S','P','D','H')),\n"
        "         updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)\"\"\")\n"
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
    md(
        "**Build the season.** Three planted facts land on turns 4, 11 and 19; every other\n"
        "turn is deterministic filler drawn from a real finding, so the 40-turn transcript is\n"
        "identical on every run and the probe at the end is reproducible."
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
    md(
        "**Run the compaction loop.** Walk the season turn by turn; whenever the pending text\n"
        "reaches the budget, fold it into the card and reset the buffer. Every fold is saved\n"
        "as a new card *version*, which is what makes the size chart and the fidelity probe\n"
        "below possible after the fact."
    ),
    code(
        "# The season is a scale model: ~12k characters, where a real one runs into the\n"
        "# millions. Rather than inflate the transcript - slow, expensive, and no more\n"
        "# instructive - we shrink the budget by the same factor. The mechanism, and\n"
        "# everything it can lose, is identical.\n"
        "CARD_BUDGET = 2_000\n"
        "\n"
        "card = dict(EMPTY_CARD)\n"
        "pending, transcript_chars, version = [], 0, 0\n"
        "\n"
        "for turn in TURNS:\n"
        "    pending.append(turn)\n"
        "    transcript_chars += len(turn[2])\n"
        "    if context.compaction_due(sum(len(t[2]) for t in pending), CARD_BUDGET):\n"
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
    md(
        "**Chart card size vs transcript size.** Pull every saved card version and plot the\n"
        "two growth curves on a log axis. Then read the caption underneath - the number this\n"
        "chart reports is necessary but nowhere near sufficient."
    ),
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
        "if ratio >= 1:\n"
        "    ok(f\"final card is {ratio:.1f}x smaller than the transcript it stands for\")\n"
        "else:\n"
        "    ok(f\"final card is {1 / ratio:.1f}x LARGER than the transcript - read on\")"
    ),
    md(
        "### Read that chart sceptically\n\n"
        "You may well have just watched the card grow *past* the transcript. That is not a\n"
        "bug in the run; it is the direct consequence of a choice made two cells ago, and it\n"
        "is worth sitting with.\n\n"
        "`context.merge_card` is **additive**: the model can add a fact or correct one, but\n"
        "it cannot delete. That was deliberate - it means any fact missing from the final\n"
        "card was genuinely lost by summarisation rather than quietly overwritten by us, so\n"
        "the probe in the next section measures something real. The cost is that nothing\n"
        "ever leaves, and a card that never forgets is not a compaction card. It is a log.\n\n"
        "**Both halves of that trade are the lesson.** A card that forgets nothing has\n"
        "perfect fidelity and no compression. A card that forgets aggressively has excellent\n"
        "compression and unknown fidelity - and \"unknown\" is the part the original section\n"
        "never measured, because it only ever plotted the size.\n\n"
        "Real systems bound the card: keep at most N facts, evict by age or by how recently\n"
        "a fact was referenced, and *re-run the probe after every eviction policy change*.\n"
        "Notebook 04 does exactly that as a scored eval. Here we hold the policy still at\n"
        "one extreme so the measurement below is unambiguous.\n\n"
        "Either way, the chart alone could never tell you which regime you are in. So we go\n"
        "and ask."
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

# --------------------------------------------------------------------------
# Section: offloading, with the agent in the loop
# --------------------------------------------------------------------------
OFFLOAD = [
    md(
        "## 5 · Offloading large tool results\n\n"
        "Compaction manages the conversation. Offloading manages the *attachments*: a tool\n"
        "returns 40KB of JSON, and putting it in the context window would evict everything\n"
        "else. So we store the payload, hand the model a **reference**, and let it decide.\n\n"
        "The original section stopped at \"the bytes are recoverable\", which is a property of\n"
        "the storage layer, not of the agent. The interesting question is behavioural: shown\n"
        "a reference instead of data, does the model *notice*, *fetch*, and *use* it? We are\n"
        "going to ask it something it cannot possibly answer from the stub, and check."
    ),
    code(
        "ddl(\"\"\"CREATE TABLE HARNESS_BLOB (\n"
        "         BLOB_ID      VARCHAR2(12) PRIMARY KEY,\n"
        "         CREATED_AT   TIMESTAMP DEFAULT SYSTIMESTAMP,\n"
        "         SOURCE_TOOL  VARCHAR2(60),\n"
        "         PATH         VARCHAR2(400),\n"
        "         PAYLOAD      CLOB,\n"
        "         BYTES        NUMBER)\"\"\")\n"
        "\n"
        "\n"
        "def store_blob(source_tool, payload):\n"
        "    blob_id = context.new_blob_id()\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\n"
        "            \"INSERT INTO HARNESS_BLOB (blob_id, source_tool, path, payload, bytes)\"\n"
        "            \" VALUES (:1, :2, :3, :4, :5)\",\n"
        "            (blob_id, source_tool, context.blob_path(blob_id), payload, len(payload)),\n"
        "        )\n"
        "    conn.commit()\n"
        "    return blob_id\n"
        "\n"
        "\n"
        "def fetch_blob(blob_id):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"SELECT payload FROM HARNESS_BLOB WHERE blob_id = :1\", (blob_id,))\n"
        "        row = cur.fetchone()\n"
        "    if not row:\n"
        "        return None\n"
        "    return row[0].read() if hasattr(row[0], \"read\") else row[0]\n"
        "\n"
        "ok(\"blob store ready\")"
    ),
    md(
        "**Pick a target and compute the ground truth.** The busiest asset gives an export\n"
        "big enough to be worth offloading. Ground truth is a deliberate *lookup* (the oldest\n"
        "finding's opaque id), not a count - an id can only appear in the answer if the model\n"
        "actually read the payload, which is exactly what we want to prove."
    ),
    code(
        "# The busiest asset gives us an export big enough to be worth offloading.\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\n"
        "        \"SELECT asset_id FROM CITY_INSPECTION_FINDING\"\n"
        "        \" GROUP BY asset_id ORDER BY COUNT(*) DESC, asset_id FETCH FIRST 1 ROWS ONLY\"\n"
        "    )\n"
        "    (TARGET_ASSET,) = cur.fetchone()\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\n"
        "        \"SELECT finding_id, severity, category, DBMS_LOB.SUBSTR(description, 600, 1), days_ago\"\n"
        "        \"  FROM CITY_INSPECTION_FINDING WHERE asset_id = :1 ORDER BY days_ago\",\n"
        "        (TARGET_ASSET,),\n"
        "    )\n"
        "    EXPORT_ROWS = [\n"
        "        {\"finding_id\": r[0], \"severity\": r[1], \"category\": r[2],\n"
        "         \"description\": r[3], \"days_ago\": r[4]}\n"
        "        for r in cur.fetchall()\n"
        "    ]\n"
        "\n"
        "# Ground truth, computed in Python - the model has to match this, not be graded by it.\n"
        "# A *lookup*, deliberately, not a count. Asking for a tally over 36 rows tests the\n"
        "# model's arithmetic, and any number it produces might appear in the answer for\n"
        "# unrelated reasons (list numbering, for one). An opaque finding_id cannot appear\n"
        "# unless the payload was actually read - which is the only thing we want to prove.\n"
        "# The sort key breaks ties explicitly so the question has exactly one right answer.\n"
        "OLDEST = max(EXPORT_ROWS, key=lambda r: (r[\"days_ago\"], r[\"finding_id\"]))\n"
        "EXPORT_JSON = json.dumps(EXPORT_ROWS, default=str)\n"
        "\n"
        "check(context.offload_decision(len(EXPORT_JSON)) == \"offload\",\n"
        "      f\"{TARGET_ASSET} export is {len(EXPORT_JSON)} chars - too big to inline\")\n"
        "print(f\"ground truth: oldest finding is {OLDEST['finding_id']} \"\n"
        "      f\"({OLDEST['days_ago']} days ago, {OLDEST['severity']} {OLDEST['category']})\")"
    ),
    md(
        "**Define the two tools.** `bulk_inspection_export` returns a `harness://blob/<id>`\n"
        "reference instead of the payload when the result is too big; `fetch_offloaded`\n"
        "redeems that reference. `FETCH_LOG` records every id the model asks for, so we can\n"
        "later prove it fetched rather than guessed."
    ),
    code(
        "from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage\n"
        "from langchain_core.tools import tool\n"
        "\n"
        "FETCH_LOG = []   # every blob_id the model asked for, in order\n"
        "\n"
        "\n"
        "@tool\n"
        "def bulk_inspection_export(asset_id: str) -> str:\n"
        "    \"\"\"Export every inspection finding for an asset. Large results are offloaded\n"
        "    and returned as a harness://blob/<id> reference instead of inline data.\"\"\"\n"
        "    payload = EXPORT_JSON\n"
        "    if context.offload_decision(len(payload)) == \"inline\":\n"
        "        return payload\n"
        "    blob_id = store_blob(\"bulk_inspection_export\", payload)\n"
        "    return (f\"[result offloaded: {context.blob_reference(blob_id)} - \"\n"
        "            f\"{len(EXPORT_ROWS)} findings, {len(payload)} bytes]\")\n"
        "\n"
        "\n"
        "@tool\n"
        "def fetch_offloaded(blob_id: str) -> str:\n"
        "    \"\"\"Retrieve the full payload of a previously offloaded result by its blob id.\"\"\"\n"
        "    # ✏️ TODO(4): record the fetch in FETCH_LOG and return the payload.\n"
        "    #   Return a clear error string if the id is unknown - the model should be able\n"
        "    #   to recover from a bad id, not crash the run.\n"
        "    # TODO-SOLUTION-START\n"
        "    FETCH_LOG.append(blob_id)\n"
        "    payload = fetch_blob(blob_id)\n"
        "    return payload if payload is not None else f\"ERROR: no blob {blob_id}\"\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "OFFLOAD_TOOLS = {t.name: t for t in [bulk_inspection_export, fetch_offloaded]}\n"
        "ok(f\"{len(OFFLOAD_TOOLS)} tools defined - one offloads, one redeems the reference\")"
    ),
    md(
        "**Let the agent run.** Ask a question the stub reference cannot answer, then loop:\n"
        "the model calls a tool, we feed the result back, repeat until it stops. If it never\n"
        "fetches the blob, that is a real finding about the prompt - so we let it fail rather\n"
        "than nudging it."
    ),
    code(
        "OFFLOAD_SYSTEM = (\n"
        "    \"You are the CityOps inspection copilot. You act through tools.\\n\"\n"
        "    \"Some tool results are too large to return inline; they come back as a\\n\"\n"
        "    \"harness://blob/<id> reference. A reference is not an answer - if you need what\\n\"\n"
        "    \"is inside it, call fetch_offloaded with that id.\\n\"\n"
        "    \"Answer only from data you have actually seen. Be concise: two sentences.\"\n"
        ")\n"
        "\n"
        "QUESTION = (f\"Export all inspection findings for {TARGET_ASSET}. Which finding_id has\"\n"
        "            f\" the largest days_ago - if several tie, the one whose finding_id sorts\"\n"
        "            f\" last - and what are its severity and category?\")\n"
        "\n"
        "model = CHAT.bind_tools(list(OFFLOAD_TOOLS.values()))\n"
        "msgs = [SystemMessage(content=OFFLOAD_SYSTEM), HumanMessage(content=QUESTION)]\n"
        "tool_outputs = []\n"
        "resp = None\n"
        "\n"
        "for _ in range(6):\n"
        "    resp = model.invoke(msgs, config=CFG)\n"
        "    msgs.append(resp)\n"
        "    if not getattr(resp, \"tool_calls\", None):\n"
        "        break\n"
        "    for tc in resp.tool_calls:\n"
        "        try:\n"
        "            result = str(OFFLOAD_TOOLS[tc[\"name\"]].invoke(tc[\"args\"]))\n"
        "        except Exception as e:\n"
        "            result = f\"ERROR: {type(e).__name__}: {e}\"\n"
        "        tool_outputs.append((tc[\"name\"], result))\n"
        "        print(f\"  -> {tc['name']}({tc['args']}) = {result[:90]}\")\n"
        "        msgs.append(ToolMessage(content=result, tool_call_id=tc[\"id\"]))\n"
        "\n"
        "answer = resp.content if resp is not None else \"\"\n"
        "if isinstance(answer, list):\n"
        "    answer = \"\".join(p.get(\"text\", \"\") if isinstance(p, dict) else str(p) for p in answer)\n"
        "print(\"\\nANSWER:\", answer.strip()[:400])"
    ),
    md(
        "**Check the loop, not the bytes.** Three assertions: the tool handed back a\n"
        "reference, the model fetched an id it was actually shown, and its final answer names\n"
        "the opaque finding_id from the payload. Only the last proves the agent *used* what it\n"
        "fetched - the check the original section never made."
    ),
    code(
        "# Three assertions, and only the third one is about the agent doing its job.\n"
        "stub = next((out for name, out in tool_outputs if name == \"bulk_inspection_export\"), \"\")\n"
        "offered = context.parse_blob_references(stub)\n"
        "check(bool(offered), \"the export tool handed back a blob reference, not 40KB of JSON\")\n"
        "\n"
        "# (a) the model derived the id from the reference it was shown - it did not guess.\n"
        "check(bool(FETCH_LOG) and FETCH_LOG[0] in offered,\n"
        "      f\"the model noticed the reference and fetched it ({FETCH_LOG[:1]})\")\n"
        "\n"
        "# (b) the payload actually reached the context window.\n"
        "fetched = next((out for name, out in tool_outputs if name == \"fetch_offloaded\"), \"\")\n"
        "check(EXPORT_ROWS[0][\"finding_id\"] in fetched,\n"
        "      \"the fetched payload entered the conversation\")\n"
        "\n"
        "# (c) and it was *used*. This is the check the original section never made.\n"
        "#     The id is opaque: it appears here only if the model read the payload.\n"
        "check(OLDEST[\"finding_id\"] in answer,\n"
        "      f\"the answer names {OLDEST['finding_id']} - a value only present in the payload\")"
    ),
    md(
        "If any of those failed, read the trace above rather than re-running until it\n"
        "passes. A model that ignores the reference and answers from the stub is telling you\n"
        "something true about your prompt: the system message has to say plainly that a\n"
        "reference is not an answer. \"Bytes are recoverable\" would have scored this run\n"
        "green either way - which is exactly why it was the wrong measurement."
    ),
]

# --------------------------------------------------------------------------
# Section: offloading x promotion
# --------------------------------------------------------------------------
EXCLUSION = [
    md(
        "## 6 · Offloaded blobs must never be promoted\n\n"
        "This is the interaction the review flagged as untested. Notebook 02 promotes\n"
        "curated notes into long-term memory. Offloading writes large, machine-generated\n"
        "dumps to disk-like paths. If those two features meet without a rule between them,\n"
        "a 40KB JSON export gets embedded, chunked and remembered forever as though a human\n"
        "had written it down on purpose.\n\n"
        "So we put the blob paths in front of notebook 02's real gate and watch what happens."
    ),
    code(
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"DELETE FROM HARNESS_SCRATCH WHERE path LIKE '/tool_out/blob/%'\")\n"
        "    cur.execute(\"SELECT blob_id, path FROM HARNESS_BLOB\")\n"
        "    blob_rows = cur.fetchall()\n"
        "    for blob_id, path in blob_rows:\n"
        "        body = f\"offloaded export {blob_id}\"\n"
        "        cur.execute(\n"
        "            \"INSERT INTO HARNESS_SCRATCH (path, content, revision, status)\"\n"
        "            \" VALUES (:1, :2, :3, 'N')\",\n"
        "            (path, body, promote.note_revision(body)),\n"
        "        )\n"
        "    # ...and one genuine curated note, so we can tell a rule from a blanket veto.\n"
        "    cur.execute(\"DELETE FROM HARNESS_SCRATCH WHERE path = :1\", (\"/inbox/\" + TARGET_ASSET + \"/season.md\",))\n"
        "    _season_note = (f\"Season summary for {TARGET_ASSET}: {len(EXPORT_ROWS)} findings \"\n"
        "                    f\"on file; the oldest still open is {OLDEST['finding_id']}.\")\n"
        "    cur.execute(\n"
        "        \"INSERT INTO HARNESS_SCRATCH (path, content, revision, status)\"\n"
        "        \" VALUES (:1, :2, :3, 'N')\",\n"
        "        (f\"/inbox/{TARGET_ASSET}/season.md\", _season_note,\n"
        "         promote.note_revision(_season_note)),\n"
        "    )\n"
        "conn.commit()\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"SELECT path FROM HARNESS_SCRATCH WHERE status = 'N'\")\n"
        "    candidates = [r[0] for r in cur.fetchall()]\n"
        "print(f\"{len(candidates)} notes awaiting triage\")"
    ),
    md(
        "**Run notebook 02's gate over the mix.** Every blob path plus one genuinely curated\n"
        "`/inbox` note go through the promotion rule. The two checks assert both directions:\n"
        "every blob is refused, and the real note still promotes - a specific rule, not a\n"
        "blanket veto."
    ),
    code(
        "def promotable(path):\n"
        "    \"\"\"Notebook 02's opt-in gate, plus an explicit bar on offloaded payloads.\"\"\"\n"
        "    # ✏️ TODO(5): a note is promotable only if it is inside the opt-in area AND\n"
        "    #   is not an offloaded blob. Use promote.triage_allowed and\n"
        "    #   context.is_offloaded_blob.\n"
        "    # TODO-SOLUTION-START\n"
        "    return promote.triage_allowed(path) and not context.is_offloaded_blob(path)\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "verdicts = {p: promotable(p) for p in candidates}\n"
        "with conn.cursor() as cur:\n"
        "    for path, allowed in verdicts.items():\n"
        "        cur.execute(\"UPDATE HARNESS_SCRATCH SET status = :1 WHERE path = :2\",\n"
        "                    (\"S\" if allowed else \"D\", path))\n"
        "conn.commit()\n"
        "\n"
        "for path, allowed in sorted(verdicts.items()):\n"
        "    print(f\"  {'PROMOTE' if allowed else 'discard'}  {path}\")\n"
        "\n"
        "blobs = [p for p in verdicts if context.is_offloaded_blob(p)]\n"
        "check(bool(blobs) and not any(verdicts[p] for p in blobs),\n"
        "      f\"all {len(blobs)} offloaded blob(s) refused promotion\")\n"
        "check(any(allowed for path, allowed in verdicts.items() if not context.is_offloaded_blob(path)),\n"
        "      \"a genuinely curated /inbox note still promotes - a rule, not a blanket veto\")"
    ),
    md(
        "### Belt *and* braces, on purpose\n\n"
        "`/tool_out/` already sits outside notebook 02's `/inbox/` opt-in prefix, so today\n"
        "`triage_allowed` alone would have refused these paths. The second condition looks\n"
        "redundant - and that is precisely the argument for writing it down.\n\n"
        "The opt-in prefix is a *product* decision that will change (someone will widen it\n"
        "to `/inbox/` plus `/reports/`, or drop the prefix scheme entirely). The rule that\n"
        "machine-generated offload payloads are not memories is an *architectural* one that\n"
        "should survive that change. Encoding it as an accident of string prefixes means it\n"
        "silently stops holding the day someone edits an unrelated constant."
    ),
]

# --------------------------------------------------------------------------
# Section: closing
# --------------------------------------------------------------------------
CLOSING = [
    md("## 7 · State check"),
    code(
        "for desc, passed in verify(conn, \"03_context_engineering\"):\n"
        "    check(passed, desc)\n"
        "ok(\"context engineering complete - continue to 04_evals\")"
    ),
    md(
        "### What notebook 04 does with this\n\n"
        "Two of the five evals are this notebook, run properly:\n\n"
        "- **Card fidelity over a long horizon** generalises §4. One season and three\n"
        "  planted facts is an anecdote; the eval runs multi-topic, adversarially spaced\n"
        "  sessions and reports drift as a distribution, not a single percentage.\n"
        "- **Cost per correct answer** puts §3 and §5 on the same axis as the alternatives -\n"
        "  card vs. full transcript vs. stateless - with repeated trials and variance, which\n"
        "  is what the original 8.4 lacked at n=1.\n\n"
        "The habit to carry forward is the one this notebook is built around: every time you\n"
        "make the context smaller, you have made a claim about what is still in there. Write\n"
        "the probe that tests the claim, and let it fail sometimes."
    ),
]

# --------------------------------------------------------------------------
# Section: compaction that actually forgets (strength-based consolidation)
# --------------------------------------------------------------------------
CONSOLIDATION = [
    md(
        "## 4b · Making it forget, on purpose\n\n"
        "The card above never shrank because `merge_card` is additive - nothing may leave.\n"
        "That kept the probe honest, but a card that only grows is a log, not a compaction.\n"
        "A real card needs two things the additive one lacked: a **ceiling** (a reason to\n"
        "compress at all) and a principled rule for **what gives way** when the ceiling bites.\n\n"
        "The tempting rule - evict the oldest - is wrong, and wrong in a way that matters\n"
        "here: the turn-4 Pier 3 fact is the *most* important thing in the season and among\n"
        "the oldest. Human memory doesn't forget by age; it forgets by **retrieval\n"
        "strength**. A fact referenced again and again stays sharp; one nobody revisits\n"
        "fades - and fades to its **gist** before it vanishes. `context.select_for_eviction`\n"
        "ranks by `fact_strength` (reinforcement up, disuse down, same half-life as recall),\n"
        "and evicted facts consolidate into a `gist` line rather than disappearing."
    ),
    code(
        "CEILING = 4_000            # the card may not exceed this; the additive one hit ~16k\n"
        "STRENGTH_PROMPT = (\n"
        "    \"Maintain a compaction card. Return ONLY JSON with keys facts, decisions,\\n\"\n"
        "    \"open_questions, reinforced. facts is a list of {{id,text,turn}} - reuse an id\\n\"\n"
        "    \"to correct it, invent f4+ otherwise. reinforced is a list of existing fact ids\\n\"\n"
        "    \"that the NEW TURNS touched again (empty if none).\\n\\n\"\n"
        "    \"CARD:\\n{card}\\n\\nNEW TURNS:\\n{turns}\")\n"
        "\n"
        "\n"
        "def _say(prompt):\n"
        "    c = CHAT.invoke(prompt, config=CFG).content\n"
        "    return c if isinstance(c, str) else \"\".join(\n"
        "        p.get(\"text\", \"\") if isinstance(p, dict) else str(p) for p in c)\n"
        "\n"
        "\n"
        "def compact_strength(card, pending, turn_no):\n"
        "    \"\"\"Fold like compact(), then reinforce, then evict-to-gist under the ceiling.\"\"\"\n"
        "    raw = _say(STRENGTH_PROMPT.format(card=context.render_card(card),\n"
        "               turns=\"\\n\".join(f\"[{n}] {who}: {text}\" for n, who, text, _ in pending))).strip()\n"
        "    if raw.startswith(\"```\"):\n"
        "        raw = raw.split(\"```\")[1].removeprefix(\"json\").strip()\n"
        "    update = context.parse_card(raw)\n"
        "    reinforced = update.get(\"reinforced\", [])\n"
        "    gist = card.get(\"gist\", [])                     # merge_card drops unknown keys\n"
        "    card = context.merge_card(card, update)\n"
        "    card[\"gist\"] = gist\n"
        "    for f in card[\"facts\"]:                          # reinforcement + recency bookkeeping\n"
        "        if f[\"id\"] in reinforced:\n"
        "            f[\"reinforcements\"] = f.get(\"reinforcements\", 0) + 1\n"
        "            f[\"last_seen\"] = turn_no\n"
        "        else:\n"
        "            f.setdefault(\"last_seen\", f.get(\"turn\", turn_no))\n"
        "    kept, evicted = context.select_for_eviction(card, current_turn=turn_no,\n"
        "                                                ceiling_chars=CEILING, floor_facts=3)\n"
        "    if evicted:\n"
        "        summary = _say(\"Compress these dropped inspection facts into ONE short sentence \"\n"
        "                       \"that keeps the gist and loses the specifics:\\n\"\n"
        "                       + \"\\n\".join(f\"- {f['text']}\" for f in evicted)).strip()\n"
        "        kept.setdefault(\"gist\", []).append(\n"
        "            {\"ids\": [f[\"id\"] for f in evicted], \"text\": summary})\n"
        "    return kept\n"
        "\n"
        "ok(\"strength-based compaction defined (ceiling + reinforcement + gist)\")"
    ),
    md(
        "**Run the strength-based policy over the same season.** Same fold points as before,\n"
        "but now each fold reinforces the facts it touched and then evicts the weakest ones\n"
        "into `gist` until the card is back under its ceiling. Watch the fact/gist counts\n"
        "trade off as it holds the line."
    ),
    code(
        "scard = {\"facts\": [], \"decisions\": [], \"open_questions\": [], \"gist\": []}\n"
        "pending, strength_sizes = [], []\n"
        "for turn in TURNS:\n"
        "    pending.append(turn)\n"
        "    if context.compaction_due(sum(len(t[2]) for t in pending), CARD_BUDGET):\n"
        "        scard = compact_strength(scard, pending, turn[0])\n"
        "        strength_sizes.append((turn[0], len(context.render_card(scard))))\n"
        "        print(f\"  through turn {turn[0]:>2}: {len(scard['facts'])} facts + \"\n"
        "              f\"{len(scard.get('gist', []))} gist -> {strength_sizes[-1][1]} chars\")\n"
        "        pending = []\n"
        "if pending:\n"
        "    scard = compact_strength(scard, pending, TURNS[-1][0])\n"
        "    strength_sizes.append((TURNS[-1][0], len(context.render_card(scard))))\n"
        "\n"
        "check(strength_sizes[-1][1] <= CEILING * 1.1,\n"
        "      f\"strength card held near its {CEILING}-char ceiling ({strength_sizes[-1][1]} chars)\")"
    ),
    md(
        "**Plot the two policies together.** The additive card (from section 3, read back out\n"
        "of `HARNESS_CARD`) against the strength-based one, with the ceiling drawn in. This is\n"
        "the compression the size chart in section 3 could not show."
    ),
    code(
        "# Two policies, same season: the additive card (from section 3) vs this one.\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"SELECT turns_covered, card_chars FROM HARNESS_CARD ORDER BY card_version\")\n"
        "    additive = cur.fetchall()\n"
        "\n"
        "fig, ax = plt.subplots(figsize=(7, 4))\n"
        "ax.plot([t for t, _ in additive], [c for _, c in additive], marker=\"o\", label=\"additive\")\n"
        "ax.plot([t for t, _ in strength_sizes], [c for _, c in strength_sizes], marker=\"s\",\n"
        "        label=\"strength-based\")\n"
        "ax.axhline(CEILING, ls=\"--\", color=\"grey\", alpha=0.6, label=f\"ceiling {CEILING}\")\n"
        "ax.set_xlabel(\"turns covered\"); ax.set_ylabel(\"card chars\")\n"
        "ax.set_title(\"Additive grows without bound; strength-based holds the line\")\n"
        "ax.legend(); ax.grid(True, alpha=0.3)\n"
        "plt.tight_layout(); plt.show()\n"
        "\n"
        "add_final, str_final = additive[-1][1], strength_sizes[-1][1]\n"
        "print(f\"final: additive {add_final} chars vs strength {str_final} chars\")\n"
        "check(str_final < add_final,\n"
        "      f\"strength-based compaction actually compresses ({str_final} < {add_final})\")"
    ),
    md(
        "**Score fidelity three ways.** For each planted fact, `fact_status` reports whether\n"
        "it survived **verbatim**, faded to **gist**, or was **lost** - then we probe the card\n"
        "to see what each survival level can actually answer. This is the honesty the size\n"
        "chart alone can never give you."
    ),
    code(
        "# The three-way measure the size chart still cannot make: verbatim / gist / lost.\n"
        "_fact_text = {fid: text for _, (fid, text) in PLANTED.items()}\n"
        "status = context.fact_status(list(PROBES), scard)\n"
        "for fid, st in status.items():\n"
        "    print(f\"  {fid} ({_fact_text[fid][:44]}...): {st}\")\n"
        "\n"
        "scard_text = context.render_card(scard)\n"
        "for fid, (question, needle) in PROBES.items():\n"
        "    reply = _say(\"Answer using ONLY this card - it has verbatim facts AND a gist of \"\n"
        "                 \"older ones. If absent, say NOT IN CARD.\\n\\n\" + scard_text\n"
        "                 + \"\\n\\nQUESTION: \" + question)\n"
        "    print(f\"  {fid} [{status[fid]}] -> {reply.strip()[:80]}\")\n"
        "\n"
        "check(all(v != \"lost\" for v in status.values()),\n"
        "      \"no planted fact was fully lost - what left the facts list lives on as gist\")"
    ),
    md(
        "### What changed, and what it cost\n\n"
        "The strength-based card holds its ceiling while the additive one runs away - that is\n"
        "the compression section 3 could not show. And the honesty is *better*, not worse:\n"
        "`fact_status` reports each planted fact as **verbatim**, **gist**, or **lost**, so a\n"
        "fact that faded to its gist is a pass for *\"which bridge?\"* and a visible, measured\n"
        "loss for *\"which pier?\"* - exactly the distinction a hit/miss recall throws away.\n\n"
        "This is the instrument [notebook 04's card-fidelity eval](04_evals_complete.ipynb)\n"
        "would grade at scale: run both policies over many spaced seasons and score the\n"
        "verbatim/gist/lost distribution, not a single season's anecdote. The strength model\n"
        "is a starting point - reinforcement from the fold prompt is coarse, and retrieval\n"
        "itself should strengthen a fact - but it forgets the way a colleague does, not the\n"
        "way a TTL does."
    ),
]

SECTIONS = [INTRO, SETUP, SEASON, CARD_STORE, COMPACTION, CHART, PROBE, CONSOLIDATION,
            OFFLOAD, EXCLUSION, CLOSING]


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
