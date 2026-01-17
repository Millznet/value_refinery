from __future__ import annotations

import json
from pathlib import Path

import duckdb

def export_run(*, db_path: Path, run_id: str, out_dir: Path, min_score: int) -> dict[str, str]:
    out_dir = out_dir.expanduser()
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))

    chunks_kept = exports_dir / "chunks_kept.jsonl"
    cur = con.execute(
        "SELECT chunks.run_id, chunks.chunk_id, chunks.doc_id, docs.source_path, chunks.section_path, chunks.level, "
        "chunks.chunk_hash, chunks.n_chars, chunks.score, chunks.reasons, chunks.text "
        "FROM chunks JOIN docs ON chunks.doc_id = docs.doc_id AND chunks.run_id = docs.run_id "
        "WHERE chunks.run_id = ? AND chunks.score >= ? ",
        [run_id, int(min_score)],
    )
    cols = [c[0] for c in cur.description]
    with chunks_kept.open("w", encoding="utf-8") as f:
        for row in cur.fetchall():
            obj = dict(zip(cols, row))
            try:
                obj["reasons"] = json.loads(obj.get("reasons") or "[]")
            except Exception:
                obj["reasons"] = []
            f.write(json.dumps(obj, ensure_ascii=False) + "\\n")

    decisions = exports_dir / "decisions.jsonl"
    cur2 = con.execute(
        "SELECT decision_id, run_id, kind, target_id, score, reasons, created_at "
        "FROM decisions WHERE run_id = ? ORDER BY created_at ASC",
        [run_id],
    )
    cols2 = [c[0] for c in cur2.description]
    with decisions.open("w", encoding="utf-8") as f:
        for row in cur2.fetchall():
            obj = dict(zip(cols2, row))
            try:
                obj["reasons"] = json.loads(obj.get("reasons") or "[]")
            except Exception:
                obj["reasons"] = []
            f.write(json.dumps(obj, ensure_ascii=False) + "\\n")

    return {
        "exports_dir": str(exports_dir),
        "chunks_kept": str(chunks_kept),
        "decisions": str(decisions),
    }
