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
    "02_scheduled_briefings": [
        ArtifactCheck(
            description="scratch note store HARNESS_SCRATCH",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_SCRATCH'",
        ),
        ArtifactCheck(
            description="promotion queue HARNESS_PROMOTION_QUEUE",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_PROMOTION_QUEUE'",
        ),
        ArtifactCheck(
            description="provenance sidecar HARNESS_MEMORY_META",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_MEMORY_META'",
        ),
        ArtifactCheck(
            description="briefing store HARNESS_BRIEFING",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_BRIEFING'",
        ),
        ArtifactCheck(
            description="SDK long-term memory table CITY_MEMORY",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'CITY_MEMORY'",
        ),
        ArtifactCheck(
            description="scheduled HARNESS jobs registered",
            sql=(
                "SELECT COUNT(*) FROM user_scheduler_jobs "
                "WHERE job_name IN ('HARNESS_STAGE_JOB', 'HARNESS_BRIEFING_JOB')"
            ),
        ),
    ],
    "03_context_engineering": [
        ArtifactCheck(
            description="simulated season transcript HARNESS_TRANSCRIPT",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_TRANSCRIPT'",
        ),
        ArtifactCheck(
            description="versioned compaction cards HARNESS_CARD",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_CARD'",
        ),
        ArtifactCheck(
            description="offloaded tool-result store HARNESS_BLOB",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_BLOB'",
        ),
    ],
    "04_evals": [
        ArtifactCheck(
            description="eval results store HARNESS_EVAL",
            sql="SELECT COUNT(*) FROM user_tables WHERE table_name = 'HARNESS_EVAL'",
        ),
        ArtifactCheck(
            description="at least five evals recorded",
            sql="SELECT COUNT(*) FROM (SELECT DISTINCT eval_name FROM HARNESS_EVAL) "
                "HAVING COUNT(*) >= 5",
        ),
    ],
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
