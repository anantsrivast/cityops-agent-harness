"""Pure decision logic for the self-improving harness (notebook 01).

Everything here is side-effect free so it can be unit-tested without a
database or an LLM. The notebook supplies the SQL and model calls.
"""

from __future__ import annotations

import hashlib
import json

_SKILL_TEMPLATE = """---
name: {name}
description: {description}
tools: {tools}
source_workflow: {source_workflow_id}
schema_sha: {schema_sha}
---

## When to use
{when_to_use}

## Steps
{steps_body}
"""


def render_skill_md(
    *,
    name: str,
    description: str,
    tools: list[str],
    when_to_use: str,
    steps_body: str,
    source_workflow_id: str,
    schema_sha: str,
) -> str:
    return _SKILL_TEMPLATE.format(
        name=name,
        description=description,
        tools=", ".join(tools),
        source_workflow_id=source_workflow_id,
        schema_sha=schema_sha,
        when_to_use=when_to_use.strip(),
        steps_body=steps_body.strip(),
    )


def parse_skill_md(text: str) -> dict:
    if not text.startswith("---"):
        raise ValueError("skill document missing frontmatter")
    try:
        _, front, body = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("skill document missing frontmatter close") from exc

    meta: dict = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    for required in ("name", "description", "tools", "source_workflow", "schema_sha"):
        if required not in meta:
            raise ValueError(f"skill frontmatter missing {required!r}")
    meta["tools"] = [t.strip() for t in meta["tools"].split(",") if t.strip()]

    if "## Steps" not in body:
        raise ValueError("skill document missing '## Steps' section")
    when_part, steps_part = body.split("## Steps", 1)
    meta["when_to_use"] = when_part.replace("## When to use", "").strip()
    meta["steps_body"] = steps_part.strip()
    return meta


def truncate_result(value: str, max_chars: int = 300) -> str:
    value = str(value)
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]} ...[truncated {len(value) - max_chars} chars]"


def trajectory_to_text(steps: list[dict], max_result_chars: int = 300) -> str:
    lines = []
    for i, step in enumerate(steps, start=1):
        lines.append(f"Step {i}: {step['tool']}")
        lines.append(f"  args: {json.dumps(step['args'], default=str)}")
        lines.append(f"  result: {truncate_result(step['result'], max_result_chars)}")
    return "\n".join(lines)
