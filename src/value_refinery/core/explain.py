from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


DECISION_KEYS = ("decision", "action", "status", "kind", "outcome")
PATH_KEYS = ("path", "rel", "file", "source_path", "input_path")


def _first_key(d: dict, keys: Iterable[str]) -> str | None:
    for k in keys:
        if k in d:
            return k
    return None


def decision_kind(d: dict) -> str:
    k = _first_key(d, DECISION_KEYS)
    if not k:
        return ""
    v = d.get(k)
    return "" if v is None else str(v)


def decision_path(d: dict) -> str:
    k = _first_key(d, PATH_KEYS)
    if not k:
        return ""
    v = d.get(k)
    return "" if v is None else str(v)


def iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict):
                    yield obj
                else:
                    yield {"_raw": ln, "_error": "non_object_json"}
            except json.JSONDecodeError as e:
                yield {"_raw": ln, "_error": f"json_decode_error:{e.msg}"}


@dataclass(frozen=True)
class ExplainFilters:
    decisions: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    contains: str = ""


def match_filters(d: dict, *, flt: ExplainFilters) -> bool:
    if flt.decisions:
        kind = decision_kind(d)
        if not kind or kind not in flt.decisions:
            return False

    if flt.paths:
        p = decision_path(d)
        ok = False
        for needle in flt.paths:
            if needle and (needle == p or needle in p):
                ok = True
                break
        if not ok:
            return False

    if flt.contains:
        blob = json.dumps(d, sort_keys=True, ensure_ascii=False)
        if flt.contains not in blob:
            return False

    return True


def load_filtered(path: Path, *, flt: ExplainFilters, limit: int = 50) -> list[dict]:
    out: list[dict] = []
    for d in iter_jsonl(path):
        if match_filters(d, flt=flt):
            out.append(d)
            if limit and len(out) >= limit:
                break
    return out


def count_by_decision(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in iter_jsonl(path):
        k = decision_kind(d) or "unknown"
        counts[k] = counts.get(k, 0) + 1
    return counts
