from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .chunk import chunk_text, decode_bytes, iter_input_files
from .db import connect
from .quality import basic_quality_score

from .rubric import score_with_rubric
from .redact import apply_redactions

console = Console()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_str(s: str) -> str:
    return sha256_bytes(s.encode("utf-8", errors="ignore"))


def _insert_run(
    con,
    *,
    run_id: str,
    pack_id: str,
    created_at: int,
    input_path: str,
    out_dir: str,
    db_path: str,
    manifest_path: str,
    pack_json: str,
) -> None:
    con.execute(
        """
        INSERT INTO runs(run_id, pack_id, created_at, input_path, out_dir, db_path, manifest_path, pack_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
          pack_id=excluded.pack_id,
          created_at=excluded.created_at,
          input_path=excluded.input_path,
          out_dir=excluded.out_dir,
          db_path=excluded.db_path,
          manifest_path=excluded.manifest_path,
          pack_json=excluded.pack_json
        """,
        [run_id, pack_id, created_at, input_path, out_dir, db_path, manifest_path, pack_json],
    )


def _decision_id(run_id: str, kind: str, target_id: str, score: int | None, reasons: str) -> str:
    return sha256_str(f"{run_id}:{kind}:{target_id}:{score}:{reasons}")


def _insert_decision(
    con,
    *,
    run_id: str,
    kind: str,
    target_id: str,
    score: int | None,
    reasons_json: str,
    created_at: int,
) -> None:
    did = _decision_id(run_id, kind, target_id, score, reasons_json)
    con.execute(
        """
        INSERT INTO decisions(decision_id, run_id, kind, target_id, score, reasons, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(decision_id) DO NOTHING
        """,
        [did, run_id, kind, target_id, score, reasons_json, created_at],
    )


def _insert_dedup(
    con,
    *,
    run_id: str,
    chunk_hash: str,
    canonical_chunk_id: str,
    dup_chunk_id: str,
    created_at: int,
) -> None:
    dedup_id = sha256_str(f"{run_id}:{chunk_hash}:{canonical_chunk_id}:{dup_chunk_id}")
    con.execute(
        """
        INSERT INTO dedup(dedup_id, run_id, chunk_hash, canonical_chunk_id, dup_chunk_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(dedup_id) DO NOTHING
        """,
        [dedup_id, run_id, chunk_hash, canonical_chunk_id, dup_chunk_id, created_at],
    )


def run_pipeline(
    *,
    run_id: str,
    pack_id: str,
    pack: dict,
    input: Path,
    db: Path,
    out_dir: Path,
    manifest_path: Path,
    min_score: int,
    limit: int,
    show: bool,
    allowed_exts: list[str],
    max_bytes: int = 0,
    max_chunk_chars: int = 8000,
    min_chunk_chars: int = 200,
) -> None:
    input = input.expanduser()
    db = db.expanduser()
    out_dir = out_dir.expanduser()
    manifest_path = manifest_path.expanduser()

    con = connect(str(db))
    
    rubric = pack.get("rubric") or {}
    redaction_cfg = pack.get("redaction") or {}

    now = int(time.time())
    _insert_run(
        con,
        run_id=run_id,
        pack_id=pack_id,
        created_at=now,
        input_path=str(input),
        out_dir=str(out_dir),
        db_path=str(db),
        manifest_path=str(manifest_path),
        pack_json=json.dumps(pack),
    )

    files = list(iter_input_files(input, allowed_exts=allowed_exts))
    if limit and limit > 0:
        files = files[:limit]

    docs_ingested = 0
    chunks_unique = 0
    kept = 0
    dropped_low = 0
    dropped_dup = 0

    t0 = time.time()

    for p in files:
        if max_bytes and max_bytes > 0:
            try:
                st = p.stat()
                if st.st_size > max_bytes:
                    console.print(f"[yellow]skip too large[/yellow]: {p} ({st.st_size} bytes)")
                    continue
            except Exception:
                pass
        try:
            data = p.read_bytes()
        except Exception as e:
            console.print(f"[yellow]skip read failed[/yellow]: {p} ({e})")
            continue

        doc_hash = sha256_bytes(data)
        doc_id = doc_hash
        ext = p.suffix.lower().lstrip(".")
        ing = int(time.time())
        size = len(data)

        con.execute(
            """
            INSERT INTO docs(doc_id, run_id, source_path, ext, ingested_at, bytes, doc_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
              run_id=excluded.run_id,
              source_path=excluded.source_path,
              ext=excluded.ext,
              ingested_at=excluded.ingested_at,
              bytes=excluded.bytes,
              doc_hash=excluded.doc_hash
            """,
            [doc_id, run_id, str(p), ext, ing, size, doc_hash],
        )
        docs_ingested += 1

        text = decode_bytes(data)
        chunks = chunk_text(text, ext=p.suffix.lower(), max_chunk_chars=max_chunk_chars, min_chunk_chars=min_chunk_chars)


        for c in chunks:
            t = (c.get("text") or "").strip()
            if not t:
                continue

            # 1) redact first (affects hash/exported text)
            t_red, red_hits = apply_redactions(text=t, redaction_cfg=redaction_cfg)

            # 2) score: start with cheap heuristics then apply rubric weights
            base_score, base_reasons = basic_quality_score(t_red)
            rub_score, rub_reasons, _hits = score_with_rubric(text=t_red, rubric=rubric)

            # combine: base heuristics reasons + rubric reasons + redaction info
            score = max(0, min(100, int(rub_score)))  # rubric already includes base_score; keep simple for now
            reasons = list(dict.fromkeys(list(base_reasons) + list(rub_reasons)))  # stable de-dupe
            if red_hits:
                for h in red_hits:
                    reasons.append(f"redacted:{h.redaction_id}:{h.n}")

            reasons_json = json.dumps(reasons)
            chunk_hash = sha256_str(t_red)
            
            section_path = str(c.get("path") or c.get("title") or "")
            level = int(c.get("level") or 0)
            
            chunk_id = sha256_str(f"{doc_id}:{section_path}:{level}:{chunk_hash}")

            # use redacted text in DB
            t = t_red
            
            n_chars = int(len(t))

            # exact dedup within run
            canon = con.execute(
                "SELECT chunk_id FROM chunks WHERE run_id=? AND chunk_hash=? LIMIT 1",
                [run_id, chunk_hash],
            ).fetchone()

            if canon:
                dropped_dup += 1
                _insert_dedup(
                    con,
                    run_id=run_id,
                    chunk_hash=chunk_hash,
                    canonical_chunk_id=canon[0],
                    dup_chunk_id=chunk_id,
                    created_at=int(time.time()),
                )
                _insert_decision(
                    con,
                    run_id=run_id,
                    kind="drop_dup",
                    target_id=chunk_id,
                    score=score,
                    reasons_json=reasons_json,
                    created_at=int(time.time()),
                )
                continue

            # store unique chunk
            con.execute(
                """
                INSERT INTO chunks(chunk_id, run_id, doc_id, section_path, level, chunk_hash, n_chars, score, reasons, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                  run_id=excluded.run_id,
                  doc_id=excluded.doc_id,
                  section_path=excluded.section_path,
                  level=excluded.level,
                  chunk_hash=excluded.chunk_hash,
                  n_chars=excluded.n_chars,
                  score=excluded.score,
                  reasons=excluded.reasons,
                  text=excluded.text
                """,
                [chunk_id, run_id, doc_id, section_path, level, chunk_hash, n_chars, int(score), reasons_json, t],
            )
            chunks_unique += 1

            if score >= min_score:
                kept += 1
                _insert_decision(
                    con,
                    run_id=run_id,
                    kind="keep",
                    target_id=chunk_id,
                    score=score,
                    reasons_json=reasons_json,
                    created_at=int(time.time()),
                )
            else:
                dropped_low += 1
                _insert_decision(
                    con,
                    run_id=run_id,
                    kind="drop_low_score",
                    target_id=chunk_id,
                    score=score,
                    reasons_json=reasons_json,
                    created_at=int(time.time()),
                )

    dt = time.time() - t0

    table = Table(title="Value Refinery — Run Summary")
    table.add_column("Run")
    table.add_column("Pack")
    table.add_column("Docs", justify="right")
    table.add_column("Unique chunks", justify="right")
    table.add_column(f"Kept (>= {min_score})", justify="right")
    table.add_column("Dropped low", justify="right")
    table.add_column("Dropped dup", justify="right")
    table.add_column("Seconds", justify="right")
    table.add_row(run_id, pack_id, str(docs_ingested), str(chunks_unique), str(kept), str(dropped_low), str(dropped_dup), f"{dt:.2f}")
    console.print(table)

    if show and kept:
        rows = con.execute(
            "SELECT source_path, section_path, score, substr(text,1,300) as sample "
            "FROM chunks JOIN docs USING(doc_id) "
            "WHERE chunks.run_id=? AND score >= ? "
            "ORDER BY score DESC LIMIT 5",
            [run_id, min_score],
        ).fetchall()
        console.print("[bold]Sample kept chunks:[/bold]")
        for src, sec, sc, sample in rows:
            console.print(f"[cyan]{sc}[/cyan] {src} :: {sec}\n{sample}\n")
