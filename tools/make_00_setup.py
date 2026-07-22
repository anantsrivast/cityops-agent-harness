"""Regenerate notebooks/00_setup.ipynb. Run: .venv/bin/python tools/make_00_setup.py"""

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell(
    "# 00 - Setup: verify your environment\n\n"
    "Run every cell top to bottom. Each section ends with a green check.\n\n"
    "Prerequisites: `.env` filled in (copy `.env.example`), the ADB wallet in "
    "`wallet/`, and - depending on `LLM_PROVIDER` - an API key or a running "
    "Ollama with the configured model pulled (`ollama pull qwen3`)."
))

cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.checks import ok, check\n"
    "from cityops_harness.config import load_settings\n"
    "\n"
    "settings = load_settings()\n"
    "ok(f\"settings loaded - provider={settings.llm_provider}, \"\n"
    "   f\"langfuse={settings.langfuse_mode}, dsn={settings.db_dsn}\")"
))

cells.append(nbf.v4.new_markdown_cell("## 1 · Autonomous Database"))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.db import get_connection\n"
    "\n"
    "conn = get_connection(settings)\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\"SELECT banner_full FROM v$version\")\n"
    "    banner = cur.fetchone()[0]\n"
    "ok(banner.splitlines()[0])"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 2 · In-database embeddings (ONNX)\n\n"
    "Embeddings run **inside** the database - no API key, no text egress. The\n"
    "cell below loads Oracle's `ALL_MINILM_L12_V2` model from the public\n"
    "OML-Resources object-storage bucket if it is not already present."
))
cells.append(nbf.v4.new_code_cell(
    "ONNX_URI = (\"https://objectstorage.us-ashburn-1.oraclecloud.com\"\n"
    "            \"/n/adwc4pm/b/OML-Resources/o/all_MiniLM_L12_v2.onnx\")\n"
    "\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\n"
    "        \"SELECT COUNT(*) FROM user_mining_models WHERE model_name = :m\",\n"
    "        m=settings.embed_model,\n"
    "    )\n"
    "    present = cur.fetchone()[0] > 0\n"
    "\n"
    "if not present:\n"
    "    with conn.cursor() as cur:\n"
    "        cur.execute(\"\"\"\n"
    "            BEGIN\n"
    "              DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD(\n"
    "                model_name => :m,\n"
    "                credential => NULL,\n"
    "                uri        => :u,\n"
    "                metadata   => JSON('{\"function\":\"embedding\",'\n"
    "                                   || '\"embeddingOutput\":\"embedding\",'\n"
    "                                   || '\"input\":{\"input\":[\"DATA\"]}}')\n"
    "              );\n"
    "            END;\"\"\", m=settings.embed_model, u=ONNX_URI)\n"
    "    conn.commit()\n"
    "\n"
    "with conn.cursor() as cur:\n"
    "    cur.execute(\n"
    "        f\"SELECT VECTOR_EMBEDDING({settings.embed_model} USING 'hello' AS DATA)\"\n"
    "        \" FROM dual\"\n"
    "    )\n"
    "    vec = cur.fetchone()[0]\n"
    "check(vec is not None, f\"{settings.embed_model} embeds in-database\")"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 3 · LLM provider\n\n"
    "One env var (`LLM_PROVIDER`) drives both LLM consumers: LangChain chat\n"
    "calls and the Oracle Agent Memory SDK (which speaks LiteLLM)."
))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.llm import chat_model, litellm_spec, sdk_llm\n"
    "\n"
    "print(\"LiteLLM spec:\", litellm_spec(settings))\n"
    "_ = sdk_llm(settings)  # constructs the Agent Memory SDK adapter\n"
    "\n"
    "model = chat_model(settings)\n"
    "reply = model.invoke(\"Reply with exactly: pong\")\n"
    "check(\"pong\" in reply.content.lower(),\n"
    "      f\"{settings.llm_provider} responded: {reply.content[:60]!r}\")"
))

cells.append(nbf.v4.new_markdown_cell(
    "## 4 · Langfuse (optional)\n\n"
    "`LANGFUSE_MODE=cloud` needs keys in `.env`; `local` needs the compose\n"
    "stack up (`docker compose -f docker-compose.langfuse.yml -f "
    "docker-compose.langfuse.override.yml up -d`); `off` skips this section."
))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.tracing import init_tracing\n"
    "\n"
    "handler = init_tracing(settings)\n"
    "if handler is None:\n"
    "    ok(\"Langfuse off - skipping\")\n"
    "else:\n"
    "    traced = chat_model(settings).invoke(\n"
    "        \"Say: traced\", config={\"callbacks\": [handler]}\n"
    "    )\n"
    "    from langfuse import get_client\n"
    "    get_client().flush()\n"
    "    ok(f\"trace sent to Langfuse ({settings.langfuse_mode}) - \"\n"
    "       \"check the UI for a '00_setup' trace\")"
))

cells.append(nbf.v4.new_markdown_cell("## 5 · Summary"))
cells.append(nbf.v4.new_code_cell(
    "from cityops_harness.state import verify\n"
    "\n"
    "for desc, passed in verify(conn, \"00_setup\"):\n"
    "    check(passed, desc)\n"
    "ok(\"environment ready - continue to 01_self_improving_copilot\")"
))

nb["cells"] = cells
nbf.write(nb, "notebooks/00_setup.ipynb")
print("wrote notebooks/00_setup.ipynb")
