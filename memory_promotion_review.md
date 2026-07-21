# Total Recall — Memory Promotion: Design Review

A critical review of the two memory-promotion mechanisms in `total_recall_complete.ipynb`, and of the
evaluations the notebook uses to justify them. The core finding: **both promotion paths are architecturally
sound demonstrations whose feedback loops are stubbed with proxies** — promotion without curation, success
without verification, growth without forgetting. Each proxy is harmless in a demo and a slow leak over a long
horizon.

---

## Path 1: Scratch → Long-Term Memory (Part 4.5)

### The design

The scratchpad (a SecureFile-LOB table posing as a POSIX filesystem, Part 2) is where the agent jots freely.
Promotion moves worth-keeping notes into OAMP long-term memory, where they become embedded, indexed, and
searchable by meaning. The pipeline is split along a natural seam:

```
agent_scratch (promoted='N')
      │
      ▼  DBMS_SCHEDULER job, hourly — runs entirely in the database
stage_scratch_for_promotion        UTL_TO_TEXT → UTL_TO_CHUNKS → INSERT
      │                            marks file promoted='S' (staged)
      ▼
promotion_queue (consumed='N')
      │
      ▼  drain_promotion_queue_to_oamp() — runs in the harness
mem.remember(chunk)                OAMP add_memory, extraction applies
                                   marks file promoted='Y'
```

The notebook's framing is exactly right on paper: *"Promotion is the valve between them, the mechanism that
decides **what graduates**."* Short-term memory is cheap to write and safe to be wrong in; long-term memory
must stay curated because everything in it competes for retrieval attention.

### Where it falls short

#### 1. The valve has no filter — everything graduates

The producer's only predicate is *not yet promoted*:

```sql
FOR f IN (SELECT path, content FROM agent_scratch WHERE promoted='N' AND is_dir='N') LOOP
```

There is no quality gate, no worth-keeping signal, no opt-in marker (e.g., only promote `/inbox`), no
size/age filter. Every scratch file is chunked and pushed into long-term memory within an hour.

**Example.** During a task the agent writes three files:

| File | What it is | What promotion does with it |
|---|---|---|
| `/work/attempt1_wrong.sql` | A query that returned wrong numbers; agent abandoned it | Chunked and embedded into durable memory |
| `/work/draft_notes.md` | "TODO: check if revenue includes refunds?? probably not" | Chunked and embedded into durable memory |
| `/inbox/supplier_note.md` | "Northwind supplies 40% of Outdoors COGS" | Chunked and embedded into durable memory |

Only the third deserves to graduate. But an hour later, a recall for *"revenue calculation"* can surface the
abandoned wrong query and the speculative TODO **as durable memories**, ranked purely by cosine similarity,
indistinguishable from vetted facts. This destroys the scratchpad's own contract — it is no longer "safe to
be wrong in" because everything written there becomes permanent within the hour. The notebook names the
failure mode itself ("everything stored there competes for retrieval attention later") and then ships a
pipeline that guarantees it.

#### 2. The consumer half is never actually scheduled

The producer is a real `DBMS_SCHEDULER` job that survives client disconnects. The consumer
(`drain_promotion_queue_to_oamp`) runs in the Python harness and is only ever invoked **manually** in the
notebook; the text says *"you schedule it from your orchestrator"* and moves on. In a real deployment, the
moment the harness process is gone, `promotion_queue` fills indefinitely while nothing reaches long-term
memory — the pipeline silently half-works, which is worse than visibly failing.

#### 3. Nothing ever forgets, and nothing supersedes

There is no decay, TTL, consolidation, or contradiction resolution anywhere in the path.

**Example.** Q3: the agent promotes *"Northwind supplies 40% of Outdoors COGS."* Q1 next year, after the
dual-sourcing effort the notebook's own demo scenario is about succeeds: *"Northwind now supplies 20%."* Both
facts live in the store forever with no recency weighting and no supersession link. A recall for *"supplier
concentration"* returns whichever is cosine-nearer to the query phrasing — over a long horizon, the store
becomes an archaeology site where every stratum answers with equal confidence.

#### 4. Double-extraction compounds the noise

`mem.remember` routes through OAMP with extraction enabled, so promoted chunks are *re-interpreted* by the
LLM at ingest. Chunks are 200-word windows cut mid-document; extracting "facts" from a window that begins
mid-sentence invites confident misreadings — and there is no provenance kept (which file, which revision),
so a bad extraction can never be traced back or invalidated when the source file changes.

---

## Path 2: Workflow → Skill (Parts 6.4–6.5)

### The design

Every `run_agent` call captures a workflow (intent, steps, tools, outcome) into `agent_workflow`, deduping
near-identical intents by embedding distance and accumulating `occurrences` / `successes` / `failures`. The
harvester then promotes only what **recurs and works**:

```python
HARVEST_KNOBS = {"min_occurrences": 3, "recency_days": 30}
# promote iff: promoted='N' AND occurrences >= 3 AND recent AND successes > failures
```

`promote_workflow_to_skill` has the LLM distil the workflow into a `SKILL.md` (frontmatter + When-to-use +
Steps), stores it SHA-versioned in the skillbox, and retires the raw recipe (`promoted='Y'`) so recall never
spends attention on both. In Part 7, retrieved skills are injected **first in the system prompt, labelled as
approved procedures the agent should prefer** — the whole point is that a skill carries more inference-time
weight than the episodic history it came from.

This gating idea — *recurring AND recent AND reliable* — is the right instinct. The problem is that every
input to the gate is a proxy that doesn't measure what it claims.

### Where it falls short

#### 1. The captured trajectory is nearly information-free

What `run_agent` actually records (cell 176):

```python
tools_used = sorted({c["name"] for m in out["messages"] for c in (getattr(m, "tool_calls", None) or [])})
mem.capture_workflow(text, [{"tool": t} for t in tools_used], tools_used, success=bool(final))
```

A **sorted set of tool names**. No arguments, no ordering, no intermediate results, no reasoning. So when
promotion asks the LLM to *"distil numbered, parameterised steps"* from:

```
Intent: compute revenue by product category for last 90 days
Steps:  [{"tool": "run_sql"}]
Tools:  run_sql
```

…there is nothing to distil. The model **confabulates** a plausible steps body — which SQL to write, which
tables to join — none of it grounded in what actually ran. The notebook then injects that confabulation at
**maximum prompt authority**, telling the agent to prefer it over improvising. A fabricated procedure at high
authority is strictly worse than no procedure: improvisation at least reads the schema catalog fresh.

#### 2. "Success" means "produced prose," not "was correct"

```python
success=bool(final)   # final = any non-empty closing AIMessage
```

An agent that confidently returns a wrong revenue number three times satisfies `successes > failures` and
gets its workflow **enshrined as an approved skill**. Note the budget interaction: `node_finalize` exists
precisely to guarantee a closing answer even when the loop runs out of budget mid-task — so even a truncated,
partial run usually counts as a *success*. The harvester's reliability gate filters on a signal that is
almost always true.

#### 3. Intent-string dedup is brittle in both directions

Merging happens when the *intent embedding* is within cosine distance 0.15:

```python
if sims and sims[0]["D"] < 0.15:   # merge: occurrences += 1
```

- **Under-merge (nothing ever harvests):** *"revenue by category last 90 days"*, *"quarterly category revenue
  breakdown"*, and *"how did categories do this quarter"* are the same task, but paraphrase drift can keep
  each pair above 0.15 — three rows with `occurrences=1`, and the `min_occurrences=3` gate never fires. The
  long-horizon learning loop silently stalls.
- **Over-merge (counts pollute each other):** *"refunds by category last 90 days"* embeds close to the
  revenue intent but is a different computation. Its successes and failures now credit the wrong workflow,
  and the eventual skill is distilled from a chimera of two tasks.

Both failure modes get *worse* as the horizon grows, because both paraphrase diversity and near-neighbor
density increase with volume.

#### 4. Promotion is a one-way door with no lifecycle

`promoted='Y'` permanently retires the raw recipe from recall; the skill becomes the canonical version. But:

- **No demotion.** If the distilled skill is wrong (see #1), nothing detects it. Skill usage is never linked
  back to outcomes — there is no `skill_id` on captured workflows, so a skill that causes failures never
  accumulates evidence against itself.
- **No staleness handling.** The schema changes, the skill's SQL guidance rots, and it *still* gets injected
  as an approved procedure ahead of the fresh schema catalog.
- **No retrieval threshold.** `build_skill_manifest(query, 4)` returns the 4 nearest skills regardless of
  distance. Once the skillbox has a few dozen entries, every turn — relevant or not — gets its four nearest
  skills injected at top-of-prompt authority. On an off-topic query, that is four pieces of confident,
  authoritative noise.

**Compound example.** Turn 1: agent answers a revenue question with a subtly wrong join; `node_finalize`
closes it out → `success=True`. Turns 2–3: similar phrasing, same wrong path recalled as a "candidate
recipe" (self-reinforcing) → `occurrences=3, successes=3`. Harvester fires. The LLM distils a steps body
from a tool-name set, inventing details. Result: a **confabulated skill distilled from an unverified
trajectory, injected forever at the highest prompt authority, with the grounded raw recipe now retired and
no mechanism to ever demote it.** Every stage worked as designed; the composition is the failure.

---

## The evals: what each accomplishes, and the gap it leaves

The notebook is unusually honest about measuring its claims — but each measurement validates a *narrower*
claim than the prose around it suggests. None of them touch long-horizon behavior.

### TODO checks & part checkpoints (throughout)

**What they accomplish.** Functional smoke tests: promotion marks files `'Y'` (TODO 12), a `SKILL.md` is
written and the source workflow retired (TODO 17), the harvester returns a list (TODO 18), the checkpoint
recalls a promoted note by meaning (4.6). They prove the plumbing is connected end to end — genuinely
valuable for a workshop.

**The gap.** They assert *mechanism*, never *quality*. TODO 12 promotes a two-sentence file that is 100%
signal — the indiscriminate-promotion problem is invisible at n=1 file. TODO 17 checks that markdown with a
`##` exists, not that the skill's steps are faithful to the trajectory. TODO 18 accepts an empty list. All
checks pass identically on a system that would drown in noise at n=10,000 memories.

### 8.1 — Compaction, measured over 30 turns

**What it accomplishes.** Real numbers on a real mechanism: over a 30-turn scripted dialogue, the OAMP
context card stays bounded (~flat) while the raw transcript grows linearly. It honestly demonstrates the
*cost* half of compaction, with the card genuinely built by the LLM at checkpoints.

**The gap.** It measures **characters, not fidelity**. A card that summarized the dialogue *incorrectly*
would produce the identical green line. Rolling summaries compound loss — the summary of turn 60 is built on
the summary of turn 40 — and nothing here measures drift, which is precisely the long-horizon risk. Thirty
turns of one scripted conversation is also the short end of "long": no topic switches, no multi-session
resumption mid-plan, no adversarial spacing between when a fact appears and when it's needed.

### 8.2b — Offloading, measured

**What it accomplishes.** A 5,000-char tool result is replaced in context by a ~60-char reference and shown
to be fully recoverable via `fetch_tool_output`. Clean demonstration of the right pattern (pointer in
context, payload in storage), with a measured ~99% context reduction.

**The gap.** It never tests whether the *agent* recovers gracefully — i.e., a task where the model must
notice the reference, decide to fetch, and use the payload correctly across subsequent turns. The measured
claim is "the bytes are recoverable," but the operative claim is "the agent doesn't lose information it
later needs," which is untested. (Offloaded blobs also land in scratch under `/tool_out/`, where Path 1's
indiscriminate promotion will happily chunk raw tool dumps into long-term memory — an unmeasured interaction
between the two mechanisms.)

### 8.4 — Card vs. full transcript vs. no memory (LLM-as-judge)

**What it accomplishes.** The best-designed eval in the notebook: three strategies differ *only* in context
assembly, cost comes from real usage metadata, accuracy from a judge against ground truth computed
independently. It cleanly shows the card matches full-transcript accuracy at a fraction of the input tokens
and beats stateless. The claim "compaction holds cost down without losing accuracy" is genuinely supported —
*at this scale*.

**The gap.** Four turns, one seeded conversation, one run, one judge sample. Specifically:

- **All four questions are recall questions** answerable from the seeded dialogue — the regime where a
  summary+retrieval card is strongest. Long-horizon tasks fail differently: goal drift, mid-plan state loss,
  needing a detail the summarizer deemed irrelevant twenty turns ago. None of that is probed.
- **n=1, no variance.** A single LLM-judged scalar per strategy, no repeated trials, no confidence interval;
  the ±0.05 "won" tolerance at the end is doing a lot of quiet work.
- **It evaluates the card only** — neither promotion path is in the loop. The notebook's two *learning*
  mechanisms (the subject of the skepticism) are never evaluated for whether they improve task performance.
  There is no eval of the form: "agent with harvested skills vs. without, on held-out task variants" — which
  is the experiment that would actually test whether promotion helps.

### 9.1 — Continuity across sessions

**What it accomplishes.** Proves durable persistence with no model in the loop: a fact written in one
session is retrieved by a brand-new connection and client. The amnesiac problem — the baseline failure of
non-persistent agents — is genuinely solved.

**The gap.** Persistence-of-one-fact is the easy half of continuity. The hard half is *resuming work*: a new
session recovering the goal, the plan, what's done, and what's next. Nothing persists explicit plan/task
state (the card summarizes conversation, not intention), and the agent loop itself is capped at 8 iterations
/ 120 seconds — so any genuinely long task spans many sessions and leans entirely on the unmeasured part.

### Summary

| Eval | Validates | Silent on |
|---|---|---|
| TODO checks / checkpoints | Plumbing works end to end | Quality of what flows through it |
| 8.1 compaction curve | Context *size* stays bounded | Summary *fidelity* and drift over time |
| 8.2b offloading | Payloads recoverable, huge context savings | Whether the agent actually recovers what it needs |
| 8.4 card vs. full vs. none | Cost ↓ with accuracy held, over 4 recall turns | Long-horizon tasks; any effect of the promotion paths |
| 9.1 continuity | Facts persist across sessions | Resuming *work* (plan/goal state) across sessions |

---

## The through-line

Both promotion paths share one root defect: **the signals that gate graduation are proxies, and no loop ever
closes.** Path 1 graduates on *existence* (every file promotes). Path 2 graduates on *completion* (any prose
counts as success) and *recurrence of phrasing* (intent-string similarity). Nothing downstream ever feeds
back — no memory is ever demoted for being wrong, no skill for causing failures, no summary for drifting.
Every store grows monotonically while retrieval stays top-k with no relevance threshold.

Short-horizon, the stores are small and mostly signal, so everything looks great — and the evals, all
short-horizon, confirm it. Long-horizon, noise compounds in exactly the places the evals don't look:
retrieval precision decays as junk accumulates, stale facts contradict fresh ones, and confabulated skills
sit permanently at the top of the prompt. Closing the loops would mean: an explicit worth-keeping gate on
Path 1 (opt-in promotion, provenance, supersession links); verified outcomes and full-trajectory capture on
Path 2 (skill-usage tracking, trial periods, demotion); distance thresholds on every top-k injection; and an
eval that runs a multi-session task with and without the learned artifacts. That delta is the distance
between this notebook and a system you could trust on a week-long task.
