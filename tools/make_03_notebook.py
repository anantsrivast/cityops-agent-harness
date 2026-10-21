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
        "# 03 - Context Engineering: measuring what survives, not what shrinks\n"
        "\n"
        "Notebooks 01 and 02 fixed how the harness *learns*. This notebook fixes how it\n"
        "*forgets* - and, more importantly, how you find out what it forgot.\n"
        "\n"
        "A long conversation has to be compressed before it goes back into a prompt. Agent\n"
        "Memory does that for you: every thread keeps a running **summary**, extracts durable\n"
        "**memories** from the turns, and assembles both into a **context card** for the next\n"
        "call. Each of those steps is lossy on purpose. A smaller card is trivially easy to\n"
        "produce - throw everything away and the size chart looks fantastic. The only\n"
        "interesting question is what the card still knows when a fact is finally needed.\n"
        "\n"
        "| Review gap (8.1 / 8.2b) | This notebook |\n"
        "|---|---|\n"
        "| Card judged by character count | **Fidelity probe**: a fact planted at turn 4, asked for at turn 40 - through the summary alone, the full context card, and the raw transcript when both fail |\n"
        "| \"The bytes are recoverable\" declared a win | **Agent in the loop**: the model must notice the reference, fetch it, and use the payload |\n"
        "| Offloading and promotion never tested together | Offloaded blobs are **barred from promotion**, and the notebook proves it |"
    ),
]

# --------------------------------------------------------------------------
# Section: setup
# --------------------------------------------------------------------------
SETUP = [
    md(
        "## 0 \u00b7 Setup\n"
        "\n"
        "Connect, verify notebooks 01 and 02, open the memory store. Notebook 02 is a hard\n"
        "dependency now: this notebook posts a whole season into its store and reads the store's\n"
        "own context card back."
    ),
    code(
        "import json\n"
        "import random\n"
        "\n"
        "from cityops_harness.checks import ok, check\n"
        "from cityops_harness.config import load_settings\n"
        "from cityops_harness.db import get_connection\n"
        "from cityops_harness.embed import OracleONNXEmbedder\n"
        "from cityops_harness.llm import chat_model, litellm_spec\n"
        "from cityops_harness.state import require, verify\n"
        "from cityops_harness.tracing import init_tracing\n"
        "from cityops_harness import context, promote\n"
        "\n"
        "settings = load_settings()\n"
        "conn = get_connection(settings)\n"
        "require(conn, \"01_self_improving_copilot\")\n"
        "require(conn, \"02_scheduled_briefings\")\n"
        "HANDLER = init_tracing(settings)\n"
        "# Bind tracing once: every CHAT.invoke below is traced without passing callbacks.\n"
        "CHAT = chat_model(settings)\n"
        "if HANDLER:\n"
        "    CHAT = CHAT.with_config(callbacks=[HANDLER])\n"
        "ok(f\"connected - provider={settings.llm_provider}, langfuse={settings.langfuse_mode}\")"
    ),
    code(
        "from oracleagentmemory.core import MemoryExtractionConfig, OracleAgentMemory, SchemaPolicy\n"
        "from oracleagentmemory.core.extractors.memoryextractionconfig import (\n"
        "    MemoryExtractionMode,\n"
        "    MemoryLinkExtractionMode,\n"
        ")\n"
        "from oracleagentmemory.core.llms.llm import Llm as SdkLlm\n"
        "\n"
        "# Notebook 02 created the managed schema; this notebook only requires it.\n"
        "memory = OracleAgentMemory(\n"
        "    connection=conn,\n"
        "    embedder=OracleONNXEmbedder(conn, settings.embed_model),\n"
        "    llm=SdkLlm(**litellm_spec(settings)),\n"
        "    schema_policy=SchemaPolicy.REQUIRE_EXISTING,\n"
        "    table_name_prefix=\"CITY_\",\n"
        ")\n"
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
        "ok(\"memory store open (CITY_ tables, notebook 02's schema)\")"
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
        "`CITY_INSPECTION_FINDING`, seeded so every learner posts the same conversation.\n\n"
        "Three turns carry a **planted fact**: a specific, checkable detail we will come\n"
        "back for at the very end, long after the store's summary has had every opportunity\n"
        "to discard it."
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
# Section: the same season, through the store's summary and context card
# --------------------------------------------------------------------------
CHECKPOINTS = [
    md(
        "## 2 \u00b7 The same season, through the store\n"
        "\n"
        "Post the forty turns to one thread of notebook 02's store, with the store doing what it\n"
        "would do for any production agent: **extraction on** at its default policy (atomic\n"
        "facts - these are conversation turns, not the curated notes 02 keeps verbatim), a\n"
        "**running summary** on, links off (nothing in this season supersedes anything, and every\n"
        "link pass is a model call).\n"
        "\n"
        "Turns go in batches of eight. Each batch is one extraction pass and one summary refresh,\n"
        "so the store compresses the season at five checkpoints - and at each one we read back\n"
        "the two things the next prompt would be given:\n"
        "\n"
        "- `get_summary()` - the running summary. Each refresh rewrites the *previous summary*\n"
        "  plus the new turns, so by turn 40 a turn-4 detail has been paraphrased five times.\n"
        "- `get_context_card()` - that summary plus up to eight memories the store retrieves\n"
        "  **by querying with the summary itself**, plus the thread's topics. A detail the\n"
        "  summary has blurred can still come back here, if extraction kept it as a memory and\n"
        "  the summary still points near it.\n"
        "\n"
        "Every message carries its turn number and planted-fact id as metadata. That is\n"
        "provenance - and the handle \u00a74 will use to walk back to the transcript. Each run\n"
        "deletes the previous run's season thread first, which removes its messages, memories\n"
        "and summaries together."
    ),
    code(
        "SEASON_USER = \"inspection-season\"\n"
        "BATCH = 8\n"
        "NEEDLES = {\"f1\": \"pier 3\", \"f2\": \"2019\", \"f3\": \"okafor\"}\n"
        "\n"
        "SEASON_EXTRACTION = MemoryExtractionConfig(\n"
        "    extract_memories=True,\n"
        "    extraction_mode=MemoryExtractionMode.INLINE,       # memories exist when add_messages returns\n"
        "    memory_extraction_window=-1,                       # judge only the batch just posted...\n"
        "    memory_extraction_frequency=-1,                    # ...after every post\n"
        "    memory_link_extraction_mode=MemoryLinkExtractionMode.DISABLED,\n"
        "    memory_extraction_inherit_message_metadata=[\"turn_no\", \"planted_fact_id\"],\n"
        "    enable_context_summary=True,\n"
        "    context_summary_update_frequency=0,                # refresh the running summary at every checkpoint\n"
        ")\n"
        "\n"
        "# Clean slate: the previous run's season - thread, messages, memories, summaries.\n"
        "for _t in memory.list_threads(user_id=SEASON_USER, agent_id=\"CITY\"):\n"
        "    memory.delete_thread(_t.thread_id)\n"
        "season = memory.create_thread(user_id=SEASON_USER, agent_id=\"CITY\",\n"
        "                              metadata={\"purpose\": \"03 inspection season\"},\n"
        "                              memory_extraction_config=SEASON_EXTRACTION)\n"
        "\n"
        "\n"
        "def post_batch(batch):\n"
        "    \"\"\"One batch of (turn_no, speaker, text, planted_fact_id) -> the season thread.\"\"\"\n"
        "    # \u270f\ufe0f TODO(1): post the batch with season.add_messages as user messages\n"
        "    #   (\"<speaker>: <text>\"), with per-message metadata carrying turn_no and\n"
        "    #   speaker - and planted_fact_id only on the turns that have one.\n"
        "    # TODO-SOLUTION-START\n"
        "    season.add_messages(\n"
        "        [{\"role\": \"user\", \"content\": f\"{who}: {text}\"} for _n, who, text, _f in batch],\n"
        "        metadata=[{\"turn_no\": n, \"speaker\": who, **({\"planted_fact_id\": fid} if fid else {})}\n"
        "                  for n, who, _text, fid in batch],\n"
        "    )\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "def holds(text):\n"
        "    \"\"\"Which planted needles appear verbatim in a piece of context.\"\"\"\n"
        "    low = text.lower()\n"
        "    return sorted(f for f, needle in NEEDLES.items() if needle in low)\n"
        "\n"
        "\n"
        "CHECKPOINTS = []\n"
        "for i in range(0, len(TURNS), BATCH):\n"
        "    batch = TURNS[i:i + BATCH]\n"
        "    post_batch(batch)\n"
        "    summary = season.get_summary().content\n"
        "    card = season.get_context_card(max_relevant_results=8, include_invalid_results=False).content\n"
        "    planted = sorted(f for _n, _w, _t, f in TURNS[:i + BATCH] if f)\n"
        "    CHECKPOINTS.append({\"turns\": i + len(batch), \"planted\": planted,\n"
        "                        \"summary_chars\": len(summary), \"in_summary\": holds(summary),\n"
        "                        \"card_chars\": len(card), \"in_card\": holds(card)})\n"
        "    r = CHECKPOINTS[-1]\n"
        "    print(f\"  turn {r['turns']:>2}  planted {','.join(r['planted']) or '-':<8}\"\n"
        "          f\"  summary {r['summary_chars']:>5} chars holds {','.join(r['in_summary']) or '-':<8}\"\n"
        "          f\"  card {r['card_chars']:>5} chars holds {','.join(r['in_card']) or '-'}\")\n"
        "\n"
        "SEASON_MEMORIES = memory.list_memories(user_id=SEASON_USER, agent_id=\"CITY\", limit=500)\n"
        "check(len(SEASON_MEMORIES) > 0, f\"the store extracted {len(SEASON_MEMORIES)} memories from the season\")\n"
        "check(len(CHECKPOINTS) == 5, \"five checkpoints recorded\")"
    ),
    md(
        "**Read the table before the probe.** Two columns matter: what the summary holds and what\n"
        "the card holds, checkpoint by checkpoint. If a needle is in the card but not the\n"
        "summary, retrieval rescued it. If it is in neither, the extractor let it go *and* the\n"
        "summary paraphrased it away. The size columns are there because size is the number\n"
        "everyone quotes; notice how little it tells you about the other two."
    ),
    code(
        "print(\"a few of the memories extraction kept, as stored:\")\n"
        "for m in SEASON_MEMORIES[:8]:\n"
        "    meta = m.metadata or {}\n"
        "    tag = meta.get(\"planted_fact_id\")\n"
        "    print(f\"  turn {str(meta.get('turn_no', '?')):>2}{'  [' + tag + ']' if tag else '      '}  {m.content[:92]}\")\n"
        "PLANTED_MEMORIES = sorted({(m.metadata or {}).get(\"planted_fact_id\") for m in SEASON_MEMORIES} - {None})\n"
        "print(f\"\\nplanted facts that became memories: {PLANTED_MEMORIES or 'none'}\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the fidelity probe: summary alone, then the full card
# --------------------------------------------------------------------------
PROBE = [
    md(
        "## 3 \u00b7 The probe: is it still in there?\n"
        "\n"
        "Turn 4 planted a reason. Thirty-six turns later, we ask the question whose answer\n"
        "*requires* that reason - with nothing to answer from but the context under test, twice:\n"
        "the summary alone, then the full context card.\n"
        "\n"
        "Scoring is functional: does the model's answer contain the planted detail? A structured\n"
        "card could also be scored by set membership on fact ids; the store's card is prose, so\n"
        "the only honest test is to ask. That is a real cost of using it, and worth knowing."
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
        "SUMMARY_TEXT = season.get_summary().content\n"
        "CARD_TEXT = season.get_context_card(max_relevant_results=8, include_invalid_results=False).content\n"
        "print(f\"summary: {len(SUMMARY_TEXT)} chars   card: {len(CARD_TEXT)} chars\\n\")\n"
        "print(CARD_TEXT[:2000] + (\"\\n...\" if len(CARD_TEXT) > 2000 else \"\"))"
    ),
    code(
        "def ask_with(context_text, question):\n"
        "    \"\"\"Answer from the given context only.\"\"\"\n"
        "    # \u270f\ufe0f TODO(2): ask CHAT to answer `question` using ONLY `context_text`; if the\n"
        "    #   context does not contain the answer it must say exactly NOT IN CONTEXT.\n"
        "    #   Return the reply text.\n"
        "    # TODO-SOLUTION-START\n"
        "    return CHAT.invoke(\n"
        "        \"Answer using ONLY the context below. If the context does not contain the\"\n"
        "        \" answer, say exactly: NOT IN CONTEXT.\\n\\n\"\n"
        "        f\"CONTEXT:\\n{context_text}\\n\\nQUESTION: {question}\").text\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "def probe(context_text, label):\n"
        "    found = {}\n"
        "    for fid, (question, needle) in PROBES.items():\n"
        "        reply = ask_with(context_text, question)\n"
        "        found[fid] = needle in reply.lower()\n"
        "        print(f\"  {label:<8} {fid}  {'\u2713' if found[fid] else '\u2717'}  {reply.strip()[:88]}\")\n"
        "    return found\n"
        "\n"
        "\n"
        "SUMMARY_HITS = probe(SUMMARY_TEXT, \"summary\")\n"
        "print()\n"
        "CARD_HITS = probe(CARD_TEXT, \"card\")\n"
        "print(f\"\\nfunctional recall at turn 40 - summary {sum(SUMMARY_HITS.values())}/3, \"\n"
        "      f\"context card {sum(CARD_HITS.values())}/3\")\n"
        "ok(\"probe complete - whatever the card missed, \u00a74 goes looking for\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the fallback: memory search, then the verbatim transcript
# --------------------------------------------------------------------------
FALLBACK = [
    md(
        "## 4 \u00b7 When memory does not have it: fall back to the transcript\n"
        "\n"
        "The card is *standing* context. It is built by querying the store with the thread's\n"
        "own summary - never with the question being asked - so a fact the summary has drifted\n"
        "away from stops being retrieved even while its memory sits intact in the table. And\n"
        "any fact the extractor never kept has no memory to retrieve at all.\n"
        "\n"
        "So a failed probe gets two more tries, each one tier less lossy than the last:\n"
        "\n"
        "1. **Targeted memory search** - the question itself as the query, memories only,\n"
        "   invalid excluded. This is what notebook 02's `recall` does, and what an agent's\n"
        "   search-memory tool should do.\n"
        "2. **The transcript** - messages are stored verbatim and searchable. A message search\n"
        "   with the question finds the turn; its metadata names the turn number; and\n"
        "   `get_messages` fetches the neighbours, because a single turn is often meaningless\n"
        "   alone.\n"
        "\n"
        "The trigger is code - a reply of NOT IN CONTEXT - not the model's sense that it is\n"
        "lost. Wrapped as a tool, tier 2 is the second retrieval tool an agent should carry,\n"
        "described as *the verbatim transcript, for when memory does not have it.*"
    ),
    code(
        "def _text(content):\n"
        "    return content if isinstance(content, str) else \" \".join(\n"
        "        p.get(\"text\", \"\") for p in content if isinstance(p, dict))\n"
        "\n"
        "\n"
        "def transcript_excerpt(question, radius=2):\n"
        "    \"\"\"The turn a message search lands on, with `radius` turns either side.\"\"\"\n"
        "    # \u270f\ufe0f TODO(3): season.search(question, record_types=[\"message\"], max_results=1);\n"
        "    #   read turn_no from the hit's metadata. The thread's messages are 0-indexed in\n"
        "    #   posting order, so fetch season.get_messages(start=turn-1-radius, end=turn+radius)\n"
        "    #   and return (turn, \"[turn] content\" lines joined by newlines) - (None, \"\") if no hit.\n"
        "    # TODO-SOLUTION-START\n"
        "    hits = season.search(question, record_types=[\"message\"], max_results=1)\n"
        "    if not hits:\n"
        "        return None, \"\"\n"
        "    turn = int((hits[0].metadata or {}).get(\"turn_no\", 0))\n"
        "    window = season.get_messages(start=max(turn - 1 - radius, 0), end=turn + radius)\n"
        "    return turn, \"\\n\".join(f\"[{(m.metadata or {}).get('turn_no', '?')}] {_text(m.content)}\"\n"
        "                           for m in window)\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "def recover(fid):\n"
        "    \"\"\"Tier 1: memory search with the question. Tier 2: the transcript.\"\"\"\n"
        "    question, needle = PROBES[fid]\n"
        "    hits = season.search(question, record_types=[\"memory\"], include_invalid_results=False,\n"
        "                         max_results=5)\n"
        "    if hits:\n"
        "        reply = ask_with(\"\\n\".join(f\"- {h.content}\" for h in hits), question)\n"
        "        if \"NOT IN CONTEXT\" not in reply and needle in reply.lower():\n"
        "            return \"memory search\", reply\n"
        "    turn, excerpt = transcript_excerpt(question)\n"
        "    if turn is None:\n"
        "        return \"not recovered\", \"(no message matched)\"\n"
        "    reply = ask_with(excerpt, question)\n"
        "    if \"NOT IN CONTEXT\" not in reply and needle in reply.lower():\n"
        "        return f\"transcript @{turn}\", reply\n"
        "    return \"not recovered\", reply\n"
        "\n"
        "\n"
        "print(\"which tier answers each probe:\")\n"
        "TIER = {}\n"
        "for fid, hit in CARD_HITS.items():\n"
        "    tier, reply = (\"context card\", \"(answered in \u00a73)\") if hit else recover(fid)\n"
        "    TIER[fid] = tier\n"
        "    print(f\"  {fid}  {tier:<16} {reply.strip()[:84]}\")\n"
        "check(all(t != \"not recovered\" for t in TIER.values()),\n"
        "      \"every planted fact is reachable: by the card, by memory search, or from the transcript\")"
    ),
    code(
        "# Exercise the transcript tier on purpose, so you see it work even if the card held up.\n"
        "_turn, _excerpt = transcript_excerpt(PROBES[\"f1\"][0])\n"
        "print(f\"message search for the pier-3 question lands on turn {_turn}; the excerpt:\")\n"
        "print(_excerpt)\n"
        "check(_turn is not None and abs(_turn - 4) <= 2,\n"
        "      \"the transcript search lands on (or beside) the planted turn 4\")\n"
        "ok(\"three tiers, least lossy last: context card -> memory search -> verbatim transcript\")"
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
        "# Ties are ACCEPTED, not broken. An earlier version asked for the tied id that\n"
        "# 'sorts last' and compared against max((days_ago, finding_id)); four findings\n"
        "# tie here at 192 days, the model lexically mis-sorted four opaque hex ids, and\n"
        "# the cell failed - on a string-ordering sub-task, not on the thing being tested.\n"
        "# That is the same trap as the tally above. Any tied id proves the point equally:\n"
        "# all four exist only in the payload.\n"
        "_max_age = max(r[\"days_ago\"] for r in EXPORT_ROWS)\n"
        "OLDEST_IDS = [r[\"finding_id\"] for r in EXPORT_ROWS if r[\"days_ago\"] == _max_age]\n"
        "OLDEST = next(r for r in EXPORT_ROWS if r[\"days_ago\"] == _max_age)\n"
        "EXPORT_JSON = json.dumps(EXPORT_ROWS, default=str)\n"
        "\n"
        "check(context.offload_decision(len(EXPORT_JSON)) == \"offload\",\n"
        "      f\"{TARGET_ASSET} export is {len(EXPORT_JSON)} chars - too big to inline\")\n"
        "print(f\"ground truth: {len(OLDEST_IDS)} finding(s) tie at {_max_age} days ago - \"\n"
        "      f\"{', '.join(OLDEST_IDS)}\")"
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
        "QUESTION = (f\"Export all inspection findings for {TARGET_ASSET}. Name one finding_id\"\n"
        "            f\" with the largest days_ago, and give its severity and category.\")\n"
        "\n"
        "model = CHAT.bind_tools(list(OFFLOAD_TOOLS.values()))\n"
        "msgs = [SystemMessage(content=OFFLOAD_SYSTEM), HumanMessage(content=QUESTION)]\n"
        "tool_outputs = []\n"
        "resp = None\n"
        "\n"
        "for _ in range(6):\n"
        "    resp = model.invoke(msgs)\n"
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
        "answer = resp.text if resp is not None else \"\"\n"
        "print(\"\\nANSWER:\", answer.strip()[:400])"
    ),
    md(
        "**Check the loop, not the bytes.** Three assertions: the tool handed back a\n"
        "reference, the model fetched an id it was actually shown, and its final answer names\n"
        "one of the opaque finding_ids from the payload. Only the last proves the agent\n"
        "*used* what it fetched - the check the original section never made.\n\n"
        "Note what the assertion deliberately does **not** demand: that the model pick a\n"
        "particular one of the four findings tied at the maximum age. Grading that would\n"
        "test lexical sorting over opaque ids - a different skill, which a live run failed\n"
        "while fetching and reading the payload perfectly. Keep the assertion on the\n"
        "mechanism you are measuring, or you will fail runs for the wrong reason."
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
        "#     The ids are opaque: one appears here only if the model read the payload.\n"
        "_named = [fid for fid in OLDEST_IDS if fid in answer]\n"
        "check(bool(_named),\n"
        "      f\"the answer names {_named or OLDEST_IDS} - a value only present in the payload\")"
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
        "print(f\"{len(candidates)} candidate notes in the scratchpad\")"
    ),
    md(
        "**Run notebook 02's gate over the mix.** Every blob path plus one genuinely curated\n"
        "`/inbox` note go through the promotion rule. Refused notes are marked discarded\n"
        "(`D`); admitted ones stay candidates (`N`) - this notebook has no memory client, and\n"
        "in notebook 02 only `promote_note` turns a candidate into a promoted (`P`) note. The\n"
        "two checks assert both directions: every blob is refused, and the real note is still\n"
        "admitted - a specific rule, not a blanket veto."
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
        "        if not allowed:\n"
        "            cur.execute(\"UPDATE HARNESS_SCRATCH SET status = 'D' WHERE path = :1\", (path,))\n"
        "conn.commit()\n"
        "\n"
        "for path, allowed in sorted(verdicts.items()):\n"
        "    print(f\"  {'admit  ' if allowed else 'discard'}  {path}\")\n"
        "\n"
        "blobs = [p for p in verdicts if context.is_offloaded_blob(p)]\n"
        "check(bool(blobs) and not any(verdicts[p] for p in blobs),\n"
        "      f\"all {len(blobs)} offloaded blob(s) refused promotion\")\n"
        "check(any(allowed for path, allowed in verdicts.items() if not context.is_offloaded_blob(path)),\n"
        "      \"a genuinely curated /inbox note is still admitted - a rule, not a blanket veto\")"
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
    md(
        "## 7 \u00b7 State check"
    ),
    code(
        "for desc, passed in verify(conn, \"03_context_engineering\"):\n"
        "    check(passed, desc)\n"
        "ok(\"context engineering complete - continue to 04_evals\")"
    ),
    md(
        "### What notebook 04 does with this\n"
        "\n"
        "Two of the five evals extend this notebook:\n"
        "\n"
        "- **Card fidelity over a long horizon** generalises \u00a73. One season and three planted\n"
        "  facts is an anecdote; the eval runs multi-topic, adversarially spaced sessions and\n"
        "  reports drift as a distribution, not a single percentage. It keeps a structured,\n"
        "  id-scored card as its baseline - the natural next arm is the store's context card\n"
        "  measured here, scored the same way.\n"
        "- **Cost per correct answer** puts \u00a73 and \u00a74 on the same axis - card vs. transcript vs.\n"
        "  stateless - with repeated trials and variance, which is what the original 8.4 lacked\n"
        "  at n=1.\n"
        "\n"
        "The habit to carry forward is the one this notebook is built around: every time you\n"
        "make the context smaller, you have made a claim about what is still in there. Write\n"
        "the probe that tests the claim, and let it fail sometimes."
    ),
]

SECTIONS = [INTRO, SETUP, SEASON, CHECKPOINTS, PROBE, FALLBACK, OFFLOAD, EXCLUSION, CLOSING]


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
