from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import duckdb


def write_report(*, db_path: Path, run_id: str, out_dir: Path, min_score: int) -> dict[str, str]:
    out_dir = out_dir.expanduser()
    db_path = db_path.expanduser()

    con = duckdb.connect(str(db_path))

    docs = con.execute("SELECT count(*) FROM docs WHERE run_id=?", [run_id]).fetchone()[0]
    chunks = con.execute("SELECT count(*) FROM chunks WHERE run_id=?", [run_id]).fetchone()[0]

    def n(kind: str) -> int:
        return con.execute("SELECT count(*) FROM decisions WHERE run_id=? AND kind=?", [run_id, kind]).fetchone()[0]

    kept = n("keep")
    dropped_low = n("drop_low_score")
    dropped_dup = n("drop_dup")

    # Top sources by kept chunks
    top_sources = con.execute(
        """
        SELECT d.source_path, count(*) AS kept_chunks
        FROM decisions AS dec
        JOIN chunks AS c ON c.chunk_id = dec.target_id AND c.run_id = dec.run_id
        JOIN docs   AS d ON d.doc_id = c.doc_id AND d.run_id = c.run_id
        WHERE dec.run_id = ? AND dec.kind = 'keep'
        GROUP BY d.source_path
        ORDER BY kept_chunks DESC
        LIMIT 10
        """,
        [run_id],
    ).fetchall()

    # Reason frequency from decisions
    reason_counts: Counter[str] = Counter()
    rows = con.execute("SELECT reasons FROM decisions WHERE run_id=?", [run_id]).fetchall()
    for (r,) in rows:
        try:
            arr = json.loads(r or "[]")
            if isinstance(arr, list):
                reason_counts.update([str(x) for x in arr])
        except Exception:
            continue

    report_json = {
        "run_id": run_id,
        "min_score": int(min_score),
        "counts": {
            "docs": int(docs),
            "unique_chunks": int(chunks),
            "kept": int(kept),
            "dropped_low_score": int(dropped_low),
            "dropped_dup": int(dropped_dup),
        },
        "top_sources": [{"source_path": s, "kept_chunks": int(k)} for (s, k) in top_sources],
        "reason_counts": dict(reason_counts.most_common()),
    }

    # Write files
    (out_dir / "report.json").write_text(json.dumps(report_json, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"# Value Refinery Report\n")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- min_score: `{min_score}`\n")
    c = report_json["counts"]
    lines.append("## Counts")
    lines.append(f"- docs: {c['docs']}")
    lines.append(f"- unique_chunks: {c['unique_chunks']}")
    lines.append(f"- kept: {c['kept']}")
    lines.append(f"- dropped_low_score: {c['dropped_low_score']}")
    lines.append(f"- dropped_dup: {c['dropped_dup']}\n")

    lines.append("## Top sources (kept)")
    if report_json["top_sources"]:
        for item in report_json["top_sources"]:
            lines.append(f"- {item['kept_chunks']} — {item['source_path']}")
    else:
        lines.append("- (none)")
    lines.append("")

    lines.append("## Reason frequency (all decisions)")
    if report_json["reason_counts"]:
        for k, v in list(report_json["reason_counts"].items())[:20]:
            lines.append(f"- {v} — {k}")
    else:
        lines.append("- (none)")
    lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "report_md": str(out_dir / "report.md"),
        "report_json": str(out_dir / "report.json"),
    }
