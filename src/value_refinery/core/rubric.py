from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    reason: str
    weight: int


def score_with_rubric(*, text: str, rubric: dict[str, Any]) -> tuple[int, list[str], list[RuleHit]]:
    """
    Apply a simple weighted rubric.

    rubric format:
      base_score: int (default 80)
      rules: list of:
        - id: str
          kind: "regex" | "regex_count_ge"
          pattern: str
          weight: int
          reason: str
          threshold: int (only for regex_count_ge)
    """
    base = int(rubric.get("base_score", 80))
    rules = rubric.get("rules") or []

    score = base
    reasons: list[str] = []
    hits: list[RuleHit] = []

    for r in rules:
        try:
            rid = str(r.get("id", "rule"))
            kind = str(r.get("kind", "regex"))
            pat = str(r.get("pattern", ""))
            weight = int(r.get("weight", 0))
            reason = str(r.get("reason", rid))

            if not pat:
                continue

            if kind == "regex":
                if re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE):
                    score += weight
                    reasons.append(reason)
                    hits.append(RuleHit(rid, reason, weight))

            elif kind == "regex_count_ge":
                thr = int(r.get("threshold", 1))
                cnt = len(re.findall(pat, text, flags=re.IGNORECASE | re.MULTILINE))
                if cnt >= thr:
                    score += weight
                    reasons.append(reason)
                    hits.append(RuleHit(rid, reason, weight))

            else:
                # unknown kind -> ignore
                continue
        except Exception:
            # a bad rule shouldn't kill the run
            continue

    # clamp 0..100
    score = max(0, min(100, score))
    return score, reasons, hits
