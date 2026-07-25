# Deployment

How to run this repo in GitHub Codespaces, configure it, use the Langfuse UI,
and tear it all down. Local setup is in the [README](../README.md); this
document is the Codespaces path end to end.

## 1 · Start in Codespaces

1. **Add Codespaces secrets** first. The devcontainer reads these at create
   time; they are injected into the Codespace as environment variables (see
   [§2.1](#21--how-secrets-reach-the-app) for why that matters):

   | Secret | Required? | What it is |
   |---|---|---|
   | `WALLET_B64` | yes | base64 of your ADB wallet zip — see the encoding step below |
   | `DB_PASSWORD` | yes | the database user's password |
   | `WALLET_PASSWORD` | yes | password set when the wallet was downloaded from OCI |
   | `ANTHROPIC_API_KEY` | per provider | needed when `LLM_PROVIDER=anthropic` (the default) |
   | `OPENAI_API_KEY` | per provider | needed when `LLM_PROVIDER=openai` |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | only for `cloud` | paste from langfuse.com; **not** needed for local Langfuse |

   ### Encode the wallet for `WALLET_B64`

   Download your ADB wallet from OCI (a `Wallet_*.zip`), then base64-encode the
   **zip itself** into a single line — `post-create.sh` decodes it and unzips it
   into `wallet/`:

   ```bash
   base64 -w0 Wallet_ANANT.zip > wallet.b64      # Linux
   base64 -i  Wallet_ANANT.zip | tr -d '\n' > wallet.b64   # macOS
   ```

   The secret value is the contents of `wallet.b64` (paste the whole string).

   ### Create the secrets — web UI

   Repo → **Settings** → **Secrets and variables** → **Codespaces** → **New
   repository secret**. Add each row above (Name = the secret name, Secret = the
   value). For a value that spans a line — `WALLET_B64` — paste the whole string
   into the Secret box.

   > Prefer to keep secrets off the repo? Add them at the **account** level
   > instead: github.com → your avatar → **Settings** → **Codespaces** →
   > **Repository access**, and grant this repository access to each secret.
   > Account-level secrets work across all your Codespaces; repo-level secrets
   > are scoped to this repo. Either is fine — the devcontainer reads whatever
   > ends up in the environment.

   ### Create the secrets — `gh` CLI

   ```bash
   gh secret set WALLET_B64      --app codespaces < wallet.b64
   gh secret set DB_PASSWORD     --app codespaces        # prompts for the value
   gh secret set WALLET_PASSWORD --app codespaces
   gh secret set ANTHROPIC_API_KEY --app codespaces
   gh secret list --app codespaces                       # verify
   ```

   > **Secrets apply on the next start.** If you add or change a secret while a
   > Codespace is already running, it won't pick it up until you **stop and
   > start** that Codespace (Code → Codespaces → ⋯ → Stop), or rebuild the
   > container. New Codespaces get them immediately.

2. **Create the Codespace** (Code → Codespaces → Create). On first boot
   [`.devcontainer/post-create.sh`](../.devcontainer/post-create.sh) runs
   automatically and:
   - installs `cityops_harness` and registers the `harness` Jupyter kernel,
   - unpacks `WALLET_B64` into `wallet/` (skipped if the folder already exists),
   - seeds `.env` from `.env.example` if `.env` is absent.

   The devcontainer requests 4 CPUs / 8 GB — enough to run the local Langfuse
   stack (§3). It forwards ports **3000** (Langfuse) and **11434** (Ollama).

## 2 · Set the environment variables

Secrets seed the machine; the per-run configuration lives in **`.env`** (created
for you, git-ignored). Open it and set:

```bash
# Oracle Autonomous DB
DB_USER=ADMIN                 # or your ADB user
DB_DSN=anant_low              # a service alias from wallet/tnsnames.ora
EMBED_MODEL=ALL_MINILM_L12_V2 # leave as-is (state checks reference it by name)

# LLM provider: anthropic | openai | ollama
LLM_PROVIDER=anthropic

# Langfuse: off | local | cloud
LANGFUSE_MODE=off
```

`DB_PASSWORD`, `WALLET_PASSWORD`, and the API keys come from the Codespaces
secrets — you don't paste them into `.env`. Confirm everything is wired up by
running **`notebooks/00_setup.ipynb`** top to bottom; every section ends in a
green check.

> **Non-ADMIN DB users:** `00_setup.ipynb` loads the ONNX embedding model via
> `DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD`. Once, as ADMIN, run
> `GRANT EXECUTE ON DBMS_CLOUD TO <your_user>;`. Notebook 02's scheduled
> pipeline also needs `GRANT CREATE PROCEDURE TO <your_user>;` and
> `GRANT CREATE JOB TO <your_user>;`.

Notebooks **00–03 run with `LANGFUSE_MODE=off`**. Only **notebook 04 (evals)
requires Langfuse** — set `LANGFUSE_MODE=local` and bring up the stack below.

### 2.1 · How secrets reach the app

Worth understanding, because `.env` and the secrets look like they overlap but
don't:

- **Codespaces injects each secret as an environment variable** into the
  container — it never writes them into `.env`. `WALLET_B64` is consumed by
  `post-create.sh` at build time; the rest sit in the environment.
- **`.env` is only the non-secret config** (`DB_DSN`, `LLM_PROVIDER`,
  `LANGFUSE_MODE`). `post-create.sh` seeds it from `.env.example`, so it starts
  with *placeholders* like `DB_PASSWORD=change_me`.
- **The real value wins.** `load_settings()` calls `load_dotenv()`, which
  defaults to `override=False` — it will not overwrite a variable already in the
  environment. So the injected `DB_PASSWORD` beats the `.env` placeholder;
  `.env` is a fallback, not the source of truth.
- **Locally it's the reverse:** no injected variables, so you paste real values
  into your hand-edited `.env` and the same code reads them from there.

Corollary: if a secret is **missing**, nothing overrides the placeholder and the
app silently uses `change_me`, surfacing as an auth failure — the fix is *add the
secret*, not edit `.env`.

## 3 · Langfuse UI (local, self-hosted)

Only needed for notebook 04, or any time you want to inspect traces.

**Start the stack** (first run pulls several GB — Langfuse, ClickHouse,
Postgres, MinIO, Redis):

```bash
docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml up -d
```

Wait for it to be healthy (~30–60s after the pull):

```bash
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/public/health)" = "200" ]; do sleep 5; done; echo ready
```

**Open the UI:** in Codespaces, the **Ports** tab shows port **3000**
(“Langfuse”) — click the globe icon to open the forwarded URL. Locally it's
`http://localhost:3000`.

The override file seeds a ready-to-use project and login, so there is nothing to
click through:

| | value |
|---|---|
| Login email | `workshop@example.com` |
| Login password | `workshop123` |
| Project | `cityops-agent-harness` |
| Public key | `pk-lf-local-0000` |
| Secret key | `sk-lf-local-0000` |

These deterministic keys are what `cityops_harness.tracing` uses in `local`
mode, so with `LANGFUSE_MODE=local` the notebooks authenticate automatically —
you do **not** put them in `.env`. After running notebook 04, its five datasets
(`promotion-precision`, `skill-fidelity`, `skills-help`, `card-fidelity`,
`cost-per-correct`) appear under **Datasets**, each with a scored run.

> **Port note:** ClickHouse's host-published debug ports are remapped to
> `19000`/`18123` (from the usual `9000`/`8123`) in
> `docker-compose.langfuse.yml`, because `9000` collides readily on a shared dev
> host. This is internal only — nothing you use changes; the UI is still on 3000.

## 4 · Tear down

**Stop Langfuse** (keeps the data volumes, so a later `up -d` is fast):

```bash
docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml down
```

Add `-v` to also delete the stored traces/datasets:

```bash
docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml down -v
```

**Stop the ADB scheduler jobs** notebook 02 leaves running (they fire hourly /
daily by design). From any notebook cell or SQL client:

```sql
BEGIN DBMS_SCHEDULER.DISABLE('HARNESS_STAGE_JOB');    END;
BEGIN DBMS_SCHEDULER.DISABLE('HARNESS_BRIEFING_JOB'); END;
```

**Stop the Codespace:** it auto-suspends when idle; to end it, Code → Codespaces
→ … → **Stop**, or **Delete** to reclaim storage. Nothing in the ADB is removed
by deleting the Codespace — the database and the `HARNESS_%` / `CITY_%` objects
persist until you drop them.
