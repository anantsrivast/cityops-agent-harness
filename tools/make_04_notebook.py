"""Regenerate notebooks/04_evals_complete.ipynb.

Run: python tools/make_04_notebook.py

Notebook 04 is the one notebook that REQUIRES Langfuse (LANGFUSE_MODE=local +
the compose stack up). The five evals run as Langfuse datasets via the 4.x
Experiments API - dataset.run_experiment(name=, task=, evaluators=[]) - pinned
live in the phase-04 plan's Task 0.
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
        "# 04 - Evals: measure what you claimed to fix\n\n"
        "Notebooks 01-03 each closed a gap the design review named. This notebook checks\n"
        "the work - through Langfuse, as datasets with scored traces - against the exact\n"
        "column the review said the original suite was *silent on*:\n\n"
        "| # | Eval | Closes the review's silence on... |\n"
        "|---|------|-----------------------------------|\n"
        "| 1 | **Promotion precision** | did the triage gate admit the *right* notes, not just some notes |\n"
        "| 2 | **Skill fidelity** | are distilled `SKILL.md` steps faithful to the trajectory they came from |\n"
        "| 3 | **Skills-help** | does harvesting skills actually *improve task success* (the missing experiment) |\n"
        "| 4 | **Card fidelity over a horizon** | does compaction keep the fact you'll need 20 turns later, not just stay small |\n"
        "| 5 | **Cost per correct answer** | is a smaller context *cheaper per correct answer*, with variance, not a lucky n=1 |\n\n"
        "Each eval builds a labelled dataset, runs it through `dataset.run_experiment`, scores\n"
        "every item on the server, then rolls the scores into one `check` that can fail. A\n"
        "green notebook here is the claim that the previous three actually did what they said."
    ),
]

# --------------------------------------------------------------------------
# Section: setup + Langfuse precondition
# --------------------------------------------------------------------------
SETUP = [
    md(
        "## 0 · Setup\n\n"
        "Unlike notebooks 00-03, this one **requires Langfuse**: the evals *are* Langfuse\n"
        "datasets. The precondition cell fails loudly, with the command to fix it, if the\n"
        "stack is not reachable - the same shape as notebook 02's privilege check."
    ),
    code(
        "import json\n"
        "import matplotlib.pyplot as plt\n"
        "from pydantic import BaseModel, Field\n"
        "\n"
        "from cityops_harness.checks import ok, check\n"
        "from cityops_harness.config import load_settings\n"
        "from cityops_harness.db import get_connection\n"
        "from cityops_harness.llm import chat_model\n"
        "from cityops_harness.state import require, verify\n"
        "from cityops_harness.tracing import init_tracing\n"
        "from cityops_harness import evals, promote, improve, context\n"
        "\n"
        "settings = load_settings()\n"
        "conn = get_connection(settings)\n"
        "require(conn, \"01_self_improving_copilot\")\n"
        "CHAT = chat_model(settings)\n"
        "ok(f\"connected - provider={settings.llm_provider}, langfuse={settings.langfuse_mode}\")"
    ),
    code(
        "# Langfuse is mandatory here. init_tracing sets the env; the client must auth.\n"
        "HANDLER = init_tracing(settings)\n"
        "from langfuse import get_client, Evaluation\n"
        "lf = get_client()\n"
        "_up = False\n"
        "try:\n"
        "    _up = lf.auth_check()\n"
        "except Exception as _e:\n"
        "    print(f\"(auth_check raised: {_e})\")\n"
        "check(_up,\n"
        "      \"Langfuse reachable. If not, start it: docker compose \"\n"
        "      \"-f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml up -d \"\n"
        "      \"(and set LANGFUSE_MODE=local in .env)\")"
    ),
    code(
        "def answer(prompt):\n"
        "    \"\"\"One plain-text model call. Flattens providers that return content blocks.\"\"\"\n"
        "    c = CHAT.invoke(prompt).content\n"
        "    if isinstance(c, list):\n"
        "        c = \"\".join(p.get(\"text\", \"\") if isinstance(p, dict) else str(p) for p in c)\n"
        "    return c\n"
        "\n"
        "ok(\"helpers ready\")"
    ),
]

# --------------------------------------------------------------------------
# Section: the shared eval harness
# --------------------------------------------------------------------------
HARNESS = [
    md(
        "## 1 · The eval harness, once\n\n"
        "`run_eval` is the whole Langfuse integration in one place: create a dataset, upsert\n"
        "its items (stable ids, so re-runs don't duplicate), then `run_experiment` - which\n"
        "creates a linked dataset **run**, executes the `task` per item inside its own trace,\n"
        "and attaches each `Evaluation` the `score` function returns. Aggregates for the\n"
        "`check(...)` are computed locally from the same per-item results; `HARNESS_EVAL`\n"
        "keeps them so the run is inspectable without opening the UI."
    ),
    code(
        "with conn.cursor() as cur:\n"
        "    try:\n"
        "        cur.execute(\"\"\"CREATE TABLE HARNESS_EVAL (\n"
        "            eval_name   VARCHAR2(60),\n"
        "            metric      VARCHAR2(60),\n"
        "            value       NUMBER,\n"
        "            detail      CLOB,\n"
        "            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
        "            CONSTRAINT harness_eval_pk PRIMARY KEY (eval_name, metric))\"\"\")\n"
        "    except Exception as e:\n"
        "        if \"ORA-00955\" not in str(e):\n"
        "            raise\n"
        "\n"
        "\n"
        "def record_eval(eval_name, metric, value, detail=\"\"):\n"
        "    with conn.cursor() as cur:\n"
        "        cur.execute(\"DELETE FROM HARNESS_EVAL WHERE eval_name = :1 AND metric = :2\",\n"
        "                    (eval_name, metric))\n"
        "        cur.execute(\"INSERT INTO HARNESS_EVAL (eval_name, metric, value, detail) \"\n"
        "                    \"VALUES (:1, :2, :3, :4)\", (eval_name, metric, float(value), detail))\n"
        "    conn.commit()\n"
        "\n"
        "\n"
        "def run_eval(name, items, task, score, max_concurrency=3):\n"
        "    \"\"\"Create a Langfuse dataset from `items` and run `task`/`score` over it.\n"
        "    Returns the ExperimentResult; read res.item_results for per-item output+scores.\"\"\"\n"
        "    try:\n"
        "        lf.create_dataset(name=name)\n"
        "    except Exception:\n"
        "        pass  # already exists - datasets are keyed by name\n"
        "    for it in items:\n"
        "        lf.create_dataset_item(dataset_name=name, id=it[\"id\"], input=it[\"input\"],\n"
        "                               expected_output=it.get(\"expected_output\"),\n"
        "                               metadata=it.get(\"metadata\"))\n"
        "    ds = lf.get_dataset(name)\n"
        "    res = ds.run_experiment(name=name, task=task, evaluators=[score],\n"
        "                            max_concurrency=max_concurrency)\n"
        "    lf.flush()\n"
        "    print(f\"  dataset run: {res.dataset_run_url}\")\n"
        "    return res\n"
        "\n"
        "ok(\"eval harness ready\")"
    ),
]

# --------------------------------------------------------------------------
# Eval 1: promotion precision
# --------------------------------------------------------------------------
EVAL_PROMOTION = [
    md(
        "## 2 · Eval 1 - Promotion precision\n\n"
        "A labelled corpus: genuine keepers filed in `/inbox`, an abandoned draft *also* in\n"
        "`/inbox` (path-legal but junk - only the LLM triage can catch it), and working\n"
        "files outside the inbox (caught by the path gate alone). The gate admits a note\n"
        "only if `promote.triage_allowed(path)` **and** the triage LLM says keep. We score\n"
        "precision and recall against the `signal`/`junk` labels - admitting junk costs\n"
        "precision, dropping signal costs recall."
    ),
    code(
        "CORPUS = [\n"
        "    (\"/inbox/Harbor Bridge/a.md\", \"Pier 3 bearing plate shows through-section corrosion; \"\n"
        "     \"flagged for Q3 rehabilitation with load restriction in the interim.\", \"signal\"),\n"
        "    (\"/inbox/Harbor Bridge/b.md\", \"Deck joint at pier 6 sealed and re-tested; movement \"\n"
        "     \"within spec. Closed.\", \"signal\"),\n"
        "    (\"/inbox/Riverside Culvert/c.md\", \"Invert scour measured at 40mm against 25mm design; \"\n"
        "     \"scheduled for grout repair next window.\", \"signal\"),\n"
        "    (\"/inbox/North Span/d.md\", \"Cathodic protection reading nominal across all test \"\n"
        "     \"stations this cycle.\", \"signal\"),\n"
        "    (\"/inbox/scratch/e.md\", \"todo: ask maria if the pier numbering starts at the north \"\n"
        "     \"or south abutment?? not sure. delete this later\", \"junk\"),\n"
        "    (\"/inbox/scratch/f.md\", \"asdf test test ignore\", \"junk\"),\n"
        "    (\"/work/attempt1.sql\", \"SELECT * FROM findings WHERE -- wrong, rewrite\", \"junk\"),\n"
        "    (\"/tool_out/dump.json\", \"[{\\\"a\\\":1},{\\\"a\\\":2}, ...]\", \"junk\"),\n"
        "]\n"
        "\n"
        "\n"
        "class KeepDiscard(BaseModel):\n"
        "    keep: bool = Field(description=\"true if a durable, completed fact worth long-term \"\n"
        "                                   \"memory; false if a draft, question, or scratch\")\n"
        "\n"
        "\n"
        "_triage = CHAT.with_structured_output(KeepDiscard)\n"
        "\n"
        "\n"
        "def _admit(path, content):\n"
        "    if not promote.triage_allowed(path):\n"
        "        return False           # path gate - no LLM needed\n"
        "    verdict = _triage.invoke(\n"
        "        \"Is this inspection note a durable, completed observation worth promoting to \"\n"
        "        f\"long-term memory?\\n\\nNOTE ({path}):\\n{content}\")\n"
        "    return verdict.keep\n"
        "\n"
        "\n"
        "def promo_task(*, item, **kwargs):\n"
        "    return {\"admitted\": _admit(item.input[\"path\"], item.input[\"content\"])}\n"
        "\n"
        "\n"
        "def promo_score(*, input, output, expected_output, metadata, **kwargs):\n"
        "    correct = output[\"admitted\"] == (expected_output[\"label\"] == \"signal\")\n"
        "    return Evaluation(name=\"admitted_correctly\", value=1.0 if correct else 0.0,\n"
        "                      comment=f\"admitted={output['admitted']} label={expected_output['label']}\")\n"
        "\n"
        "\n"
        "items = [{\"id\": p, \"input\": {\"path\": p, \"content\": c},\n"
        "          \"expected_output\": {\"label\": lbl}, \"metadata\": {\"label\": lbl}}\n"
        "         for p, c, lbl in CORPUS]\n"
        "res1 = run_eval(\"promotion-precision\", items, promo_task, promo_score)"
    ),
    code(
        "predicted = {r.item.input[\"path\"] for r in res1.item_results if r.output[\"admitted\"]}\n"
        "positives = {r.item.input[\"path\"] for r in res1.item_results\n"
        "             if r.item.expected_output[\"label\"] == \"signal\"}\n"
        "# ✏️ TODO(1): score the gate with evals.classification_metrics(predicted, positives).\n"
        "# TODO-SOLUTION-START\n"
        "m = evals.classification_metrics(predicted, positives)\n"
        "# TODO-SOLUTION-END\n"
        "print(f\"precision={m['precision']:.2f} recall={m['recall']:.2f} f1={m['f1']:.2f} \"\n"
        "      f\"(tp={m['tp']} fp={m['fp']} fn={m['fn']})\")\n"
        "record_eval(\"promotion-precision\", \"precision\", m[\"precision\"], json.dumps(m))\n"
        "record_eval(\"promotion-precision\", \"recall\", m[\"recall\"], json.dumps(m))\n"
        "check(m[\"precision\"] >= 0.8 and m[\"recall\"] >= 0.8,\n"
        "      f\"triage gate admits the right notes (precision {m['precision']:.0%}, \"\n"
        "      f\"recall {m['recall']:.0%})\")"
    ),
]

# --------------------------------------------------------------------------
# Eval 2: skill fidelity
# --------------------------------------------------------------------------
EVAL_SKILL = [
    md(
        "## 3 · Eval 2 - Skill fidelity\n\n"
        "A distilled skill is only trustworthy if its steps match what actually ran. We take\n"
        "trajectories and their distilled skills and have an LLM judge score faithfulness in\n"
        "[0,1]. Three are honestly distilled; one is **tampered** - a fabricated step spliced\n"
        "in. The pass bar is a high mean on the honest ones; the tampered item is the control\n"
        "that proves the judge is not a rubber stamp."
    ),
    code(
        "TRAJ_A = [\n"
        "    {\"tool\": \"tool_find_similar_findings\", \"args\": {\"description\": \"deck corrosion\"},\n"
        "     \"result\": \"3 hits incl F-1002 (high)\"},\n"
        "    {\"tool\": \"tool_log_finding\", \"args\": {\"asset_id\": \"Harbor Bridge\", \"severity\": \"high\"},\n"
        "     \"result\": \"created F-2210\"},\n"
        "]\n"
        "TRAJ_B = [\n"
        "    {\"tool\": \"tool_get_asset\", \"args\": {\"asset_id\": \"North Span\"}, \"result\": \"class=bridge\"},\n"
        "    {\"tool\": \"tool_find_similar_findings\", \"args\": {\"description\": \"cathodic reading\"},\n"
        "     \"result\": \"1 hit F-1500\"},\n"
        "]\n"
        "\n"
        "\n"
        "def _skill_from(traj, name, when, steps):\n"
        "    return improve.render_skill_md(name=name, description=when, tools=[s[\"tool\"] for s in traj],\n"
        "                                   when_to_use=when, steps_body=steps,\n"
        "                                   source_workflow_id=\"wf-\" + name, schema_sha=\"deadbeef\")\n"
        "\n"
        "\n"
        "FAITHFUL_STEPS = \"1. Search similar findings first.\\n2. Log the new finding citing severity.\"\n"
        "SKILLS = [\n"
        "    (TRAJ_A, _skill_from(TRAJ_A, \"log-corrosion\", \"recurring corrosion logging\",\n"
        "                          FAITHFUL_STEPS), True),\n"
        "    (TRAJ_B, _skill_from(TRAJ_B, \"check-cathodic\", \"cathodic protection check\",\n"
        "                          \"1. Look up the asset.\\n2. Search prior cathodic readings.\"), True),\n"
        "    (TRAJ_A, _skill_from(TRAJ_A, \"log-corrosion-2\", \"recurring corrosion logging\",\n"
        "                          FAITHFUL_STEPS), True),\n"
        "    # tampered: claims an approval step that never happened in the trajectory\n"
        "    (TRAJ_A, _skill_from(TRAJ_A, \"log-corrosion-bad\", \"recurring corrosion logging\",\n"
        "                          \"1. Search similar findings.\\n2. Email the district engineer for \"\n"
        "                          \"sign-off.\\n3. Log the finding.\"), False),\n"
        "]\n"
        "\n"
        "\n"
        "class Faithfulness(BaseModel):\n"
        "    score: float = Field(description=\"0..1: fraction of the skill's steps grounded in \"\n"
        "                                     \"the trajectory; penalise invented steps\")\n"
        "\n"
        "\n"
        "_judge = CHAT.with_structured_output(Faithfulness)\n"
        "\n"
        "\n"
        "def skill_task(*, item, **kwargs):\n"
        "    v = _judge.invoke(\n"
        "        \"Score how faithfully the skill's steps reflect what the trajectory actually \"\n"
        "        \"did. Invented steps lower the score.\\n\\nTRAJECTORY:\\n\"\n"
        "        + item.input[\"trajectory\"] + \"\\n\\nSKILL:\\n\" + item.input[\"skill\"])\n"
        "    return {\"faithfulness\": max(0.0, min(1.0, v.score))}\n"
        "\n"
        "\n"
        "def skill_score(*, input, output, expected_output, metadata, **kwargs):\n"
        "    return Evaluation(name=\"faithfulness\", value=output[\"faithfulness\"])\n"
        "\n"
        "\n"
        "items = [{\"id\": f\"skill-{i}\",\n"
        "          \"input\": {\"trajectory\": improve.trajectory_to_text(t), \"skill\": s},\n"
        "          \"metadata\": {\"faithful\": faithful}}\n"
        "         for i, (t, s, faithful) in enumerate(SKILLS)]\n"
        "res2 = run_eval(\"skill-fidelity\", items, skill_task, skill_score)"
    ),
    code(
        "honest = [r.output[\"faithfulness\"] for r in res2.item_results if r.item.metadata[\"faithful\"]]\n"
        "tampered = [r.output[\"faithfulness\"] for r in res2.item_results\n"
        "            if not r.item.metadata[\"faithful\"]]\n"
        "# ✏️ TODO(2): aggregate the honest scores with evals.mean_stdev.\n"
        "# TODO-SOLUTION-START\n"
        "mean, stdev = evals.mean_stdev(honest)\n"
        "# TODO-SOLUTION-END\n"
        "print(f\"honest skills: mean faithfulness {mean:.2f} +/- {stdev:.2f}\")\n"
        "print(f\"tampered skill: {tampered[0]:.2f} (should be well below the honest mean)\")\n"
        "record_eval(\"skill-fidelity\", \"mean_faithfulness\", mean,\n"
        "            json.dumps({\"honest\": honest, \"tampered\": tampered}))\n"
        "check(mean >= 0.8, f\"distilled skills are faithful to their trajectories (mean {mean:.0%})\")\n"
        "check(tampered[0] < mean, \"the judge catches a fabricated step (control)\")"
    ),
]

# --------------------------------------------------------------------------
# Eval 3: skills-help
# --------------------------------------------------------------------------
EVAL_SKILLS_HELP = [
    md(
        "## 4 · Eval 3 - Skills-help (the missing experiment)\n\n"
        "The review's sharpest omission: nobody checked whether harvesting skills *helps*.\n"
        "Here each held-out task variant is run twice - **with** the harvested procedure in\n"
        "context and **without** it - and success is scored by an LLM judge, not `bool(final)`.\n"
        "The skill encodes a mandatory logging format (cite a prior finding_id, use a valid\n"
        "severity); without it, the model tends to answer free-form and miss the contract."
    ),
    code(
        "SKILL_MANIFEST = (\n"
        "    \"MANDATORY logging procedure: when recording a finding you MUST (a) cite one \"\n"
        "    \"relevant prior finding_id from the provided context, and (b) state severity as \"\n"
        "    \"exactly one of low/medium/high.\")\n"
        "\n"
        "PRIORS = \"Prior findings: F-1002 (deck corrosion, high); F-1500 (cathodic, low); \" \\\n"
        "         \"F-1777 (joint wear, medium).\"\n"
        "\n"
        "VARIANTS = [\n"
        "    \"Record that girder G-11 near pier 3 has a new hairline weld crack.\",\n"
        "    \"Note accelerated corrosion on the deck underside over pier 3.\",\n"
        "    \"Log that bearing pad at pier 6 shows 3mm vertical cracking.\",\n"
        "]\n"
        "\n"
        "\n"
        "def _agent(task_text, use_skill):\n"
        "    sys = \"You are the CityOps inspection copilot.\\n\" + PRIORS + \"\\n\"\n"
        "    if use_skill:\n"
        "        sys += SKILL_MANIFEST + \"\\n\"\n"
        "    return answer(sys + \"\\nTASK: \" + task_text + \"\\nWrite the finding record.\")\n"
        "\n"
        "\n"
        "class Success(BaseModel):\n"
        "    ok: bool = Field(description=\"true only if the record cites a prior finding_id AND \"\n"
        "                                 \"states severity as low, medium, or high\")\n"
        "\n"
        "\n"
        "_success = CHAT.with_structured_output(Success)\n"
        "\n"
        "\n"
        "def help_task(*, item, **kwargs):\n"
        "    text = _agent(item.input[\"task\"], item.input[\"use_skill\"])\n"
        "    return {\"record\": text}\n"
        "\n"
        "\n"
        "def help_score(*, input, output, expected_output, metadata, **kwargs):\n"
        "    v = _success.invoke(\"Does this finding record cite a prior finding_id (like F-1002) \"\n"
        "                        \"and state a valid severity (low/medium/high)?\\n\\n\" + output[\"record\"])\n"
        "    return Evaluation(name=\"task_success\", value=1.0 if v.ok else 0.0)\n"
        "\n"
        "\n"
        "items = []\n"
        "for i, v in enumerate(VARIANTS):\n"
        "    for arm in (True, False):\n"
        "        items.append({\"id\": f\"help-{i}-{'with' if arm else 'without'}\",\n"
        "                      \"input\": {\"task\": v, \"use_skill\": arm},\n"
        "                      \"metadata\": {\"arm\": \"with\" if arm else \"without\"}})\n"
        "res3 = run_eval(\"skills-help\", items, help_task, help_score, max_concurrency=2)"
    ),
    code(
        "def _rate(arm):\n"
        "    vals = [r.evaluations[0].value for r in res3.item_results if r.item.metadata[\"arm\"] == arm]\n"
        "    return sum(vals) / len(vals) if vals else 0.0\n"
        "\n"
        "\n"
        "with_skill, without_skill = _rate(\"with\"), _rate(\"without\")\n"
        "# ✏️ TODO(3): compare the two arms - skills should not hurt, and both must be scored.\n"
        "# TODO-SOLUTION-START\n"
        "helped = with_skill >= without_skill and (len(VARIANTS) > 0)\n"
        "# TODO-SOLUTION-END\n"
        "print(f\"success with skills: {with_skill:.0%}   without: {without_skill:.0%}\")\n"
        "record_eval(\"skills-help\", \"success_with\", with_skill)\n"
        "record_eval(\"skills-help\", \"success_without\", without_skill,\n"
        "            json.dumps({\"delta\": with_skill - without_skill}))\n"
        "check(helped, f\"harvested skills do not hurt success (with {with_skill:.0%} \"\n"
        "      f\">= without {without_skill:.0%})\")"
    ),
    md(
        "**Honest caveat.** Three variants is *directional*, not powered - the point is the\n"
        "experiment shape (paired arms, judge-scored, delta reported), which the original\n"
        "suite lacked entirely. A real run repeats each arm many times and reports the\n"
        "confidence interval on the delta, exactly as eval 5 treats cost below."
    ),
]

# --------------------------------------------------------------------------
# Eval 4 + 5 share a season; build it once
# --------------------------------------------------------------------------
SEASON = [
    md(
        "## 5 · A spaced, multi-topic season (shared by evals 4 and 5)\n\n"
        "Four facts on four different assets, planted at increasing depth, then a compaction\n"
        "card built the notebook-03 way. Evals 4 and 5 both interrogate this one card."
    ),
    code(
        "PLANTED = {\n"
        "    2:  (\"g1\", \"Pier 3 of Harbor Bridge has through-section corrosion - the reason it \"\n"
        "               \"leads the Q3 list.\"),\n"
        "    8:  (\"g2\", \"Riverside Culvert was graded on the 2019 scale, so its grades are not \"\n"
        "               \"comparable with the rest.\"),\n"
        "    14: (\"g3\", \"North Span cathodic protection read nominal at every test station.\"),\n"
        "    20: (\"g4\", \"Inspector Okafor signed off all East Yard reports, a single-reviewer bias.\"),\n"
        "}\n"
        "FILLER = (\"Routine check on {a}: surface wear noted, within tolerance, no action.\")\n"
        "ASSETS = [\"West Viaduct\", \"Elm Overpass\", \"Dock Gantry\", \"Mill Footbridge\"]\n"
        "\n"
        "TURNS = []\n"
        "for n in range(1, 25):\n"
        "    if n in PLANTED:\n"
        "        fid, text = PLANTED[n]\n"
        "        TURNS.append((n, text, fid))\n"
        "    else:\n"
        "        TURNS.append((n, f\"Turn {n}: \" + FILLER.format(a=ASSETS[n % len(ASSETS)]), None))\n"
        "\n"
        "PLANTED_IDS = [fid for _, _, fid in TURNS if fid]\n"
        "print(f\"{len(TURNS)} turns, {len(PLANTED_IDS)} planted facts at depths {list(PLANTED)}\")"
    ),
    code(
        "COMPACT_PROMPT = (\n"
        "    \"Maintain a compaction card. Return ONLY JSON with keys facts, decisions, \"\n"
        "    \"open_questions. facts is a list of {{id,text,turn}}; reuse an id to correct it, \"\n"
        "    \"invent g5+ otherwise. Keep anything needed in three months.\\n\\n\"\n"
        "    \"CARD:\\n{card}\\n\\nNEW TURNS:\\n{turns}\")\n"
        "\n"
        "\n"
        "def _compact(card, pending):\n"
        "    raw = answer(COMPACT_PROMPT.format(card=context.render_card(card),\n"
        "                 turns=\"\\n\".join(f\"[{n}] {t}\" for n, t, _ in pending))).strip()\n"
        "    if raw.startswith(\"```\"):\n"
        "        raw = raw.split(\"```\")[1].removeprefix(\"json\").strip()\n"
        "    return context.merge_card(card, context.parse_card(raw))\n"
        "\n"
        "\n"
        "CARD = {\"facts\": [], \"decisions\": [], \"open_questions\": []}\n"
        "TRANSCRIPT, pending = \"\", []\n"
        "for turn in TURNS:\n"
        "    pending.append(turn)\n"
        "    TRANSCRIPT += turn[1] + \"\\n\"\n"
        "    if context.compaction_due(sum(len(t[1]) for t in pending), 1200):\n"
        "        CARD = _compact(CARD, pending); pending = []\n"
        "if pending:\n"
        "    CARD = _compact(CARD, pending)\n"
        "print(f\"card holds {len(CARD['facts'])} facts after the season\")"
    ),
]

EVAL_CARD = [
    md(
        "## 6 · Eval 4 - Card fidelity over a horizon\n\n"
        "Structural recall first (`context.card_fidelity`: did the fact id survive), then a\n"
        "per-fact functional probe as the dataset. A card that stayed small by dropping the\n"
        "turn-2 fact fails here - which is the whole point the size chart could not make."
    ),
    code(
        "PROBES = {\n"
        "    \"g1\": (\"Which pier leads the Q3 list and why?\", \"pier 3\"),\n"
        "    \"g2\": (\"Which inspection's grades are not comparable, and why?\", \"2019\"),\n"
        "    \"g3\": (\"What did North Span's cathodic protection read?\", \"nominal\"),\n"
        "    \"g4\": (\"Whose sign-off carries a single-reviewer bias, and where?\", \"okafor\"),\n"
        "}\n"
        "CARD_TEXT = context.render_card(CARD)\n"
        "# Structural = is the fact physically in the card. We match on content, not id:\n"
        "# the compaction model mints its own fact ids when folding, so id-equality\n"
        "# (context.card_fidelity) understates a card that kept the fact under a new id.\n"
        "_struct = {fid: (needle.lower() in CARD_TEXT.lower()) for fid, (_, needle) in PROBES.items()}\n"
        "struct_recall = sum(_struct.values()) / len(_struct)\n"
        "print(f\"structural recall {struct_recall:.0%}  \"\n"
        "      + \", \".join(f\"{k}={'in' if v else 'GONE'}\" for k, v in _struct.items()))\n"
        "\n"
        "\n"
        "def card_task(*, item, **kwargs):\n"
        "    q = item.input[\"question\"]\n"
        "    a = answer(\"Answer using ONLY this card; if absent say NOT IN CARD.\\n\\n\"\n"
        "               + CARD_TEXT + \"\\n\\nQ: \" + q)\n"
        "    return {\"answer\": a}\n"
        "\n"
        "\n"
        "def card_score(*, input, output, expected_output, metadata, **kwargs):\n"
        "    hit = expected_output[\"needle\"].lower() in output[\"answer\"].lower()\n"
        "    return Evaluation(name=\"fact_recalled\", value=1.0 if hit else 0.0)\n"
        "\n"
        "\n"
        "_depth_of = {fid: d for d, (fid, _) in PLANTED.items()}\n"
        "items = [{\"id\": fid, \"input\": {\"question\": q},\n"
        "          \"expected_output\": {\"needle\": needle}, \"metadata\": {\"depth\": _depth_of[fid]}}\n"
        "         for fid, (q, needle) in PROBES.items()]\n"
        "res4 = run_eval(\"card-fidelity\", items, card_task, card_score)"
    ),
    code(
        "func = {r.item.id: r.evaluations[0].value for r in res4.item_results}\n"
        "# ✏️ TODO(4): functional recall = mean of the per-probe hits.\n"
        "# TODO-SOLUTION-START\n"
        "func_recall = sum(func.values()) / len(func)\n"
        "# TODO-SOLUTION-END\n"
        "print(f\"functional recall {func_recall:.0%}: \"\n"
        "      + \", \".join(f\"{k}={'hit' if v else 'MISS'}\" for k, v in func.items()))\n"
        "record_eval(\"card-fidelity\", \"structural_recall\", struct_recall)\n"
        "record_eval(\"card-fidelity\", \"functional_recall\", func_recall, json.dumps(func))\n"
        "\n"
        "fig, ax = plt.subplots(figsize=(6, 3))\n"
        "ax.bar([f\"{k}@t{_depth_of[k]}\" for k in func], list(func.values()),\n"
        "       color=[\"#1a7f37\" if v else \"#cf222e\" for v in func.values()])\n"
        "ax.set_xlabel(\"planted fact @ turn\"); ax.set_ylabel(\"recalled (1/0)\")\n"
        "ax.set_title(\"Card fidelity by planting depth\"); ax.set_ylim(0, 1.1)\n"
        "plt.tight_layout(); plt.show()\n"
        "check(func_recall >= 0.6, f\"card retains facts across the horizon ({func_recall:.0%})\")"
    ),
]

EVAL_COST = [
    md(
        "## 7 · Eval 5 - Cost per correct answer\n\n"
        "The same questions answered three ways - from the **card**, from the **full\n"
        "transcript**, and **stateless** - each repeated for variance. Cost is a token proxy\n"
        "(`len(context)//4`). The claim compaction has to earn: the card answers correctly\n"
        "for *fewer tokens per correct answer* than shipping the whole transcript."
    ),
    code(
        "REPEATS = 2\n"
        "COST_Q = {\"g1\": (\"Which pier leads the Q3 list and why?\", \"pier 3\"),\n"
        "          \"g3\": (\"What did North Span's cathodic protection read?\", \"nominal\")}\n"
        "CONTEXTS = {\"card\": CARD_TEXT, \"transcript\": TRANSCRIPT, \"stateless\": \"\"}\n"
        "\n"
        "\n"
        "def cost_task(*, item, **kwargs):\n"
        "    ctx = CONTEXTS[item.input[\"condition\"]]\n"
        "    q = item.input[\"question\"]\n"
        "    prompt = (f\"Answer using ONLY this context; if absent say NOT IN CONTEXT.\\n\\n\"\n"
        "              f\"{ctx}\\n\\nQ: {q}\") if ctx else f\"Answer if you can, else NOT IN CONTEXT.\\n\\nQ: {q}\"\n"
        "    a = answer(prompt)\n"
        "    return {\"answer\": a, \"cost\": len(prompt) // 4,\n"
        "            \"correct\": item.input[\"needle\"].lower() in a.lower()}\n"
        "\n"
        "\n"
        "def cost_score(*, input, output, expected_output, metadata, **kwargs):\n"
        "    return Evaluation(name=\"correct\", value=1.0 if output[\"correct\"] else 0.0)\n"
        "\n"
        "\n"
        "items = []\n"
        "for cond in CONTEXTS:\n"
        "    for fid, (q, needle) in COST_Q.items():\n"
        "        for rep in range(REPEATS):\n"
        "            items.append({\"id\": f\"cost-{cond}-{fid}-{rep}\",\n"
        "                          \"input\": {\"condition\": cond, \"question\": q, \"needle\": needle},\n"
        "                          \"metadata\": {\"condition\": cond}})\n"
        "res5 = run_eval(\"cost-per-correct\", items, cost_task, cost_score, max_concurrency=2)"
    ),
    code(
        "by_cond = {}\n"
        "for r in res5.item_results:\n"
        "    c = r.item.metadata[\"condition\"]\n"
        "    by_cond.setdefault(c, {\"costs\": [], \"correct\": []})\n"
        "    by_cond[c][\"costs\"].append(r.output[\"cost\"])\n"
        "    by_cond[c][\"correct\"].append(bool(r.output[\"correct\"]))\n"
        "\n"
        "# ✏️ TODO(5): summarise each condition with evals.summarize_trials(costs, correct).\n"
        "summary = {}\n"
        "# TODO-SOLUTION-START\n"
        "for c, d in by_cond.items():\n"
        "    summary[c] = evals.summarize_trials(d[\"costs\"], d[\"correct\"])\n"
        "# TODO-SOLUTION-END\n"
        "for c, s in summary.items():\n"
        "    cpc = s[\"cost_per_correct\"]\n"
        "    print(f\"  {c:>10}: acc={s['accuracy']:.0%} cost/correct=\"\n"
        "          f\"{cpc if cpc is None else round(cpc,1)} (n={s['n']})\")\n"
        "    record_eval(\"cost-per-correct\", f\"{c}_cost_per_correct\",\n"
        "                cpc if cpc is not None else -1.0, json.dumps(s))\n"
        "\n"
        "card_cpc, tx_cpc = summary[\"card\"][\"cost_per_correct\"], summary[\"transcript\"][\"cost_per_correct\"]\n"
        "labels = list(summary)\n"
        "vals = [summary[c][\"cost_per_correct\"] or 0 for c in labels]\n"
        "fig, ax = plt.subplots(figsize=(6, 3))\n"
        "ax.bar(labels, vals, color=\"#0969da\")\n"
        "ax.set_ylabel(\"tokens per correct answer\"); ax.set_title(\"Cost per correct (lower is better)\")\n"
        "plt.tight_layout(); plt.show()\n"
        "check(card_cpc is not None and tx_cpc is not None and card_cpc <= tx_cpc,\n"
        "      f\"the card is cheaper per correct answer than the full transcript \"\n"
        "      f\"({round(card_cpc,1)} vs {round(tx_cpc,1)} tokens)\")"
    ),
]

# --------------------------------------------------------------------------
# Section: closing
# --------------------------------------------------------------------------
CLOSING = [
    md(
        "## 8 · What these five measured\n\n"
        "| Eval | Result lives in | Under-powered where |\n"
        "|---|---|---|\n"
        "| Promotion precision | `HARNESS_EVAL` + Langfuse `promotion-precision` | 8-note corpus |\n"
        "| Skill fidelity | `skill-fidelity` | single tampered control |\n"
        "| Skills-help | `skills-help` | 3 variants, 1 repeat |\n"
        "| Card fidelity | `card-fidelity` | one season, 4 facts |\n"
        "| Cost per correct | `cost-per-correct` | 2 questions x 2 repeats |\n\n"
        "Every one is a *shape* a real harness scales up - more items, more repeats, a\n"
        "confidence interval on each number. The point was to make the claim falsifiable and\n"
        "put the score next to the trace that produced it.\n\n"
        "The natural next build is the deferred **strength-based card consolidation** (design\n"
        "spec): eval 4 is exactly the instrument that would grade whether a card that finally\n"
        "*forgets* keeps the facts that matter. Stop the Langfuse stack when you're done with\n"
        "`docker compose -f docker-compose.langfuse.yml -f docker-compose.langfuse.override.yml down`."
    ),
    code(
        "for desc, passed in verify(conn, \"04_evals\"):\n"
        "    check(passed, desc)\n"
        "ok(\"evals complete - the harness measures what it claimed to fix\")"
    ),
]

SECTIONS = [INTRO, SETUP, HARNESS, EVAL_PROMOTION, EVAL_SKILL, EVAL_SKILLS_HELP,
            SEASON, EVAL_CARD, EVAL_COST, CLOSING]


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
    nbf.write(build(), "notebooks/04_evals_complete.ipynb")
    print("wrote notebooks/04_evals_complete.ipynb")
