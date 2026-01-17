from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable, Sequence

def decode_bytes(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore")


def iter_input_files(
    root: Path,
    allowed_exts: Sequence[str],
    *,
    ignore_dirs: Sequence[str] | None = None,
) -> Iterable[Path]:
    """
    Yield files under root matching allowed extensions.

    Notes:
    - ignore_dirs is a simple name-based filter applied to any path segment.
    """
    root = root.expanduser()
    allow = {e.lower() if e.startswith(".") else "." + e.lower() for e in allowed_exts}

    if ignore_dirs is None:
        ignore_dirs = (".git", ".venv", "__pycache__", "node_modules", "dist", "build")

    ignore_set = set(ignore_dirs)

    if root.is_file():
        if root.suffix.lower() in allow:
            yield root
        return

    if not root.exists():
        return

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in ignore_set for part in p.parts):
            continue
        if p.suffix.lower() in allow:
            yield p


def _split_by_size(text: str, max_chars: int) -> list[str]:
    """
    Split text into <= max_chars pieces, preferring newline boundaries.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    s = text.replace("\r\n", "\n")
    lines = s.splitlines(keepends=True)

    out: list[str] = []
    cur: list[str] = []
    cur_len = 0

    for ln in lines:
        ln_len = len(ln)
        if cur_len + ln_len > max_chars and cur:
            out.append("".join(cur).strip())
            cur = [ln]
            cur_len = ln_len
        else:
            cur.append(ln)
            cur_len += ln_len

        # pathological: one line bigger than max_chars
        if cur_len > max_chars and len(cur) == 1:
            big = cur[0]
            cur = []
            cur_len = 0
            for i in range(0, len(big), max_chars):
                out.append(big[i : i + max_chars].strip())

    if cur:
        out.append("".join(cur).strip())

    return [x for x in out if x.strip()]


def _pack_parts(parts: list[str], *, min_chars: int, max_chars: int) -> list[str]:
    """
    Pack small parts into chunks, trying to reach min_chars but never exceeding max_chars.
    """
    if not parts:
        return []

    if max_chars <= 0:
        # no cap: just join until min_chars (still useful)
        max_chars = 10**9

    out: list[str] = []
    cur: list[str] = []
    cur_len = 0

    for part in parts:
        p = part.strip()
        if not p:
            continue
        add_len = len(p) + (2 if cur else 0)

        # if adding would exceed max, flush
        if cur and (cur_len + add_len) > max_chars:
            out.append("\n\n".join(cur).strip())
            cur = [p]
            cur_len = len(p)
            continue

        # else add
        if cur:
            cur.append(p)
            cur_len += add_len
        else:
            cur = [p]
            cur_len = len(p)

        # if we reached min, we *may* flush if next would overflow later; but keep simple:
        if cur_len >= max(min_chars, 1) and cur_len >= (max_chars * 0.85):
            out.append("\n\n".join(cur).strip())
            cur = []
            cur_len = 0

    if cur:
        out.append("\n\n".join(cur).strip())

    # enforce hard cap via final split if needed
    final: list[str] = []
    for x in out:
        final.extend(_split_by_size(x, max_chars))
    return [x for x in final if x.strip()]


def chunk_markdown(text: str) -> list[dict]:
    """
    Split markdown into chunks by headings.

    Behavior:
    - If there are H2+ headings, we treat the first H1 as a doc title (path prefix) and chunk on H2+.
    - If there are no H2+ headings, chunk on whatever headings exist (including H1).
    - section_path is hierarchical like: "Incident Response Playbook (Sample) / Goal"
    """
    s = (text or "").replace("\r\n", "\n").strip()
    if not s:
        return [{"path": "", "title": "", "level": 0, "text": ""}]

    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    hs = list(heading_re.finditer(s))
    if not hs:
        return [{"path": "", "title": "", "level": 0, "text": s}]

    levels = [len(m.group(1)) for m in hs]
    has_h2_plus = any(l >= 2 for l in levels)

    chunks: list[dict] = []
    stack: list[str] = []

    # Optional doc title (first H1)
    doc_title = None
    if has_h2_plus:
        for m in hs:
            if len(m.group(1)) == 1:
                doc_title = m.group(2).strip()
                break

    for i, m in enumerate(hs):
        level = len(m.group(1))
        title = m.group(2).strip()

        # If we have H2+ structure, skip emitting H1 as a chunk (use as path prefix only)
        if has_h2_plus and level == 1:
            stack = [title]
            continue

        start = m.start()
        end = hs[i + 1].start() if i + 1 < len(hs) else len(s)
        section_text = s[start:end].strip()
        if not section_text:
            continue

        # maintain hierarchical stack
        stack = stack[: max(0, level - 1)]
        if not stack and doc_title:
            stack = [doc_title]
        if len(stack) >= level:
            stack = stack[: level - 1]
        stack.append(title)

        path = " / ".join(stack)
        chunks.append({"path": path, "title": title, "level": level, "text": section_text})

    if not chunks:
        return [{"path": "", "title": "", "level": 0, "text": s}]

    return chunks


def chunk_text_blocks(text: str, *, min_chunk_chars: int, max_chunk_chars: int) -> list[dict]:
    """
    Chunk .txt/.log by blank-line-separated blocks, then pack into size-bounded chunks.
    """
    s = (text or "").replace("\r\n", "\n").strip()
    if not s:
        return [{"path": "", "title": "", "level": 0, "text": ""}]

    blocks = [b.strip() for b in re.split(r"\n{2,}", s) if b.strip()]
    packed = _pack_parts(blocks, min_chars=min_chunk_chars, max_chars=max_chunk_chars)

    out: list[dict] = []
    for i, chunk in enumerate(packed, start=1):
        out.append({"path": f"Block {i:04d}", "title": f"Block {i:04d}", "level": 0, "text": chunk})
    return out


def chunk_jsonl(text: str, *, min_chunk_chars: int, max_chunk_chars: int, max_records_per_chunk: int = 200) -> list[dict]:
    """
    Chunk .jsonl by records (lines). We don't enforce JSON validity; we treat each non-empty line as a record.
    """
    s = (text or "").replace("\r\n", "\n").strip()
    if not s:
        return [{"path": "", "title": "", "level": 0, "text": ""}]

    lines = [ln for ln in s.splitlines() if ln.strip()]
    out: list[dict] = []

    cur: list[str] = []
    cur_chars = 0
    start_idx = 1
    rec_idx = 0

    def flush(end_idx: int) -> None:
        nonlocal cur, cur_chars, start_idx
        if not cur:
            return
        body = "\n".join(cur).strip()
        out.append({"path": f"Records {start_idx}-{end_idx}", "title": f"Records {start_idx}-{end_idx}", "level": 0, "text": body})
        cur = []
        cur_chars = 0
        start_idx = end_idx + 1

    for ln in lines:
        rec_idx += 1
        ln = ln.strip()
        add = len(ln) + (1 if cur else 0)

        if (max_chunk_chars > 0 and cur and (cur_chars + add) > max_chunk_chars) or (len(cur) >= max_records_per_chunk):
            flush(rec_idx - 1)

        cur.append(ln)
        cur_chars += add

    flush(rec_idx)

    # enforce hard caps if something slipped through (giant record)
    final: list[dict] = []
    for d in out:
        pieces = _split_by_size(d["text"], max_chunk_chars if max_chunk_chars > 0 else 10**9)
        if len(pieces) == 1:
            final.append(d)
        else:
            for i, p in enumerate(pieces, start=1):
                final.append({"path": f'{d["path"]} (part {i})', "title": d["title"], "level": 0, "text": p})
    return final


def chunk_csv(text: str, *, min_chunk_chars: int, max_chunk_chars: int, max_rows_per_chunk: int = 500) -> list[dict]:
    """
    Chunk .csv by row groups. Header is repeated per chunk.
    """
    s = (text or "").replace("\r\n", "\n").strip()
    if not s:
        return [{"path": "", "title": "", "level": 0, "text": ""}]

    f = io.StringIO(s)
    reader = csv.reader(f)
    rows = list(reader)
    if not rows:
        return [{"path": "", "title": "", "level": 0, "text": ""}]

    header = rows[0]
    data_rows = rows[1:]

    out: list[dict] = []
    cur_rows: list[list[str]] = []
    cur_chars = 0
    start_row = 1  # 1-based data row index (excluding header)
    row_idx = 0

    def rows_to_text(rs: list[list[str]]) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(header)
        for r in rs:
            w.writerow(r)
        return buf.getvalue().strip()

    def flush(end_row: int) -> None:
        nonlocal cur_rows, cur_chars, start_row
        if not cur_rows:
            return
        body = rows_to_text(cur_rows)
        out.append({"path": f"Rows {start_row}-{end_row}", "title": f"Rows {start_row}-{end_row}", "level": 0, "text": body})
        cur_rows = []
        cur_chars = 0
        start_row = end_row + 1

    # seed with header cost roughly
    header_text = rows_to_text([])  # header only
    header_cost = len(header_text)

    for r in data_rows:
        row_idx += 1
        # approximate cost: join row with commas + newline
        row_str = ",".join(r)
        add = len(row_str) + 1
        est = header_cost + cur_chars + add

        if (max_chunk_chars > 0 and cur_rows and est > max_chunk_chars) or (len(cur_rows) >= max_rows_per_chunk):
            flush(row_idx - 1)

        cur_rows.append(r)
        cur_chars += add

    flush(row_idx)

    # hard cap enforce
    final: list[dict] = []
    for d in out:
        pieces = _split_by_size(d["text"], max_chunk_chars if max_chunk_chars > 0 else 10**9)
        if len(pieces) == 1:
            final.append(d)
        else:
            for i, p in enumerate(pieces, start=1):
                final.append({"path": f'{d["path"]} (part {i})', "title": d["title"], "level": 0, "text": p})
    return final


def _enforce_chunk_caps(chunks: list[dict], *, max_chunk_chars: int) -> list[dict]:
    """
    If markdown chunks are huge, split them while preserving path.
    """
    if max_chunk_chars <= 0:
        return chunks

    out: list[dict] = []
    for c in chunks:
        t = (c.get("text") or "").strip()
        if not t:
            continue
        if len(t) <= max_chunk_chars:
            out.append(c)
            continue
        pieces = _split_by_size(t, max_chunk_chars)
        base_path = str(c.get("path") or c.get("title") or "")
        title = str(c.get("title") or "")
        level = int(c.get("level") or 0)
        for i, p in enumerate(pieces, start=1):
            out.append({"path": f"{base_path} (part {i})" if base_path else f"part {i}", "title": title, "level": level, "text": p})
    return out


def chunk_text(text: str, *, ext: str, min_chunk_chars: int = 200, max_chunk_chars: int = 8000) -> list[dict]:
    """
    Dispatcher: choose chunking strategy by file extension.
    ext should include the leading dot (e.g. ".md", ".jsonl").
    """
    e = (ext or "").lower()
    if e == ".md":
        chunks = chunk_markdown(text)
        return _enforce_chunk_caps(chunks, max_chunk_chars=max_chunk_chars)

    if e in (".log", ".txt"):
        return chunk_text_blocks(text, min_chunk_chars=min_chunk_chars, max_chunk_chars=max_chunk_chars)

    if e == ".jsonl":
        return chunk_jsonl(text, min_chunk_chars=min_chunk_chars, max_chunk_chars=max_chunk_chars)

    if e == ".csv":
        return chunk_csv(text, min_chunk_chars=min_chunk_chars, max_chunk_chars=max_chunk_chars)

    # fallback: treat as a single blob, but cap it
    s = (text or "").strip()
    if not s:
        return [{"path": "", "title": "", "level": 0, "text": ""}]
    pieces = _split_by_size(s, max_chunk_chars if max_chunk_chars > 0 else 10**9)
    if len(pieces) == 1:
        return [{"path": "", "title": "", "level": 0, "text": pieces[0]}]
    return [{"path": f"part {i}", "title": "", "level": 0, "text": p} for i, p in enumerate(pieces, start=1)]
