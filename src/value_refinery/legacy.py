from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Iterable

import duckdb
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

DEFAULT_DB_PATH = "refinery.duckdb"

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)\s*$", re.M)
ALLOWED_EXTS = {".md", ".txt", ".log", ".jsonl", ".csv"}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_str(s: str) -> str:
    return sha256_bytes(s.encode("utf-8", errors="ignore"))


def chunk_markdown(text: str) -> list[dict]:
    """
    Split markdown into sections by headings.
    Returns list of {path, title, level, text}.
    """
    matches = list(MD_HEADING_RE.finditer(text))
    if not matches:
        return [{"path": "", "title": "", "level": 0, "text": text.strip()}]

    chunks: list[dict] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        level = len(m.group(1))
        title = m.group(2).strip()
        body = text[m.end() : end].strip()
        section_text = f"{m.group(0).strip()}\n{body}".strip()
        chunks.append({"path": title, "title": title, "level": level, "text": section_text})
    return [c for c in chunks if c["text"]]


def basic_quality_score(s: str) -> tuple[int, list[str]]:
    """
    Cheap heuristics. 0-100. Also returns drop reasons.
    """
    reasons: list[str] = []
    t = s.strip()
    if not t:
        return 0, ["empty"]

    n = len(t)
    if n < 200:
        reasons.append("too_short")
    if n > 20000:
        reasons.append("too_long")

    links = len(re.findall(r"https?://", t))
    if links >= 8:
        reasons.append("link_heavy")

    words = re.findall(r"[A-Za-z0-9_]+", t.lower())
    if len(words) < 40:
        reasons.append("too_few_tokens")
    else:
        uniq = len(set(words))
        ratio = uniq / max(1, len(words))
        if ratio < 0.22:
            reasons.append("low_unique_ratio")

    if re.search(r"(copyright|all rights reserved|cookie|newsletter|subscribe)", t, re.I):
        reasons.append("boilerplate_like")

    score = 100
    for r in reasons:
        if r in ("empty",):
            score -= 100
        elif r in ("too_short", "too_few_tokens"):
            score -= 35
        elif r in ("low_unique_ratio",):
            score -= 25
        elif r in ("link_heavy", "boilerplate_like"):
            score -= 20
        elif r in ("too_long",):
            score -= 10

    score = max(0, min(100, score))
    return score, reasons


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            doc_id TEXT PRIMARY KEY,
            source_path TEXT,
            ext TEXT,
            ingested_at BIGINT,
            bytes BIGINT,
            doc_hash TEXT
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT,
            section_path TEXT,
            level INTEGER,
            chunk_hash TEXT,
            n_chars INTEGER,
            score INTEGER,
            reasons TEXT,
            text TEXT
        );
        """
    )
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_score ON chunks(score);")
    except Exception:
        pass


def iter_input_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            yield p


def decode_bytes(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore")


@app.command()
def run(
    input: Path = typer.Option(Path("data/raw"), "--input", "-i"),
    db: Path = typer.Option(Path(DEFAULT_DB_PATH), "--db"),
    min_score: int = typer.Option(55, "--min-score"),
    limit: int = typer.Option(0, "--limit", help="0 means no limit"),
    show: bool = typer.Option(False, "--show", help="Print sample kept chunks"),
) -> None:
    """
    Ingest -> chunk -> score -> store (DuckDB).

    This is the working 'legacy' runner. Next we refactor into core/ + packs/.
    """
    input = input.expanduser()
    db = db.expanduser()

    con = duckdb.connect(str(db))
    ensure_schema(con)

    files = list(iter_input_files(input))
    if limit and limit > 0:
        files = files[:limit]

    docs_ingested = 0
    chunks_written = 0
    chunks_kept = 0

    t0 = time.time()
    for p in files:
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
            INSERT INTO docs(doc_id, source_path, ext, ingested_at, bytes, doc_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
              source_path=excluded.source_path,
              ext=excluded.ext,
              ingested_at=excluded.ingested_at,
              bytes=excluded.bytes,
              doc_hash=excluded.doc_hash
            """,
            [doc_id, str(p), ext, ing, size, doc_hash],
        )
        docs_ingested += 1

        text = decode_bytes(data)
        if p.suffix.lower() == ".md":
            chunks = chunk_markdown(text)
        else:
            chunks = [{"path": "", "title": "", "level": 0, "text": text.strip()}]

        for c in chunks:
            t = (c.get("text") or "").strip()
            if not t:
                continue

            score, reasons = basic_quality_score(t)
            chunk_hash = sha256_str(t)
            section_path = (c.get("path") or "")[:400]
            level = int(c.get("level") or 0)
            n_chars = len(t)
            chunk_id = sha256_str(f"{doc_id}:{section_path}:{chunk_hash}")

            con.execute(
                """
                INSERT INTO chunks(chunk_id, doc_id, section_path, level, chunk_hash, n_chars, score, reasons, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                  doc_id=excluded.doc_id,
                  section_path=excluded.section_path,
                  level=excluded.level,
                  chunk_hash=excluded.chunk_hash,
                  n_chars=excluded.n_chars,
                  score=excluded.score,
                  reasons=excluded.reasons,
                  text=excluded.text
                """,
                [
                    chunk_id,
                    doc_id,
                    section_path,
                    level,
                    chunk_hash,
                    n_chars,
                    int(score),
                    json.dumps(reasons),
                    t,
                ],
            )
            chunks_written += 1
            if score >= min_score:
                chunks_kept += 1

    dt = time.time() - t0

    table = Table(title="Value Refinery — Run Summary")
    table.add_column("DB")
    table.add_column("Input")
    table.add_column("Docs", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column(f"Kept (>= {min_score})", justify="right")
    table.add_column("Seconds", justify="right")
    table.add_row(str(db), str(input), str(docs_ingested), str(chunks_written), str(chunks_kept), f"{dt:.2f}")
    console.print(table)

    if show and chunks_kept:
        console.print("[bold]Sample kept chunks:[/bold]")
        rows = con.execute(
            "SELECT source_path, section_path, score, substr(text,1,300) as sample "
            "FROM chunks JOIN docs USING(doc_id) WHERE score >= ? ORDER BY score DESC LIMIT 5",
            [min_score],
        ).fetchall()
        for src, sec, sc, sample in rows:
            console.print(f"[cyan]{sc}[/cyan] {src} :: {sec}\n{sample}\n")


@app.command()
def stats(db: Path = typer.Option(Path(DEFAULT_DB_PATH), "--db")) -> None:
    """Quick DB stats."""
    db = db.expanduser()
    con = duckdb.connect(str(db))
    ensure_schema(con)

    docs = con.execute("SELECT count(*) FROM docs").fetchone()[0]
    chunks = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    avg = con.execute("SELECT coalesce(avg(score),0) FROM chunks").fetchone()[0]
    try:
        p90 = con.execute("SELECT coalesce(quantile_cont(score, 0.90),0) FROM chunks").fetchone()[0]
    except Exception:
        p90 = 0

    table = Table(title="Value Refinery — Stats")
    table.add_column("DB")
    table.add_column("Docs", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Avg score", justify="right")
    table.add_column("P90 score", justify="right")
    table.add_row(str(db), str(docs), str(chunks), f"{avg:.1f}", f"{p90:.1f}")
    console.print(table)


if __name__ == "__main__":
    app()

