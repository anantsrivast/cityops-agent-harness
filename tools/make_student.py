"""Generate learner (*_todo.ipynb) notebooks from authored *_complete.ipynb files.

The complete notebook is the single source of truth; solution code is wrapped in
comment markers and replaced by a placeholder here, so the two can never drift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER_START = "# TODO-SOLUTION-START"
MARKER_END = "# TODO-SOLUTION-END"
PLACEHOLDER = "#   ... your code here ..."


def strip_solutions(source: str) -> str:
    out: list[str] = []
    in_block = False
    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == MARKER_START:
            in_block = True
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}{PLACEHOLDER}\n")
        elif stripped == MARKER_END:
            in_block = False
        elif not in_block:
            out.append(line)
    if in_block:
        raise ValueError("unclosed TODO-SOLUTION-START: missing TODO-SOLUTION-END marker")
    return "".join(out)


def to_student(nb: dict) -> dict:
    student = json.loads(json.dumps(nb))  # deep copy
    for cell in student["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell["source"] = strip_solutions("".join(cell["source"])).splitlines(keepends=True)
        cell["outputs"] = []
        cell["execution_count"] = None
    return student


def main(notebooks_dir: str) -> None:
    directory = Path(notebooks_dir)
    for complete in sorted(directory.glob("*_complete.ipynb")):
        student_path = complete.with_name(
            complete.name.replace("_complete.ipynb", "_todo.ipynb")
        )
        nb = json.loads(complete.read_text())
        student_path.write_text(json.dumps(to_student(nb), indent=1))
        print(f"{complete.name} -> {student_path.name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "notebooks")
