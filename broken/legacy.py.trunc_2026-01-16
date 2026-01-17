from __future__ import annotations
import re, os, json, time, hashlib, pathlib
import duckdb
import typer
from rich import print

app = typer.Typer(add_completion=False)

DB_PATH = "refinery.duckdb"

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_str(s: str) -> str:
    return sha256_bytes(s.encode("utf-8", errors="ignore"))

def now_ts() -> int:
    return int(time.time())

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)\s*$", re.M)

def chunk_markdown(text: str) -> list[dict]:
    """
    Split markdown into sections by headings.
    Returns list of {path, title, level, text}.
    """
    matches = list(MD_HEADING_RE.finditer(text))
    if not matches:
        # fallback: one big chunk
        return [{"path": "", "title": "", "level": 0, "text": text.strip()}]

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        level = len(m.group(1))
        title = m.group(2).strip()
        body = text[m.end():end].strip()
        section_text = f"{m.group(0).strip()}\n{body}".strip()
        chunks.append({
            "path": title,
            "title": title,
            "level": level,
            "text": section_text
        })
    return [c for c in chunks if c["text"]]

def basic_quality_score(s: str) -> tuple[int, list[str]]:
    """
    Cheap heuristics. 0-100. Also returns drop reasons.
    """
    reasons = []
    t = s.strip()
    if not t:
        return 0, ["empty"]

    # length
    n = len(t)
    if n < 200:
        reasons.append("too_short")
    if n > 20000:
        reasons.append("too_long")

    # link density
    links = len(re.findall(r"https?://", t))
    if links >= 8:
        reasons.append("link_heavy")

    # repetition / low diversity
    words = re.findall(r"[A-Za-z0-9_]+", t.lower())
    if len(words) < 40:
        reasons.append("too_few_tokens")
    else:
        uniq = len(set(words))
        ratio = uniq / max(1, len(words))
        if ratio < 0.22:
            reasons.append("low_unique_ratio")

    # "template" vibe
    if re.search(r"(copyright|all rights reserved|cookie|newsletter|subscribe)", t, re.I):
        reasons.append("boilerplate_like")

    # scoring rule (simple)
    score = 100
    for r in reasons:
        if r in ("empty",):
            score -= 100
        elif r in ("too_short","too_few_tokens"):
            score -= 35
        elif r in ("low_unique_ratio",):
            score -= 25
        elif r in ("link_heavy","boilerplate_like"):
            score -= 20
        elif r in ("too_long",):
            score -= 10

    score = max(0, min(100, score))
    return score, reasons

def ensure_schema(con: duckdb.DuckDBPyConnection):
    con.execute("""
    CREATE TABLE IF NOT EXISTS docs (
        doc_id TEXT PRIMARY KEY,
        source_path TEXT,
        ext TEXT,
        ingested_at BIGINT,
        bytes BIGINT,
        doc_hash TEXT
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT,
        section_path TEXT,
        level INTEGER,
        chunk_hash TEXT,
        n_chars INTEGER,
        score INTEGER,
        reasons TEXT,   -- json array string
        kept BOOLEAN
    );
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_kept ON chunks(kept);")
    con.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash);")

def iter_files(root: str):
    rootp = pathlib.Path(root)
    for p in rootp.rglob("*"):
        if p.is_file():
            yield p

@app.command()
def ingest(path: str = "docs", exts: str = "md,txt"):
    """
    Ingest md/txt files into DuckDB.
    """
    exts_set = set(["." + e.strip().lstrip(".") for e in exts.split(",") if e.strip()])
    con = duckdb.connect(DB_PATH)
    ensure_schema(con)

    added_docs = 0
    added_chunks = 0

    for p in iter_files(path):
        if p.suffix.lower() not in exts_set:
            continue
        try:
            data = p.read_bytes()
        except Exception as e:
            print(f"[yellow]skip read failed[/yellow]: {p} ({e})")
            continue

        doc_hash = sha256_bytes(data)
        doc_id = doc_hash  # stable id
        ext = p.suffix.lower().lstrip(".")
        ing = now_ts()
        size = len(data)

        # upsert doc
        con.execute("""
            INSERT INTO docs(doc_id, source_path, ext, ingested_at, bytes, doc_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
              source_path=excluded.source_path,
              ext=excluded.ext,
              ingested_at=exclud_

