from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RedactionHit:
    redaction_id: str
    n: int


def apply_redactions(*, text: str, redaction_cfg: dict[str, Any]) -> tuple[str, list[RedactionHit]]:
    """
    redaction_cfg format:
      redactions: list of:
        - id: str
          kind: "regex"
          pattern: str
          replace: str
    """
    hits: list[RedactionHit] = []
    redactions = redaction_cfg.get("redactions") or []

    out = text
    for r in redactions:
        try:
            rid = str(r.get("id", "redaction"))
            kind = str(r.get("kind", "regex"))
            pat = str(r.get("pattern", ""))
            repl = str(r.get("replace", "[REDACTED]"))

            if kind != "regex" or not pat:
                continue

            out, n = re.subn(pat, repl, out, flags=re.IGNORECASE | re.MULTILINE)
            if n:
                hits.append(RedactionHit(rid, int(n)))
        except Exception:
            continue

    return out, hits
