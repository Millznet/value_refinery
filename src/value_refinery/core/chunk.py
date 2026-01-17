from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

MD_HEADING_RE = re.compile(r"^(#{1,6})\\s+(.*)\\s*$", re.M)

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
            # reset stack to doc title
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

    # Fallback: if we skipped everything (weird doc), return whole doc
    if not chunks:
        return [{"path": "", "title": "", "level": 0, "text": s}]

    return chunks

def decode_bytes(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore")

def iter_input_files(root: Path, allowed_exts: Sequence[str]) -> Iterable[Path]:
    root = root.expanduser()
    allow = {e.lower() if e.startswith(".") else "." + e.lower() for e in allowed_exts}
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in allow:
            yield p
