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
| `notebooks/02_scheduled_briefings_complete.ipynb` (+ `_todo`) | Curated whole-note promotion, provenance + supersession, DBMS_SCHEDULER pipeline, morning briefing |
| `notebooks/03_context_engineering_complete.ipynb` (+ `_todo`) | Compaction with a card-fidelity probe, agent-in-the-loop offloading, blobs barred from promotion |
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

## Quick start (local)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # fill in DB_PASSWORD, WALLET_PASSWORD, keys
# place your ADB wallet files in wallet/   (git-ignored)
.venv/bin/jupyter lab notebooks/00_setup.ipynb
```

> **Non-ADMIN database users:** `00_setup.ipynb` loads the ONNX embedding
> model via `DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD`, which needs object-storage
> access. If you connect as a regular user, first run (once, as ADMIN):
> `GRANT EXECUTE ON DBMS_CLOUD TO <your_user>;` — otherwise the load fails
> with `ORA-00904: "DBMS_CLOUD"."GET_OBJECT": invalid identifier`.

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
