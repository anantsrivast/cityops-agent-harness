import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from make_student import strip_solutions, to_student

SRC = """def harvest(rows):
    # ✏️ TODO(1): return rows with occurrences >= 3
    # TODO-SOLUTION-START
    keep = [r for r in rows if r.occurrences >= 3]
    return keep
    # TODO-SOLUTION-END
"""


def test_strip_solutions_replaces_block_keeping_indent():
    out = strip_solutions(SRC)
    assert "keep = [" not in out
    assert "TODO-SOLUTION" not in out
    assert "# ✏️ TODO(1)" in out                    # instruction survives
    assert "    #   ... your code here ..." in out  # placeholder at marker indent


def test_strip_solutions_noop_without_markers():
    assert strip_solutions("x = 1\n") == "x = 1\n"


def test_strip_solutions_raises_on_unclosed_marker():
    src = "def f():\n    # TODO-SOLUTION-START\n    return 1\n"
    with pytest.raises(ValueError, match="TODO-SOLUTION-END"):
        strip_solutions(src)


def _nb(cells):
    return {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def test_to_student_strips_code_and_outputs():
    nb = _nb([
        {"cell_type": "markdown", "source": ["# Title"], "metadata": {}},
        {"cell_type": "code", "source": SRC.splitlines(keepends=True),
         "metadata": {}, "outputs": [{"output_type": "stream"}], "execution_count": 7},
    ])
    out = to_student(nb)
    code = out["cells"][1]
    assert "keep = [" not in "".join(code["source"])
    assert code["outputs"] == []
    assert code["execution_count"] is None
    assert out["cells"][0]["source"] == ["# Title"]  # markdown untouched


def test_cli_converts_complete_to_todo(tmp_path):
    nb = _nb([{"cell_type": "code", "source": SRC.splitlines(keepends=True),
               "metadata": {}, "outputs": [], "execution_count": 1}])
    (tmp_path / "01_demo_complete.ipynb").write_text(json.dumps(nb))
    repo = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, str(repo / "tools" / "make_student.py"), str(tmp_path)],
        check=True,
    )
    student = json.loads((tmp_path / "01_demo_todo.ipynb").read_text())
    assert "keep = [" not in "".join(student["cells"][0]["source"])
