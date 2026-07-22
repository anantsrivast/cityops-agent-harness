"""Did the previous notebook leave its artifacts in the database?

Each notebook opens with require(conn, "<previous notebook id>") so the series
is independently runnable: a clear error names what is missing and where to
backfill it, instead of an ORA-00942 five cells later.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactCheck:
    description: str
    sql: str  # scalar SELECT; truthy first column of first row = pass


REGISTRY: dict[str, list[ArtifactCheck]] = {
    "00_setup": [
        ArtifactCheck(
            description="in-database ONNX embedding model ALL_MINILM_L12_V2",
            sql=(
                "SELECT COUNT(*) FROM user_mining_models "
                "WHERE model_name = 'ALL_MINILM_L12_V2'"
            ),
        ),
    ],
    "01_self_improving_copilot": [
        ArtifactCheck(
            description="CityOps domain data loaded (CITY_INSPECTION_FINDING rows)",
            sql="SELECT COUNT(*) FROM CITY_INSPECTION_FINDING",
        ),
        ArtifactCheck(
            description="tool registry table HARNESS_TOOLS",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_TOOLS'",
        ),
        ArtifactCheck(
            description="workflow capture table HARNESS_WORKFLOW",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_WORKFLOW'",
        ),
        ArtifactCheck(
            description="skillbox table HARNESS_SKILLS",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_SKILLS'",
        ),
    ],
    # Notebooks 01-04 register their artifacts here in later phases.
}


def verify(conn, notebook: str) -> list[tuple[str, bool]]:
    results: list[tuple[str, bool]] = []
    for chk in REGISTRY.get(notebook, []):
        cur = conn.cursor()
        try:
            cur.execute(chk.sql)
            row = cur.fetchone()
            passed = bool(row and row[0])
        except Exception:
            passed = False
        finally:
            cur.close()
        results.append((chk.description, passed))
    return results


def require(conn, notebook: str) -> None:
    failed = [desc for desc, passed in verify(conn, notebook) if not passed]
    if failed:
        missing = "\n  - ".join(failed)
        raise RuntimeError(
            f"Missing artifacts from notebook {notebook!r}:\n  - {missing}\n"
            f"Run that notebook (or its backfill cell) first."
        )
