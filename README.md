# cityops-agent-harness

Agent memory **and harness engineering**, hands-on: the sequel to the CityOps
Copilot workshop. The copilot you built there gets a self-improving harness -
registered tools, harvested skills, scheduled memory promotion, and context
engineering - with every piece of durable state living in Oracle Autonomous
Database 23ai, and an eval suite (Langfuse) measuring whether the learning
actually works.

## The series

| Notebook | What it teaches |
|---|---|
| `notebooks/00_setup.ipynb` | Verify ADB, in-DB embeddings, LLM provider, Langfuse |
| `notebooks/01_self_improving_copilot_complete.ipynb` (+ `_todo`) | Tool registry, verified workflow capture, skill harvesting with lifecycle |
| `notebooks/02_scheduled_briefings_complete.ipynb` (+ `_todo`) | Curated whole-note promotion, provenance as memory metadata, supersession as the store's own graph relation, a briefing built from current memory |
| `notebooks/03_context_engineering_complete.ipynb` (+ `_todo`) | The store's running summary and context card under a fidelity probe, with a verbatim-transcript fallback; agent-in-the-loop offloading, with offloaded blobs marked as never-memories |
| `notebooks/04_evals_complete.ipynb` (+ `_todo`) | Five Langfuse evals: promotion precision, skill fidelity, skills-help, card fidelity over horizon, cost per correct |

Notebooks 01-04 come in two flavors: `*_complete.ipynb` (full solutions) and
generated `*_todo.ipynb` (fill in the marked gaps; regenerate with
`python tools/make_student.py`).

Prerequisite: the CityOps Copilot workshop (`notebook_complete_ollama.ipynb`,
kept in this repo for reference - unmodified).

## Quick start (GitHub Codespaces)

1. Add Codespaces secrets: `WALLET_B64` (base64 of your ADB wallet zip),
   `DB_PASSWORD`, `WALLET_PASSWORD`, and - per provider - `ANTHROPIC_API_KEY`
   or `OPENAI_API_KEY` (none needed for Ollama). Optional: `LANGFUSE_PUBLIC_KEY`
   / `LANGFUSE_SECRET_KEY` for cloud tracing.
2. Create a Codespace. The devcontainer installs everything and unpacks the wallet.
3. Fill any gaps in `.env`, then run `notebooks/00_setup.ipynb`.

Full walkthrough — secrets, `.env`, the Langfuse UI, and teardown — in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

**New here?** [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) narrates the *why and how*
of the whole project and each notebook, with diagrams. For a deep, line-of-sight
explanation of notebook 01's machinery, see
[docs/notebook-01-explained.md](docs/notebook-01-explained.md).

## Quick start (local)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # fill in DB_PASSWORD, WALLET_PASSWORD, keys
# place your ADB wallet files in wallet/   (git-ignored)
.venv/bin/jupyter lab notebooks/00_setup.ipynb
```

> **Non-ADMIN database users:** run these once as ADMIN, or notebooks 00 and 02
> fail:
>
> ```sql
> GRANT EXECUTE ON DBMS_CLOUD TO <your_user>;   -- nb00: loads the ONNX model
> GRANT CREATE TRIGGER TO <your_user>;          -- nb02: Agent Memory v13 schema
> ```
>
> Without `DBMS_CLOUD`, the model load fails with
> `ORA-00904: "DBMS_CLOUD"."GET_OBJECT": invalid identifier`.
>
> `CREATE TRIGGER` is new with Oracle Agent Memory 26.8, whose managed schema
> (v13) adds a `<PREFIX>MEMORY_LINK` table plus a delete trigger that
> revalidates memories when an invalidating relation is removed. **Grant it
> before opening a store that was created by an older SDK:** the v12 → v13
> upgrade retypes `MESSAGE.CONTENT` from `CLOB` to `JSON` *before* creating the
> trigger, so a run without the privilege leaves the store stamped v12 with a
> v13 column — readable by neither SDK version. Notebook 02 checks all three
> privileges in §0 and stops there, before any schema DDL, if one is missing.

## LLM providers

Set `LLM_PROVIDER` in `.env`:

| Provider | Needs | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | default; model `claude-opus-4-8` |
| `openai` | `OPENAI_API_KEY` | model `gpt-4o` |
| `ollama` | local Ollama + `ollama pull qwen3` | tool-capable model required; in Codespaces install first (`curl -fsSL https://ollama.com/install.sh | sh`); CPU runs are slow but correct |

## Langfuse

Set `LANGFUSE_MODE` in `.env`: `cloud` (keys from langfuse.com), `local`
(`docker compose -f docker-compose.langfuse.yml -f
docker-compose.langfuse.override.yml up -d`, UI at http://localhost:3000,
login `workshop@example.com` / `workshop123`), or `off`.

## Development

```bash
.venv/bin/pytest -q          # unit tests (no DB or network needed)
python tools/make_student.py # regenerate *_todo.ipynb learner notebooks
```
