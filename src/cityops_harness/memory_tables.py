"""Read-only lens on the agent-memory store's managed ``CITY_`` tables.

The SDK reads these tables back for you, which hides *where* each thing lives.
These helpers print the rows themselves, so each SDK call in notebook 02 can be
matched to the record it left behind. Plain SQL, read-only; nothing here is
needed to *use* the store - it is how you check what the store did.

Every helper takes the connection first, so the same function works against a
second session (notebook 02 §7 reads via ``conn2``).
"""

from __future__ import annotations

from typing import Any

# The store files its own bookkeeping under the '$agent_memory' metadata key.
_INVALIDATION_REASON = """JSON_VALUE(metadata, '$."$agent_memory".invalidation_reason')"""


def _lob(v: Any) -> Any:
    return v.read() if hasattr(v, "read") else v


def _rows(conn, sql: str, **binds) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, **binds)
        return [tuple(_lob(v) for v in r) for r in cur.fetchall()]


def show_memory_trail(conn, path: str, label: str | None = None) -> None:
    """One note's trail through the managed tables, read straight from them.

    Prints the ``CITY_MESSAGE`` row the note was posted as, the ``CITY_MEMORY``
    row extraction kept (metadata inherited from that message), the
    ``CITY_RECORD_CHUNKS`` rows ``search()`` scans, and every
    ``CITY_MEMORY_LINK`` row touching the memory.
    """
    print(f"  ----- {label or path} -----")
    # Each run opens a fresh inbox thread, so a re-posted note has one message per
    # run: show the latest posting and count the rest.
    msgs = _rows(conn, """SELECT record_id, thread_id, order_seq, message_role, status,
                                 JSON_VALUE(content, '$[0].text'), COUNT(*) OVER ()
                            FROM CITY_MESSAGE
                           WHERE JSON_VALUE(metadata, '$.source_path') = :p
                           ORDER BY order_seq DESC FETCH FIRST 1 ROWS ONLY""", p=path)
    print("  CITY_MESSAGE - the note as promote_note posted it to the inbox thread")
    for rid, tid, seq, role, st, text, total in msgs:
        print(f"    {rid[:8]}  thread={tid[:8]} seq={seq} role={role} status={st}  "
              f"{(text or '')[:58]}..."
              + (f"  (+{total - 1} earlier posting(s) from previous runs)" if total > 1 else ""))
    if not msgs:
        print("    (not posted - never promoted)")
    mems = _rows(conn, f"""SELECT record_id, status, memory_type,
                                  JSON_VALUE(metadata, '$.revision'),
                                  JSON_VALUE(metadata, '$.days_ago'),
                                  {_INVALIDATION_REASON},
                                  DBMS_LOB.SUBSTR(content, 58, 1)
                             FROM CITY_MEMORY
                            WHERE JSON_VALUE(metadata, '$.source_path') = :p
                            ORDER BY created_at""", p=path)
    print(f"  CITY_MEMORY ({len(mems)}) - what extraction kept; metadata inherited from the message")
    for rid, st, mtype, rev, days, why, text in mems:
        print(f"    {rid[:8]}  status={st} type={mtype} revision={(rev or '')[:8]} "
              f"days_ago={days}" + (f"  invalidation_reason={why!r}" if why else ""))
        print(f"      content: {(text or '')[:58]}...")
        chunks = _rows(conn, """SELECT chunk_id, chunk_seq, status FROM CITY_RECORD_CHUNKS
                                 WHERE source_id = :m ORDER BY chunk_seq""", m=rid)
        print(f"    CITY_RECORD_CHUNKS for it ({len(chunks)}) - what search() scans: "
              + ", ".join(f"chunk={c} seq={s} status={st}" for c, s, st in chunks))
        links = _rows(conn, """SELECT relation_id, source_memory_id, relation_type,
                                      opposite_relation_type, target_memory_id, metadata
                                 FROM CITY_MEMORY_LINK
                                WHERE source_memory_id = :m OR target_memory_id = :m
                                ORDER BY created_at""", m=rid)
        print(f"    CITY_MEMORY_LINK touching it ({len(links)})" + (":" if links else ": none"))
        for lid, src, rel, opp, tgt, meta in links:
            print(f"      {lid[:8]}  {src[:8]} --{rel}--> {tgt[:8]}  "
                  f"(opposite: {opp})  metadata={meta}")


def show_link_rows(conn, memory_id: str, names: dict[str, str] | None = None,
                   label: str = "CITY_MEMORY_LINK") -> None:
    """Every relation row touching one memory, exactly as stored.

    ``names`` maps memory ids to short labels for the printout (e.g. "defect").
    """
    names = names or {}

    def nm(i: str) -> str:
        return names.get(i, i[:8])

    links = _rows(conn, """SELECT relation_id, source_memory_id, relation_type,
                                  opposite_relation_type, target_memory_id, metadata, created_at
                             FROM CITY_MEMORY_LINK
                            WHERE source_memory_id = :m OR target_memory_id = :m
                            ORDER BY created_at""", m=memory_id)
    print(f"  {label} - rows touching {nm(memory_id)} ({len(links)})" + (":" if links else ": none"))
    for lid, src, rel, opp, tgt, meta, created in links:
        print(f"    relation_id={lid[:8]}  {nm(src)} --{rel}--> {nm(tgt)}  "
              f"opposite={opp}  metadata={meta}  created={created:%H:%M:%S}")


def show_memory_rows(conn, asset_id: str, label: str = "CITY_MEMORY") -> None:
    """Every memory row the store holds for one asset: lifecycle status + provenance.

    The valid rows are what recall and the briefing see; the invalid ones are history.
    """
    rows = _rows(conn, f"""SELECT record_id, status, JSON_VALUE(metadata, '$.source_path'),
                                  JSON_VALUE(metadata, '$.days_ago'), {_INVALIDATION_REASON}
                             FROM CITY_MEMORY
                            WHERE user_id = :u AND agent_id = 'CITY'
                            ORDER BY status DESC, TO_NUMBER(JSON_VALUE(metadata, '$.days_ago'))""",
                 u=asset_id)
    print(f"  {label} - rows for {asset_id!r} ({len(rows)}):")
    for rid, st, path, days, why in rows:
        print(f"    {rid[:8]}  {st:<8} days_ago={str(days or 0):>4}  {path}"
              + (f"  ({why})" if why else ""))
