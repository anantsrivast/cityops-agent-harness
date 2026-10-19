"""Regenerate notebooks/02_scheduled_briefings_complete.ipynb.

Run: .venv/bin/python tools/make_02_notebook.py
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
        "# 02 - Curated long-term memory: promotion, provenance, supersession\n\n"
        "Notebook 01 fixed how the harness learns *procedures*. This notebook fixes the\n"
        "other promotion path - scratch notes graduating into long-term memory - which the\n"
        "review summarised as *\"promotion without curation, growth without forgetting\"*:\n\n"
        "| Review gap (Path 1) | This notebook |\n"
        "|---|---|\n"
        "| Everything graduates within the hour | **Opt-in** `/inbox` + the store's own **extraction** as the gate, under *your* curation instructions |\n"
        "| 200-word chunks re-extracted by the LLM | **Whole-note memories**, verbatim - instructed, then *checked* |\n"
        "| No provenance, nothing supersedes | Provenance as **memory metadata**; supersession as the store's own **relations** |\n"
        "| (bonus) persistence-of-one-fact only | **Continuity of work**: a new session resumes the briefing *plan*, not just facts |\n\n"
        "The payoff: a **morning asset-risk briefing** built from *current* memory - every\n"
        "claim traceable to the note it came from, and nothing the repairs have retired."
    ),
]

# --------------------------------------------------------------------------
# Section: setup
# --------------------------------------------------------------------------
SETUP = [
    md("## 0 · Setup\n\nConnect, verify notebook 01's artifacts, check privileges, stand up the embedder."),
    code(
        "import array\n"
        "import json\n"
        "import uuid\n"
        "\n"
        "from cityops_harness.checks import ok, check\n"
        "from cityops_harness.config import load_settings\n"
        "from cityops_harness.db import get_connection\n"
        "from cityops_harness.llm import chat_model, litellm_spec\n"
        "from cityops_harness.state import require, verify\n"
        "from cityops_harness.tracing import init_tracing\n"
        "from cityops_harness import promote\n"
        "\n"
        "settings = load_settings()\n"
        "conn = get_connection(settings)\n"
        "require(conn, \"01_self_improving_copilot\")\n"
        "CHAT = chat_model(settings)\n"
        "HANDLER = init_tracing(settings)\n"
        "ok(f\"connected - provider={settings.llm_provider}, langfuse={settings.langfuse_mode}\")"
    ),
    code(
        "# One privilege most ADB users lack by default: CREATE TRIGGER, for the memory\n"
        "# store itself. Agent Memory 26.8 raised its managed schema to v13, which adds a\n"
        "# <PREFIX>MEMORY_LINK table plus a delete trigger that revalidates memories when\n"
        "# an invalidating link is removed (Section 5c).\n"
        "#\n"
        "# This gate runs BEFORE the store is opened, and on purpose. The v12 -> v13\n"
        "# upgrade is not atomic: it retypes MESSAGE.CONTENT from CLOB to JSON and only\n"
        "# then creates the trigger. Without the grant it fails there, leaving the store\n"
        "# stamped v12 but carrying a v13 column - unreadable by old and new SDK alike.\n"
        "# Better to stop here with a grant to run than to half-migrate a live store.\n"
        "REQUIRED_PRIVS = {\"CREATE TRIGGER\"}\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"SELECT privilege FROM user_sys_privs\")\n"
        "    _privs = {r[0] for r in cur.fetchall()}\n"
        "_missing = REQUIRED_PRIVS - _privs\n"
        "check(not _missing,\n"
        "      \"missing privilege(s) - run as ADMIN, then re-run this cell: \"\n"
        "      + \"; \".join(f'GRANT {p} TO {settings.db_user}' for p in sorted(_missing))\n"
        "      if _missing else f\"privileges present ({\", \".join(sorted(REQUIRED_PRIVS))})\")\n"
        "\n"
        "# Earlier versions of this notebook scheduled a promotion queue and an in-database\n"
        "# briefing job. Retire them if present, so nothing runs behind the notebook's back.\n"
        "with conn.cursor() as cur:\n"
        "    for _ddl in (\"BEGIN DBMS_SCHEDULER.DROP_JOB('HARNESS_STAGE_JOB'); END;\",\n"
        "                 \"BEGIN DBMS_SCHEDULER.DROP_JOB('HARNESS_BRIEFING_JOB'); END;\",\n"
        "                 \"DROP PROCEDURE HARNESS_STAGE_INBOX\",\n"
        "                 \"DROP PROCEDURE HARNESS_BUILD_BRIEFING\",\n"
        "                 \"DROP TABLE HARNESS_PROMOTION_QUEUE PURGE\",\n"
        "                 \"DROP TABLE HARNESS_BRIEFING PURGE\"):\n"
        "        try:\n"
        "            cur.execute(_ddl)\n"
        "        except Exception:\n"
        "            pass  # not there - nothing to retire"
    ),
    code(
        "import asyncio\n"
        "import numpy as np\n"
        "from langchain_oracledb.embeddings.oracleai import OracleEmbeddings\n"
        "from oracleagentmemory.apis.embedders.embedder import IEmbedder\n"
        "\n"
        "\n"
        "class OracleONNXEmbedder(IEmbedder):\n"
        "    def __init__(self, conn, model_name):\n"
        "        self.provider = OracleEmbeddings(\n"
        "            conn=conn, params={\"provider\": \"database\", \"model\": model_name}\n"
        "        )\n"
        "\n"
        "    def embed(self, texts, *, is_query=False):\n"
        "        return np.asarray(self.provider.embed_documents(list(texts)), dtype=np.float32)\n"
        "\n"
        "    async def embed_async(self, texts, *, is_query=False):\n"
        "        return await asyncio.to_thread(self.embed, texts, is_query=is_query)\n"
        "\n"
        "\n"
        "embedder = OracleONNXEmbedder(conn, settings.embed_model)\n"
        "check(embedder.embed([\"hello\"]).shape == (1, 384), \"in-database embedder ready\")"
    ),
]

# --------------------------------------------------------------------------
# Section: SDK init (first live use) - whole notes, no re-extraction
# --------------------------------------------------------------------------
SDK_INIT = [
    md(
        "## 1 · The Agent Memory SDK - configured for *whole-note* promotion\n\n"
        "`schema_policy=CREATE_IF_NECESSARY` creates the managed schema (v13 as of Agent\n"
        "Memory 26.8) or applies a supported upgrade to an existing one. `table_name_prefix`\n"
        "keeps every managed table under `CITY_`, which is why the promotion checks later in\n"
        "this notebook can read `CITY_MEMORY` directly.\n\n"
        "This client is used for direct reads and writes. Memory *extraction* - the store's\n"
        "LLM deciding what a message is worth remembering - is switched on in exactly one\n"
        "place: each asset's inbox thread (Section 4), under our instructions. The original\n"
        "pipeline chunked files into 200-word windows and let the LLM *re-interpret* each one\n"
        "- confident misreadings of mid-sentence fragments became durable facts. Here the\n"
        "store's LLM judges *whether* a whole note is kept, and a kept note is stored\n"
        "**verbatim** as one memory."
    ),
    code(
        "from oracleagentmemory.core import OracleAgentMemory, SchemaPolicy\n"
        "from oracleagentmemory.core.llms.llm import Llm as SdkLlm\n"
        "\n"
        "memory = OracleAgentMemory(\n"
        "    connection=conn,\n"
        "    embedder=embedder,\n"
        "    llm=SdkLlm(**litellm_spec(settings)),\n"
        "    schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,\n"
        "    table_name_prefix=\"CITY_\",\n"
        ")\n"
        "\n"
        "# Round-trip smoke test: store, find, delete.\n"
        "_mid = memory.add_memory(\"smoke test memory - safe to delete\",\n"
        "                         memory_type=\"fact\", user_id=\"_smoke\", agent_id=\"CITY\")\n"
        "_hits = memory.search(\"smoke test\", user_id=\"_smoke\", agent_id=\"CITY\", max_results=1)\n"
        "check(len(_hits) == 1 and _hits[0].id == _mid, \"SDK add_memory/search round-trip\")\n"
        "memory.delete_memory(_mid)\n"
        "ok(\"OracleAgentMemory ready (CITY_ tables, whole-note mode)\")"
    ),
]

# --------------------------------------------------------------------------
# Section: scratch store + seed notes
# --------------------------------------------------------------------------
SCRATCH = [
    md(
        "## 2 · The scratchpad: cheap to write, safe to be wrong in\n\n"
        "A plain table posing as a tiny filesystem. Inspectors jot notes all day; only\n"
        "`/inbox/<asset>/...` is a promotion *candidate area*. Working files - drafts,\n"
        "abandoned queries, tool dumps - live outside it and are **never** promoted, which\n"
        "restores the scratchpad's contract the review showed the old pipeline destroyed."
    ),
    code(
        "def _table_exists(name):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"SELECT COUNT(*) FROM user_tables WHERE table_name = :t\", t=name)\n"
        "        return cur.fetchone()[0] > 0\n"
        "\n"
        "\n"
        "if not _table_exists(\"HARNESS_SCRATCH\"):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"\"\"CREATE TABLE HARNESS_SCRATCH (\n"
        "            path       VARCHAR2(512) PRIMARY KEY,\n"
        "            content    CLOB NOT NULL,\n"
        "            revision   VARCHAR2(64) NOT NULL,\n"
        "            status     VARCHAR2(1) DEFAULT 'N'\n"
        "                       CHECK (status IN ('N','P','D')),\n"
        "            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)\"\"\")\n"
        "    conn.commit()\n"
        "\n"
        "\n"
        "def write_note(path, content):\n"
        "    rev = promote.note_revision(content)\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"DELETE FROM HARNESS_SCRATCH WHERE path = :p\", p=path)\n"
        "        cur.execute(\"\"\"INSERT INTO HARNESS_SCRATCH (path, content, revision, status)\n"
        "                       VALUES (:p, :c, :r, 'N')\"\"\", p=path, c=content, r=rev)\n"
        "    conn.commit()\n"
        "    return rev\n"
        "\n"
        "\n"
        "def read_note(path):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"SELECT content, revision, status FROM HARNESS_SCRATCH WHERE path = :p\",\n"
        "                    p=path)\n"
        "        row = cur.fetchone()\n"
        "    if row is None:\n"
        "        return None\n"
        "    content = row[0].read() if hasattr(row[0], \"read\") else row[0]\n"
        "    return {\"path\": path, \"content\": content, \"revision\": row[1], \"status\": row[2]}\n"
        "\n"
        "\n"
        "def list_notes(prefix=\"/\"):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"\"\"SELECT path, status FROM HARNESS_SCRATCH\n"
        "                       WHERE path LIKE :p ORDER BY path\"\"\", p=prefix + \"%\")\n"
        "        return cur.fetchall()\n"
        "\n"
        "\n"
        "def set_note_status(path, status):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"UPDATE HARNESS_SCRATCH SET status = :s WHERE path = :p\",\n"
        "                    s=status, p=path)\n"
        "    conn.commit()\n"
        "\n"
        "ok(\"scratch store ready\")"
    ),
    code(
        "from pathlib import Path\n"
        "\n"
        "_data_dir = Path(\"data\") if Path(\"data\").exists() else Path(\"../data\")\n"
        "with open(_data_dir / \"maintenance_logs.json\") as f:\n"
        "    _logs = json.load(f)\n"
        "_asset_names = sorted({x[\"asset_name\"] for x in _logs})\n"
        "ASSET_A = \"Harbor Bridge\" if \"Harbor Bridge\" in _asset_names else _asset_names[0]\n"
        "\n"
        "# Seed the inbox with real field narratives (non-routine first - richer signal),\n"
        "# and the review's own cautionary trio OUTSIDE the inbox.\n"
        "_candidates = [l for l in _logs if l[\"asset_name\"] == ASSET_A and l[\"severity\"] != \"routine\"]\n"
        "_candidates += [l for l in _logs if l[\"asset_name\"] == ASSET_A and l[\"severity\"] == \"routine\"]\n"
        "INBOX_SEED = []\n"
        "for i, log in enumerate(_candidates[:4]):\n"
        "    path = f\"/inbox/{ASSET_A}/{i}.md\"\n"
        "    INBOX_SEED.append((path, log[\"narrative\"], log[\"days_ago\"]))\n"
        "    write_note(path, log[\"narrative\"])\n"
        "\n"
        "SUPERSEDE_DEFECT_PATH = f\"/inbox/{ASSET_A}/defect-bearing.md\"\n"
        "SUPERSEDE_REPAIR_PATH = f\"/inbox/{ASSET_A}/repair-bearing.md\"\n"
        "write_note(SUPERSEDE_DEFECT_PATH,\n"
        "           f\"Bearing plates at pier 2 of {ASSET_A} show active corrosion with \"\n"
        "           \"measurable section loss. Load rating review recommended; monitor monthly.\")\n"
        "\n"
        "write_note(\"/work/draft_notes.md\",\n"
        "           \"TODO: check if the load rating includes the retrofit?? probably not\")\n"
        "write_note(\"/work/attempt1_wrong.sql\",\n"
        "           \"SELECT asset, COUNT(*) FROM findings GROUP BY severity  -- wrong, abandoned\")\n"
        "write_note(\"/tool_out/similar_dump.json\", json.dumps({\"rows\": list(range(50))}))\n"
        "\n"
        "for p, s in list_notes(\"/\"):\n"
        "    print(f\"{s}  {p}\")\n"
        "ok(f\"{len(INBOX_SEED) + 1} inbox candidates, 3 working files (outside the inbox)\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the copilot as a memory producer (moved from notebook 01 §8b)
# --------------------------------------------------------------------------
PRODUCER = [
    md(
        "## 2b · Where inbox notes really come from: the copilot as a *producer*\n\n"
        "The seed above is hand-written. In production the notes come from the copilot\n"
        "itself, deciding what is worth remembering while it works.\n\n"
        "The design choice worth noticing: the agent is **never told about directories**. It\n"
        "gets one `remember(asset_id, note, durable)` tool and judges only *is this worth\n"
        "keeping?*. The **tool** owns the convention - `durable=True` files to `/inbox` (the\n"
        "opt-in area this notebook promotes from), `durable=False` to `/work` (scratch, never\n"
        "promoted). Placement is policy; the agent only supplies judgement."
    ),
    md(
        "**The `remember` tool, plus one read tool.** `remember` writes through the same\n"
        "`write_note` as the seed, so an agent-filed note enters exactly the pipeline the\n"
        "seeded ones do. The path is derived, never chosen by the model - and so is the asset\n"
        "id: `harbor_bridge` resolves to `Harbor Bridge`, an unknown asset is refused.\n"
        "`tool_find_similar_findings` is a read-only copy of notebook 01's search, so the\n"
        "copilot has real history to judge against."
    ),
    code(
        "import re\n"
        "from langchain_core.tools import tool\n"
        "\n"
        "\n"
        "def _slug(text):\n"
        "    return re.sub(r\"[^a-z0-9]+\", \"-\", text.lower()).strip(\"-\")[:40] or \"note\"\n"
        "\n"
        "\n"
        "with conn.cursor() as cur:\n"
        "    cur.execute(\"SELECT DISTINCT asset_id FROM CITY_INSPECTION_FINDING\")\n"
        "    KNOWN_ASSETS = {_slug(r[0]): r[0] for r in cur.fetchall()}\n"
        "\n"
        "\n"
        "def canonical_asset(asset_id):\n"
        "    \"\"\"The model may say 'harbor_bridge'; memory is keyed by 'Harbor Bridge'. A note\n"
        "    filed under a variant would land in a different memory user, where supersession\n"
        "    and recall never see it - so the tool resolves the id, or refuses.\"\"\"\n"
        "    if asset_id is None:\n"
        "        return None\n"
        "    if _slug(asset_id) not in KNOWN_ASSETS:\n"
        "        raise ValueError(f\"unknown asset {asset_id!r}; known: {sorted(KNOWN_ASSETS.values())}\")\n"
        "    return KNOWN_ASSETS[_slug(asset_id)]\n"
        "\n"
        "\n"
        "@tool\n"
        "def remember(asset_id: str, note: str, durable: bool) -> str:\n"
        "    \"\"\"File a note for long-term memory curation.\n"
        "    durable=True  -> a completed, keep-worthy finding (enters the promotion inbox).\n"
        "    durable=False -> scratch reasoning or a dead end (kept OUT of long-term memory).\n"
        "    Returns the path it was filed under. You never choose the path.\"\"\"\n"
        "    if durable:\n"
        "        path = f\"/inbox/{canonical_asset(asset_id)}/{_slug(note)}.md\"\n"
        "    else:\n"
        "        path = f\"/work/{_slug(note)}.md\"\n"
        "    write_note(path, note)\n"
        "    return path\n"
        "\n"
        "\n"
        "@tool\n"
        "def tool_find_similar_findings(description: str, asset_id: str = None, k: int = 3) -> str:\n"
        "    \"\"\"Search past inspection findings semantically similar to a description.\n"
        "    Returns finding_id, category, severity, days_ago and description per hit.\"\"\"\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(f\"\"\"SELECT finding_id, category, severity, days_ago, description\n"
        "                         FROM CITY_INSPECTION_FINDING\n"
        "                        WHERE (:a IS NULL OR asset_id = :a)\n"
        "                        ORDER BY VECTOR_DISTANCE(embedding,\n"
        "                                 VECTOR_EMBEDDING({settings.embed_model} USING :q AS data),\n"
        "                                 COSINE)\n"
        "                        FETCH FIRST :k ROWS ONLY\"\"\",\n"
        "                    a=canonical_asset(asset_id), q=description, k=k)\n"
        "        cols = [d[0].lower() for d in cur.description]\n"
        "        hits = []\n"
        "        for r in cur.fetchall():\n"
        "            row = dict(zip(cols, r))\n"
        "            if hasattr(row[\"description\"], \"read\"):\n"
        "                row[\"description\"] = row[\"description\"].read()\n"
        "            hits.append(row)\n"
        "    return json.dumps(hits, default=str)\n"
        "\n"
        "ok(\"remember() ready - the tool owns placement and the asset id; the agent only judges\")"
    ),
    md(
        "**Run the producer.** The copilot gets the search tool *plus* `remember`, and a prompt\n"
        "that asks it to keep durable findings and discard scratch - in those words, not in\n"
        "directory names. Watch the `remember(... durable=True/False ...)` calls: the model\n"
        "decides worth, the tool decides where.\n\n"
        "The task is about the expansion-joint anchor bolts on purpose: the pier-2 bearing\n"
        "notes seeded above are the supersession demo in Section 5, and an agent note on the\n"
        "same defect would compete with them."
    ),
    code(
        "from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage\n"
        "\n"
        "PRODUCER_PROMPT = (\n"
        "    \"You are the CityOps inspection copilot, now also responsible for what gets\\n\"\n"
        "    \"remembered. Do the task through your tools. Before you finish, call remember():\\n\"\n"
        "    \"  - durable=True for each completed, keep-worthy finding (one short paragraph);\\n\"\n"
        "    \"  - durable=False for scratch reasoning or a dead end you do NOT want kept.\\n\"\n"
        "    \"You never choose folders or paths - remember() files each note where it belongs.\"\n"
        ")\n"
        "\n"
        "PRODUCER_TOOLS = {t.name: t for t in (tool_find_similar_findings, remember)}\n"
        "_pmodel = CHAT.bind_tools(list(PRODUCER_TOOLS.values()))\n"
        "_cfg = {\"callbacks\": [HANDLER]} if HANDLER else {}\n"
        "task = (f\"Inspect the expansion-joint anchor bolts on {ASSET_A} for pitting: check\"\n"
        "        f\" similar past findings first, remember what matters, and explicitly discard\"\n"
        "        f\" your scratch reasoning.\")\n"
        "msgs = [SystemMessage(content=PRODUCER_PROMPT), HumanMessage(content=task)]\n"
        "\n"
        "FILED = []   # (durable, path) for every remember() call THIS run made\n"
        "for _ in range(6):\n"
        "    resp = _pmodel.invoke(msgs, config=_cfg)\n"
        "    msgs.append(resp)\n"
        "    if not getattr(resp, \"tool_calls\", None):\n"
        "        break\n"
        "    for tc in resp.tool_calls:\n"
        "        try:\n"
        "            result = str(PRODUCER_TOOLS[tc[\"name\"]].invoke(tc[\"args\"], _cfg))\n"
        "        except Exception as e:\n"
        "            result = f\"ERROR: {type(e).__name__}: {e}\"\n"
        "        if tc[\"name\"] == \"remember\":\n"
        "            FILED.append((bool(tc[\"args\"].get(\"durable\")), result))\n"
        "            print(f\"  remember(durable={tc['args'].get('durable')}) -> {result}\")\n"
        "        else:\n"
        "            print(f\"  {tc['name']}(...) = {result[:60]}\")\n"
        "        msgs.append(ToolMessage(content=result, tool_call_id=tc[\"id\"]))\n"
        "\n"
        "_ans = resp.content if isinstance(resp.content, str) else \"\".join(\n"
        "    p.get(\"text\", \"\") if isinstance(p, dict) else str(p) for p in resp.content)\n"
        "print(\"\\nagent:\", _ans.strip()[:280])"
    ),
    md(
        "**What the agent filed.** Checked against *this run's* `remember` calls, not the\n"
        "whole table - leftover notes from an earlier run must not be able to pass it."
    ),
    code(
        "for durable, path in FILED:\n"
        "    print(f\"  {'durable' if durable else 'scratch':8} {read_note(path)['status']}  {path}\")\n"
        "\n"
        "_kept = [p for d, p in FILED if d]\n"
        "check(bool(_kept), f\"the copilot filed {len(_kept)} durable note(s) into the inbox\")\n"
        "check(all(promote.triage_allowed(p) == d for d, p in FILED),\n"
        "      \"every durable note landed in /inbox, and every scratch note outside it\")\n"
        "check(all(p.startswith(f\"/inbox/{ASSET_A}/\") for p in _kept),\n"
        "      f\"every durable note is filed under the canonical asset id {ASSET_A!r}\")\n"
        "ok(\"producer wired - Section 4 promotes these notes along with the seed\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the curation gate (the store's extraction, under our instructions)
# --------------------------------------------------------------------------
TRIAGE = [
    md(
        "## 3 · The curation gate: judgement *before* durability\n"
        "\n"
        "Two filters, in order:\n"
        "\n"
        "1. **Opt-in area** - anything outside `/inbox/` never reaches the memory store, and\n"
        "   costs no model call (the review's `/work/attempt1_wrong.sql` can never leak in).\n"
        "2. **The store's own extraction, under your instructions** - an inbox note is posted to\n"
        "   its asset's thread, and Agent Memory's extraction LLM decides whether it becomes a\n"
        "   memory at all. The *policy* is yours: `CURATION_INSTRUCTIONS` says what is worth\n"
        "   keeping, and that a kept note becomes **one** memory, **verbatim**.\n"
        "\n"
        "The SDK's built-in extraction prompt asks for small *atomic* facts - exactly the\n"
        "chunk-and-reinterpret the review warned about. Our instructions are appended to that\n"
        "prompt and override it for this thread, and Section 4 *checks* that every memory equals\n"
        "its note word for word - so if a future SDK stops honouring the override, it fails\n"
        "loudly rather than silently paraphrasing.\n"
        "\n"
        "There is no `hold` any more: an incomplete note is simply not extracted. File it again\n"
        "when the work is done."
    ),
    code(
        "from oracleagentmemory.core import MemoryExtractionConfig\n"
        "from oracleagentmemory.core.extractors.memoryextractionconfig import (\n"
        "    MemoryExtractionMode,\n"
        "    MemoryLinkExtractionMode,\n"
        ")\n"
        "\n"
        "# The policy lives in promote.py so notebook 04 grades this exact text.\n"
        "CURATION_INSTRUCTIONS = promote.CURATION_INSTRUCTIONS\n"
        "LINK_INSTRUCTIONS = promote.LINK_INSTRUCTIONS\n"
        "print(CURATION_INSTRUCTIONS)\n"
        "\n"
        "INBOX_EXTRACTION = MemoryExtractionConfig(\n"
        "    extract_memories=True,\n"
        "    extraction_mode=MemoryExtractionMode.INLINE,   # memories exist when add_messages returns\n"
        "    memory_extraction_window=-1,                   # judge only the note just posted...\n"
        "    memory_extraction_frequency=-1,                # ...after every note\n"
        "    memory_extraction_custom_instructions=CURATION_INSTRUCTIONS,\n"
        "    memory_link_extraction_mode=MemoryLinkExtractionMode.POST_EXTRACTION,\n"
        "    memory_link_extraction_custom_instructions=LINK_INSTRUCTIONS,\n"
        "    # provenance: these message-metadata keys are copied onto every extracted memory\n"
        "    memory_extraction_inherit_message_metadata=[\"source_path\", \"revision\", \"days_ago\"],\n"
        "    enable_context_summary=False,\n"
        ")\n"
        "\n"
        "\n"
        "def passes_gate(path):\n"
        "    # ✏️ TODO(1): the opt-in gate comes FIRST and never costs a model call -\n"
        "    #             only notes promote.triage_allowed(path) admits may reach the store.\n"
        "    # TODO-SOLUTION-START\n"
        "    return promote.triage_allowed(path)\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "for p, _s in list_notes(\"/\"):\n"
        "    print(f\"{'candidate' if passes_gate(p) else 'skipped  '}  {p}\")\n"
        "ok(\"curation gate ready - the path first, then the store's extraction under our instructions\")"
    ),
]

# --------------------------------------------------------------------------
# Section: promotion with provenance on the memory itself
# --------------------------------------------------------------------------
PROMOTION = [
    md(
        "## 4 · Promotion: whole notes, with a paper trail - in the store itself\n"
        "\n"
        "`promote_note` posts a candidate note to its asset's inbox thread with three metadata\n"
        "keys: `source_path`, `revision` (a fingerprint of the exact text) and `days_ago` (how\n"
        "old the observation is). Extraction keeps the note or drops it. A kept note becomes one\n"
        "memory that **inherits** those keys, so provenance lives on the memory itself -\n"
        "`list_memories(metadata_filter={\"source_path\": ...})` finds every memory a note produced.\n"
        "No sidecar table.\n"
        "\n"
        "Then the store's link step compares the new memory with what the asset already has and\n"
        "records any relation - a repair note `supersedes` the defect it fixed (Section 5).\n"
        "\n"
        "One thing stays ours: **re-runs**. The store treats a re-posted note as a new claim, not\n"
        "a duplicate, so promotion first forgets whatever an earlier promotion of the same path\n"
        "left behind."
    ),
    code(
        "def asset_from_path(path):\n"
        "    parts = path.split(\"/\")\n"
        "    return parts[2] if len(parts) > 3 and parts[1] == \"inbox\" else None\n"
        "\n"
        "\n"
        "# How old each seeded observation really is; notes written in this notebook are new.\n"
        "NOTE_DAYS_AGO = {p: d for p, _content, d in INBOX_SEED}\n"
        "\n"
        "_inbox_threads = {}\n"
        "\n"
        "\n"
        "def inbox_thread(asset_id):\n"
        "    \"\"\"One extraction-enabled thread per asset, carrying the Section 3 policy.\"\"\"\n"
        "    if asset_id not in _inbox_threads:\n"
        "        _inbox_threads[asset_id] = memory.create_thread(\n"
        "            user_id=asset_id, agent_id=\"CITY\", memory_extraction_config=INBOX_EXTRACTION)\n"
        "    return _inbox_threads[asset_id]\n"
        "\n"
        "\n"
        "def memories_from(path):\n"
        "    \"\"\"Every memory a note produced, valid or not - provenance is a metadata filter.\"\"\"\n"
        "    return memory.list_memories(user_id=asset_from_path(path), agent_id=\"CITY\",\n"
        "                                metadata_filter={\"source_path\": path}, limit=50)\n"
        "\n"
        "\n"
        "def promote_note(path):\n"
        "    note = read_note(path)\n"
        "    if not passes_gate(path):\n"
        "        set_note_status(path, \"D\")\n"
        "        return None\n"
        "    # Idempotent promotion: forget what an earlier promotion of THIS path left. The\n"
        "    # store would otherwise keep a re-posted note as a fresh, valid memory beside it.\n"
        "    for old in memories_from(path):\n"
        "        memory.delete_memory(old.id)\n"
        "    # ✏️ TODO(2): post the note to its asset's inbox thread as one user message, with\n"
        "    #             metadata source_path, revision (note[\"revision\"]) and days_ago\n"
        "    #             (NOTE_DAYS_AGO, default 0). The store extracts it - or doesn't.\n"
        "    # TODO-SOLUTION-START\n"
        "    inbox_thread(asset_from_path(path)).add_messages(\n"
        "        [{\"role\": \"user\", \"content\": note[\"content\"]}],\n"
        "        metadata={\"source_path\": path, \"revision\": note[\"revision\"],\n"
        "                  \"days_ago\": NOTE_DAYS_AGO.get(path, 0)})\n"
        "    # TODO-SOLUTION-END\n"
        "    kept = memories_from(path)\n"
        "    set_note_status(path, \"P\" if kept else \"D\")\n"
        "    return kept[0].id if kept else None\n"
        "\n"
        "ok(\"promotion defined: gate -> the store's extraction (keep / drop) -> provenance on the memory\")"
    ),
    md(
        "**Promote the inbox.** One `promote_note` call per new note - the seed, the copilot's\n"
        "notes from Section 2b, and the working files outside `/inbox` (which the gate drops\n"
        "without a model call). In production this runs wherever notes are written: right\n"
        "after `remember()`, or from whatever scheduler you already run - orchestration is\n"
        "not a memory concern, so this notebook does not teach it."
    ),
    code(
        "# This run's notes: the seed, the working files, and what the copilot filed in 2b.\n"
        "# Leftovers from earlier runs are not ours to judge here.\n"
        "_this_run = ([p for p, _c, _d in INBOX_SEED] + [SUPERSEDE_DEFECT_PATH]\n"
        "             + [\"/work/draft_notes.md\", \"/work/attempt1_wrong.sql\",\n"
        "                \"/tool_out/similar_dump.json\"]\n"
        "             + [p for _d, p in FILED])\n"
        "# Promote only the NEW ones, so re-running this cell settles nothing twice.\n"
        "for p in _this_run:\n"
        "    if read_note(p)[\"status\"] == \"N\":\n"
        "        promote_note(p)\n"
        "    _m = memories_from(p) if passes_gate(p) else []\n"
        "    print(f\"  {read_note(p)['status']}  {p}\" + (f\"  -> memory {_m[0].id[:12]}...\" if _m else \"\"))\n"
        "\n"
        "_promoted = [p for p in _this_run if read_note(p)[\"status\"] == \"P\"]\n"
        "check(len(_promoted) >= 3, f\"{len(_promoted)} inbox notes promoted, each carrying its provenance\")\n"
        "# The override in Section 3 asked for one verbatim memory per note. Check it, don't trust it.\n"
        "_mems = {p: memories_from(p) for p in _promoted}\n"
        "check(all(len(m) == 1 and m[0].content.strip() == read_note(p)[\"content\"].strip()\n"
        "          for p, m in _mems.items()),\n"
        "      \"every promoted note became exactly one memory, word for word\")\n"
        "check(all(passes_gate(p) for p in _promoted), \"nothing outside /inbox was promoted\")"
    ),
]

# --------------------------------------------------------------------------
# Section: recall with provenance, recency, and supersession
# --------------------------------------------------------------------------
RECALL = [
    md(
        "## 5 · Supersession in action, and recall that prefers the present\n"
        "\n"
        "The repair note arrives and is promoted like any other - and the\n"
        "store's link step recognises that it completes the defect: it writes a `supersedes`\n"
        "relation and flips the defect memory to `invalid`. Nothing of ours decided that.\n"
        "\n"
        "Recall then asks the store for **current** memories only - `include_invalid_results=False`\n"
        "and `record_types=[\"memory\"]` (the thread's raw messages are searchable too, and messages\n"
        "are never invalidated) - reads provenance off each memory, and weights recency by the\n"
        "observation's real age."
    ),
    code(
        "write_note(SUPERSEDE_REPAIR_PATH,\n"
        "           f\"Bearing plates at pier 2 of {ASSET_A} replaced and recoated on today's\"\n"
        "           \" shift; corrosion remediated, section loss addressed. Load rating\"\n"
        "           \" restored to design values. Next scheduled check in 12 months.\")\n"
        "promote_note(SUPERSEDE_REPAIR_PATH)\n"
        "\n"
        "\n"
        "def status_value(m):\n"
        "    return getattr(m.status, \"value\", m.status)\n"
        "\n"
        "\n"
        "_defect_now = [status_value(m) for m in memories_from(SUPERSEDE_DEFECT_PATH)]\n"
        "check(bool(_defect_now) and all(s == \"invalid\" for s in _defect_now),\n"
        "      f\"the store invalidated the defect memory on its own (status={_defect_now})\")"
    ),
    code(
        "def recall(query, asset_id, k=5):\n"
        "    \"\"\"Current memories only -> provenance from metadata -> recency re-rank.\"\"\"\n"
        "    # ✏️ TODO(3): ask the store for CURRENT memory records only: record_types=[\"memory\"]\n"
        "    #             (raw thread messages are searchable too, and are never invalidated)\n"
        "    #             and include_invalid_results=False.\n"
        "    # TODO-SOLUTION-START\n"
        "    hits = memory.search(query, user_id=asset_id, agent_id=\"CITY\", max_results=k * 2,\n"
        "                         record_types=[\"memory\"], include_invalid_results=False)\n"
        "    # TODO-SOLUTION-END\n"
        "    rows = []\n"
        "    for idx, h in enumerate(hits):\n"
        "        meta = getattr(h.record, \"metadata\", None) or {}\n"
        "        if \"source_path\" not in meta:\n"
        "            continue  # unprovenanced - not a promoted note\n"
        "        rows.append({\"memory_id\": h.id, \"content\": h.content,\n"
        "                     \"source_path\": meta[\"source_path\"], \"revision\": meta[\"revision\"][:12],\n"
        "                     \"days_ago\": meta.get(\"days_ago\") or 0, \"base\": 1.0 / (1 + idx)})\n"
        "    return promote.rerank_by_recency(rows)[:k]\n"
        "\n"
        "\n"
        "results = recall(\"bearing plate corrosion at pier 2\", ASSET_A)\n"
        "for r in results:\n"
        "    print(f\"score={r['score']:.3f} days_ago={r['days_ago']:>4} {r['source_path']}\\n\"\n"
        "          f\"    {r['content'][:100]}...\")\n"
        "_texts = \" \".join(r[\"content\"] for r in results)\n"
        "check(\"replaced\" in _texts or \"remediated\" in _texts, \"repair note is recalled\")\n"
        "_invalid = {m.id for m in memories_from(SUPERSEDE_DEFECT_PATH) if status_value(m) == \"invalid\"}\n"
        "check(all(r[\"memory_id\"] not in _invalid for r in results),\n"
        "      \"no superseded memory competes for retrieval attention\")"
    ),
]

# --------------------------------------------------------------------------
# Section: follow one note end to end
# --------------------------------------------------------------------------
TRACE = [
    md(
        "## 5b · Follow one note, end to end\n\n"
        "Every mechanism above touched a *different* note. Here we take a **single** note and\n"
        "watch it move through every stage, printing where it lives after each step - its\n"
        "scratch status, and the memory it became, with its provenance and lifecycle status.\n"
        "This is the whole notebook in one narrative: **written → promoted → remembered →\n"
        "superseded → dropped from recall.**"
    ),
    md(
        "**The lens.** `follow(path)` reads the note's scratch row and, through the provenance\n"
        "filter, the memory it became - id, revision, and lifecycle status. A superseded memory\n"
        "stays in the store as `invalid`, with the reason the store recorded."
    ),
    code(
        "def follow(path, stage):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"SELECT status FROM HARNESS_SCRATCH WHERE path = :p\", p=path)\n"
        "        _r = cur.fetchone()\n"
        "    scratch = _r[0] if _r else \"-\"\n"
        "    _names = {\"N\": \"new\", \"P\": \"promoted\", \"D\": \"discarded\"}\n"
        "    mems = memories_from(path)\n"
        "    if mems:\n"
        "        m = mems[0]\n"
        "        meta = m.metadata or {}\n"
        "        why = (meta.get(\"$agent_memory\") or {}).get(\"invalidation_reason\")\n"
        "        durable = (f\"long-term: mem={m.id[:8]} rev={meta.get('revision', '')[:8]} \"\n"
        "                   f\"{status_value(m)}\" + (f\" ({why})\" if why else \"\"))\n"
        "    else:\n"
        "        durable = \"long-term: (not promoted yet)\"\n"
        "    print(f\"  {stage:24} | scratch={scratch} ({_names.get(scratch,'?')})  ->  {durable}\")\n"
        "\n"
        "TRACE_DEFECT = f\"/inbox/{ASSET_A}/trace-pier7.md\"\n"
        "TRACE_REPAIR = f\"/inbox/{ASSET_A}/trace-pier7-repair.md\"\n"
        "# start the story clean (idempotent): forget any earlier run of this trace\n"
        "for _p in (TRACE_DEFECT, TRACE_REPAIR):\n"
        "    for _m in memories_from(_p):\n"
        "        memory.delete_memory(_m.id)\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"DELETE FROM HARNESS_SCRATCH WHERE path = :p\", p=_p)\n"
        "conn.commit()\n"
        "ok(\"follow() lens ready\")"
    ),
    md(
        "**Stage 1 - written.** A field note lands in the inbox at status `N`. Nothing is\n"
        "durable yet; it is only a *candidate*."
    ),
    code(
        "write_note(TRACE_DEFECT,\n"
        "           f\"Pier 7 of {ASSET_A}: bearing plate shows active corrosion with measurable\"\n"
        "           \" section loss. Load rating review recommended; monitor monthly.\")\n"
        "follow(TRACE_DEFECT, \"1. written\")"
    ),
    md(
        "**Stage 2 - promoted.** The note passes the gate, the store's extraction keeps it\n"
        "(a completed, durable finding) as one **verbatim** memory, and the memory inherits\n"
        "its provenance. Watch `scratch` flip `N -> P` and a memory id appear."
    ),
    code(
        "promote_note(TRACE_DEFECT)\n"
        "follow(TRACE_DEFECT, \"2. promoted\")"
    ),
    md(
        "**Stage 3 - superseded.** Months later the repair is done. Its note is promoted too,\n"
        "the store's link step recognises it completes the defect, and the old memory flips\n"
        "to **invalid** - it stays on record, with the reason, but is no longer current."
    ),
    code(
        "write_note(TRACE_REPAIR,\n"
        "           f\"Pier 7 of {ASSET_A}: bearing plates replaced and recoated; corrosion\"\n"
        "           \" remediated, section loss addressed. Load rating restored to design.\")\n"
        "promote_note(TRACE_REPAIR)\n"
        "follow(TRACE_DEFECT, \"3. after repair promoted\")\n"
        "follow(TRACE_REPAIR, \"   (the repair itself)\")"
    ),
    md(
        "**Stage 4 - recall prefers the present.** Asking about pier 7 now returns the repair;\n"
        "the superseded defect is filtered out of retrieval (it remains queryable as history,\n"
        "just no longer competes for the agent's attention)."
    ),
    code(
        "print(\"  recall('pier 7 bearing corrosion'):\")\n"
        "_hits = recall(\"pier 7 bearing corrosion\", ASSET_A)\n"
        "for _h in _hits:\n"
        "    _tag = (\"  <- the repair (current)\" if _h[\"source_path\"] == TRACE_REPAIR\n"
        "            else \"  <- the SUPERSEDED defect\" if _h[\"source_path\"] == TRACE_DEFECT else \"\")\n"
        "    print(f\"    score={_h['score']:.3f}  {_h['source_path']}{_tag}\")\n"
        "_defect_shown = any(_h[\"source_path\"] == TRACE_DEFECT for _h in _hits)\n"
        "print(f\"\\n  the superseded defect is \"\n"
        "      f\"{'STILL shown' if _defect_shown else 'correctly hidden'} in recall\")\n"
        "ok(\"followed one note: written -> promoted -> remembered -> superseded -> hidden\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the same supersession, as a first-class relation (26.8 graph memory)
# --------------------------------------------------------------------------
RELATIONS = [
    md(
        "## 5c · The relation itself: what the store wrote, and what it buys\n"
        "\n"
        "Section 5's supersession was never ours: the store's link step wrote a `supersedes`\n"
        "relation into the managed `CITY_MEMORY_LINK` table and flipped the defect to `invalid`.\n"
        "This section looks at that relation directly - as **data**, not just a status flag:\n"
        "\n"
        "| question | how |\n"
        "|---|---|\n"
        "| *what is true now?* | `search(..., include_invalid_results=False)` |\n"
        "| *what did we used to believe, and what changed it?* | `num_hops=1` follows the link from the old memory to the new one |\n"
        "| *the store got it wrong* | `delete_record_link` - a trigger revalidates the old memory |\n"
        "| *I know two memories are related; the store doesn't* | `link_records` (TODO 4) |\n"
        "\n"
        "Which relations invalidate? `supersedes`, `refines` and `duplicates` flip their target to\n"
        "`invalid`; `contradicts` and `supports` leave both memories current.\n"
        "\n"
        "What stays ours: the opt-in gate, the curation and link *instructions*, the provenance\n"
        "keys, and re-run hygiene. **The store does the bookkeeping and the judging; we write\n"
        "the policy - and check it.**"
    ),
    code(
        "# The two memories in this relation came from Section 5's promotion of the repair note.\n"
        "# Find them by provenance - no sidecar, no raw SQL.\n"
        "_d, _r = memories_from(SUPERSEDE_DEFECT_PATH), memories_from(SUPERSEDE_REPAIR_PATH)\n"
        "DEFECT_MID = _d[0].id if _d else None\n"
        "REPAIR_MID = _r[0].id if _r else None"

        "check(bool(DEFECT_MID and REPAIR_MID),\n"
        "      f\"found both memories (defect={str(DEFECT_MID)[:12]}, \"\n"
        "      f\"repair={str(REPAIR_MID)[:12]})\")\n"
        "\n"
        "\n"
        "def linked(memory_id, query=\"bearing plate corrosion at pier 2\"):\n"
        "    \"\"\"Every relation touching `memory_id`, as (relation, neighbour) pairs.\n"
        "\n"
        "    search(num_hops=1) attaches a shortest-path tree to each hit as\n"
        "    `linked_results`: a list of (RecordRelation, SearchResult) tuples, where the\n"
        "    result is the record at the *other* end - whichever direction the relation\n"
        "    was stored in.\"\"\"\n"
        "    for hit in memory.search(query, user_id=ASSET_A, agent_id=\"CITY\",\n"
        "                             max_results=20, num_hops=1, max_linked_results=10,\n"
        "                             include_invalid_results=True):\n"
        "        if hit.id == memory_id:\n"
        "            return hit, list(hit.linked_results or [])\n"
        "    return None, []\n"
        "\n"
        "\n"
        "def status_of(memory_id):\n"
        "    \"\"\"Lifecycle status off the search result - no raw SQL.\"\"\"\n"
        "    hit, _ = linked(memory_id)\n"
        "    if hit is None:\n"
        "        return None\n"
        "    return getattr(hit.status, \"value\", hit.status)"
    ),
    code(
        "# Nothing below created this. Section 5 posted the repair note; the store linked it.\n"
        "_defect, _rels = linked(DEFECT_MID)\n"
        "print(f\"relations touching the defect memory ({len(_rels)}):\")\n"
        "for _rel, _other in _rels:\n"
        "    _dir = \"->\" if _rel.source_record_id == DEFECT_MID else \"<-\"\n"
        "    print(f\"   {_rel.relation_type:<12} {_dir} {_other.id[:12]} \"\n"
        "          f\"[{getattr(_other.status, 'value', _other.status)}]  {_other.content[:46]}...\")\n"
        "\n"
        "SUPERSEDED_BY = [(r, o) for r, o in _rels\n"
        "                 if r.relation_type == \"supersedes\" and r.target_record_id == DEFECT_MID]\n"
        "check(bool(SUPERSEDED_BY),\n"
        "      \"the store recorded a 'supersedes' relation on its own, during promotion\")\n"
        "check(status_of(DEFECT_MID) == \"invalid\",\n"
        "      f\"and flipped the superseded memory's lifecycle (status={status_of(DEFECT_MID)!r}) - \"\n"
        "      \"no column of ours involved\")"
    ),
    md(
        "**The payoff is not the hiding - it is the asking.** `recall()` in Section 5 can only\n"
        "*suppress* a superseded memory. A relation is data, so one store answers both\n"
        "questions: *what is true now?* and *what did we believe before, and what changed\n"
        "it?* The first is `include_invalid_results=False`; the second is `num_hops=1`."
    ),
    code(
        "# What is true now: invalid records stay out of the result, no filtering of ours.\n"
        "_now = memory.search(\"bearing plate corrosion at pier 2\", user_id=ASSET_A,\n"
        "                     agent_id=\"CITY\", max_results=5, record_types=[\"memory\"],\n"
        "                     include_invalid_results=False)\n"
        "print(\"current belief:\")\n"
        "for h in _now:\n"
        "    print(f\"   {h.id[:12]} {h.content[:78]}...\")\n"
        "check(all(h.id != DEFECT_MID for h in _now),\n"
        "      \"the superseded defect does not compete for retrieval attention\")\n"
        "\n"
        "# What changed it: one hop from the superseded memory reaches the memory that\n"
        "# replaced it - the status flag alone says only *that* it was replaced, not by what.\n"
        "_reached = {o.id for r, o in SUPERSEDED_BY}\n"
        "print(f\"\\nthe defect was superseded by: {[i[:12] for i in _reached]}\")\n"
        "check(REPAIR_MID in _reached,\n"
        "      \"one hop names the memory that replaced it - history, not just absence\")"
    ),
    md(
        "**Undo is a delete, and the store repairs itself.** The managed schema carries a\n"
        "delete trigger on the link table: remove an invalidating relation and the memory it\n"
        "pointed at returns to `valid`, invalidation reason cleared. That trigger is what\n"
        "`CREATE TRIGGER` buys, and why Section 0 refuses to open the store without it.\n\n"
        "Deleting it also leaves you somewhere useful for the TODO: a world where the\n"
        "relation is *missing* and you have to write it yourself - which is the API you would\n"
        "reach for when **you** know two memories are related and the store does not."
    ),
    code(
        "RELATION_ID = SUPERSEDED_BY[0][0].id\n"
        "memory.delete_record_link(relation_id=RELATION_ID)\n"
        "_restored = status_of(DEFECT_MID)\n"
        "check(_restored == \"valid\",\n"
        "      f\"deleting the relation revalidated the memory (status={_restored!r}) - \"\n"
        "      \"the trigger did that, not our code\")\n"
        "\n"
        "# \u270f\ufe0f TODO(4): put it back by hand. The repair memory SUPERSEDES the defect one -\n"
        "#             direction matters, and the source is the memory that wins. Both\n"
        "#             endpoints are memory-like records, so pass record_type 'memory' for\n"
        "#             each, and carry the provenance path in metadata so the link explains\n"
        "#             itself later. Built-in types: supersedes / contradicts / refines /\n"
        "#             supports / duplicates. Returns the new relation_id.\n"
        "# TODO-SOLUTION-START\n"
        "RELATION_ID = memory.link_records(\n"
        "    source_record_id=REPAIR_MID, source_record_type=\"memory\",\n"
        "    target_record_id=DEFECT_MID, target_record_type=\"memory\",\n"
        "    relation_type=\"supersedes\",\n"
        "    metadata={\"source_path\": SUPERSEDE_REPAIR_PATH},\n"
        ")\n"
        "# TODO-SOLUTION-END\n"
        "check(status_of(DEFECT_MID) == \"invalid\",\n"
        "      \"writing the relation by hand invalidates it again - same mechanism, \"\n"
        "      \"whether the store inferred it or you asserted it\")\n"
        "ok(\"supersession is recorded in the store, not beside it\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the briefing, built from current memory
# --------------------------------------------------------------------------
BRIEFING = [
    md(
        "## 6 · The morning briefing, built from current memory\n\n"
        "Everything so far pays off here. The briefing reads the asset's **current** memories\n"
        "- superseded ones are already `invalid`, so the corroded-bearing defect is not\n"
        "reported as open - plus a few numbers from the findings table. The model narrates;\n"
        "the code decides what it is allowed to narrate, and every memory carries its\n"
        "`source_path`, so each claim can be traced to the note it came from.\n\n"
        "Run it from whatever scheduler you already have; the briefing is just a function."
    ),
    code(
        "from datetime import date\n"
        "\n"
        "\n"
        "def build_briefing(asset_id):\n"
        "    \"\"\"Current, provenanced memories + recent finding counts. No model call.\"\"\"\n"
        "    mems = memory.list_memories(user_id=asset_id, agent_id=\"CITY\", limit=200)\n"
        "    current = [m for m in mems\n"
        "               if status_value(m) == \"valid\" and \"source_path\" in (m.metadata or {})]\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"\"\"SELECT severity, COUNT(*) FROM CITY_INSPECTION_FINDING\n"
        "                       WHERE asset_id = :a AND days_ago <= 30\n"
        "                       GROUP BY severity\"\"\", a=asset_id)\n"
        "        findings = dict(cur.fetchall())\n"
        "    return {\n"
        "        \"asset\": asset_id,\n"
        "        \"generated_for\": date.today().isoformat(),\n"
        "        \"findings_last_30_days\": findings,\n"
        "        \"memories\": sorted(({\"source_path\": m.metadata[\"source_path\"],\n"
        "                             \"days_ago\": m.metadata.get(\"days_ago\") or 0,\n"
        "                             \"content\": m.content} for m in current),\n"
        "                           key=lambda r: r[\"days_ago\"]),\n"
        "    }\n"
        "\n"
        "\n"
        "BRIEFING_INPUT = build_briefing(ASSET_A)\n"
        "for _m in BRIEFING_INPUT[\"memories\"]:\n"
        "    print(f\"  {_m['days_ago']:>4}d  {_m['source_path']}\")\n"
        "_paths = {m[\"source_path\"] for m in BRIEFING_INPUT[\"memories\"]}\n"
        "check(SUPERSEDE_REPAIR_PATH in _paths and SUPERSEDE_DEFECT_PATH not in _paths,\n"
        "      \"the briefing sees the repair, not the defect it superseded\")"
    ),
    code(
        "def narrate_briefing(briefing):\n"
        "    # ✏️ TODO(5): the grounded narration - ask CHAT for a <=6-sentence morning\n"
        "    #             briefing using ONLY the memories and numbers in `briefing`, citing\n"
        "    #             each memory's source_path in [brackets]. Return the text.\n"
        "    # TODO-SOLUTION-START\n"
        "    cfg = {\"callbacks\": [HANDLER]} if HANDLER else {}\n"
        "    resp = CHAT.invoke(\n"
        "        \"Write a morning asset-risk briefing for a city operations chief.\\n\"\n"
        "        \"HARD RULE: use ONLY the memories and numbers in this JSON - do not estimate,\\n\"\n"
        "        \"extrapolate, or invent. Cite each memory you use by its source_path in\\n\"\n"
        "        \"[brackets]. <= 6 sentences, plain prose.\\n\\n\"\n"
        "        + json.dumps(briefing), config=cfg)\n"
        "    return resp.content if isinstance(resp.content, str) else \"\".join(\n"
        "        p.get(\"text\", \"\") if isinstance(p, dict) else str(p) for p in resp.content)\n"
        "    # TODO-SOLUTION-END\n"
        "\n"
        "\n"
        "BRIEFING_TEXT = narrate_briefing(BRIEFING_INPUT)\n"
        "print(BRIEFING_TEXT)\n"
        "\n"
        "# Kept as a scratch note: outside /inbox, so it is never promoted into memory.\n"
        "BRIEFING_PATH = f\"/briefings/{ASSET_A}/{BRIEFING_INPUT['generated_for']}.md\"\n"
        "write_note(BRIEFING_PATH, BRIEFING_TEXT)\n"
        "_cited = sorted(p for p in _paths if p in BRIEFING_TEXT)\n"
        "ok(f\"briefing saved to {BRIEFING_PATH}; cites {len(_cited)} of {len(_paths)} memories\")"
    ),
]

# --------------------------------------------------------------------------
# Section: continuity of work
# --------------------------------------------------------------------------
CONTINUITY = [
    md(
        "## 7 · Continuity: a new session resumes the *work*, not just the facts\n\n"
        "The review granted the original notebook fact-persistence but noted the hard half\n"
        "is resuming *work* - goal, done, next. So the briefing workflow keeps its plan as a\n"
        "scratch note, and a brand-new connection + brand-new SDK client picks it up and\n"
        "continues, without this notebook's kernel state."
    ),
    code(
        "write_note(\"/plans/briefing_plan.md\", json.dumps({\n"
        "    \"goal\": \"daily asset-risk briefing from current memory, every claim cited\",\n"
        "    \"done\": [\"inbox curated into memory\", \"first briefing narrated\"],\n"
        "    \"next\": \"review narration tone with operations chief; tune half-life\",\n"
        "}))\n"
        "ok(\"briefing plan state persisted to /plans/briefing_plan.md\")"
    ),
    code(
        "# A second 'session': fresh connection, fresh SDK client - no shared kernel state.\n"
        "conn2 = get_connection(settings)\n"
        "memory2 = OracleAgentMemory(\n"
        "    connection=conn2,\n"
        "    embedder=OracleONNXEmbedder(conn2, settings.embed_model),\n"
        "    llm=SdkLlm(**litellm_spec(settings)),\n"
        "    extract_memories=False,\n"
        "    schema_policy=SchemaPolicy.REQUIRE_EXISTING,\n"
        "    table_name_prefix=\"CITY_\",\n"
        ")\n"
        "\n"
        "with conn2.cursor() as cur:\n"
        "    cur.execute(\"SELECT content FROM HARNESS_SCRATCH WHERE path = '/plans/briefing_plan.md'\")\n"
        "    _raw = cur.fetchone()[0]\n"
        "plan = json.loads(_raw.read() if hasattr(_raw, \"read\") else _raw)\n"
        "print(\"resumed goal:\", plan[\"goal\"])\n"
        "print(\"next action :\", plan[\"next\"])\n"
        "\n"
        "_hits2 = memory2.search(\"bearing plate repair\", user_id=ASSET_A, agent_id=\"CITY\",\n"
        "                        max_results=2)\n"
        "with conn2.cursor() as cur:\n"
        "    cur.execute(\"SELECT COUNT(*) FROM HARNESS_SCRATCH WHERE path LIKE '/briefings/%'\")\n"
        "    _narrated = cur.fetchone()[0]\n"
        "check(len(plan[\"next\"]) > 0 and len(_hits2) > 0 and _narrated >= 1,\n"
        "      \"new session resumed the plan, the memories, and the briefing\")\n"
        "conn2.close()"
    ),
]

# --------------------------------------------------------------------------
# Section: closing
# --------------------------------------------------------------------------
CLOSING = [
    md(
        "## 8 · What you built (vs. what the review criticised)\n\n"
        "| Review gap (Path 1) | Fix you built |\n"
        "|---|---|\n"
        "| Every scratch file graduates | `/inbox` opt-in + the store's extraction under your curation instructions (one verbatim memory, or nothing) |\n"
        "| Chunked re-extraction invents facts | Whole-note memories, verbatim - instructed, and checked |\n"
        "| No provenance, no supersession | Provenance as memory metadata (source path, revision, observed age); supersession as the store's own relations |\n"

        "| Nothing forgets | Superseded memories invalidated, out of current recall; recency weighted by the observation's real age |\n"
        "| (payoff) | A briefing built only from current memory, each claim citing its source note |\n"
        "| Facts persist, work doesn't | Plan state resumed by a fresh session |\n\n"

        "Next: **03 - Context engineering**, where compaction and offloading get measured for\n"
        "*fidelity*, not just size."
    ),
    code(
        "for desc, passed in verify(conn, \"02_scheduled_briefings\"):\n"
        "    check(passed, desc)\n"
        "ok(\"notebook 02 artifacts in place - continue to 03_context_engineering\")"
    ),
]

SECTIONS = [INTRO, SETUP, SDK_INIT, SCRATCH, PRODUCER, TRIAGE, PROMOTION,
            RECALL, TRACE, RELATIONS, BRIEFING, CONTINUITY, CLOSING]


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
    nbf.write(build(), "notebooks/02_scheduled_briefings_complete.ipynb")
    print("wrote notebooks/02_scheduled_briefings_complete.ipynb")
