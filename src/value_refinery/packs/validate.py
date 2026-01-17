from __future__ import annotations

import re
from typing import Any


class PackValidationError(ValueError):
    pass


def _is_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _err(errors: list[str], path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _compile_regex(errors: list[str], path: str, pat: Any) -> None:
    if not _is_str(pat):
        _err(errors, path, "pattern must be a non-empty string")
        return
    try:
        re.compile(str(pat))
    except re.error as e:
        _err(errors, path, f"invalid regex: {e}")


def validate_pack(cfg: dict) -> None:
    errors: list[str] = []

    if not isinstance(cfg, dict):
        raise PackValidationError("pack must be a dict/object")

    # top-level identity
    if not _is_str(cfg.get("id")):
        _err(errors, "id", "required string")
    if not _is_str(cfg.get("version")):
        _err(errors, "version", "required string")

    # defaults
    defaults = cfg.get("defaults") or {}
    if not isinstance(defaults, dict):
        _err(errors, "defaults", "must be an object")
        defaults = {}

    ms = defaults.get("min_score", 55)
    if not isinstance(ms, int) or not (0 <= ms <= 100):
        _err(errors, "defaults.min_score", "must be int in [0,100]")

    dbn = defaults.get("db_name")
    if dbn is not None and (not _is_str(dbn) or not str(dbn).endswith(".duckdb")):
        _err(errors, "defaults.db_name", "must be a string ending in .duckdb")

    exts = defaults.get("allowed_exts", [".md", ".txt", ".log", ".jsonl", ".csv"])
    if not isinstance(exts, list) or not exts:
        _err(errors, "defaults.allowed_exts", "must be a non-empty list")
    else:
        for i, e in enumerate(exts):
            if not _is_str(e) or not str(e).startswith("."):
                _err(errors, f"defaults.allowed_exts[{i}]", "must be like '.md'")

    # rubric rules
    rubric = cfg.get("rubric") or {}
    if not isinstance(rubric, dict):
        _err(errors, "rubric", "must be an object")
        rubric = {}

    rules = rubric.get("rules") or []
    if not isinstance(rules, list):
        _err(errors, "rubric.rules", "must be a list")
        rules = []

    allowed_kinds = {"regex", "regex_count_ge"}
    for i, r in enumerate(rules):
        path = f"rubric.rules[{i}]"
        if not isinstance(r, dict):
            _err(errors, path, "must be an object")
            continue
        if not _is_str(r.get("id")):
            _err(errors, f"{path}.id", "required string")
        kind = r.get("kind")
        if kind not in allowed_kinds:
            _err(errors, f"{path}.kind", f"must be one of {sorted(allowed_kinds)}")
            continue

        if not isinstance(r.get("weight"), int) or not (-100 <= int(r["weight"]) <= 100):
            _err(errors, f"{path}.weight", "must be int in [-100,100]")

        if not _is_str(r.get("reason")):
            _err(errors, f"{path}.reason", "required string")

        _compile_regex(errors, f"{path}.pattern", r.get("pattern"))

        if kind == "regex_count_ge":
            thr = r.get("threshold")
            if not isinstance(thr, int) or thr < 0:
                _err(errors, f"{path}.threshold", "must be int >= 0")

    # redactions
    redaction = cfg.get("redaction") or {}
    if not isinstance(redaction, dict):
        _err(errors, "redaction", "must be an object")
        redaction = {}

    reds = redaction.get("redactions") or []
    if not isinstance(reds, list):
        _err(errors, "redaction.redactions", "must be a list")
        reds = []

    for i, r in enumerate(reds):
        path = f"redaction.redactions[{i}]"
        if not isinstance(r, dict):
            _err(errors, path, "must be an object")
            continue
        if not _is_str(r.get("id")):
            _err(errors, f"{path}.id", "required string")
        if r.get("kind") != "regex":
            _err(errors, f"{path}.kind", "must be 'regex'")
        _compile_regex(errors, f"{path}.pattern", r.get("pattern"))
        if "replace" in r and not isinstance(r.get("replace"), str):
            _err(errors, f"{path}.replace", "must be a string")

    if errors:
        raise PackValidationError("Invalid pack config:\n- " + "\n- ".join(errors))
