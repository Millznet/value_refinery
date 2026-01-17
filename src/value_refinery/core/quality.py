from __future__ import annotations

import re

def basic_quality_score(s: str) -> tuple[int, list[str]]:
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
