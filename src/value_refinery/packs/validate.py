from __future__ import annotations

from typing import Any


_ALLOWED_RULE_KINDS = {"regex", "regex_count_ge"}
_ALLOWED_REDACTION_KINDS = {"regex"}


def _is_str(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def validate_pack_dict(cfg: dict[str, Any]) -> list[str]:
    """
    Returns a list of human-friendly validation errors.
    Empty list => valid.
    """
    errs: list[str] = []

    if not isinstance(cfg, dict):
        return ["pack must be a mapping/object"]

    # required top-level fields
    for k in ("id", "version"):
        if not _is_str(cfg.get(k)):
            errs.append(f"missing/invalid top-level '{k}' (must be non-empty string)")

    defaults = cfg.get("defaults", {})
    if defaults is not None and not isinstance(defaults, dict):
        errs.append("defaults must be an object if present")

    rubric = cfg.get("rubric", {})
    if rubric is not None and not isinstance(rubric, dict):
        errs.append("rubric must be an object if present")

    redaction = cfg.get("redaction", {})
    if redaction is not None and not isinstance(redaction, dict):
        errs.append("redaction must be an object if present")

    # defaults checks (soft)
    if isinstance(defaults, dict):
        if "min_score" in defaults and not isinstance(defaults["min_score"], int):
            errs.append("defaults.min_score must be int")
        if "db_name" in defaults and not _is_str(defaults["db_name"]):
            errs.append("defaults.db_name must be non-empty string")
        if "allowed_exts" in defaults:
            ae = defaults["allowed_exts"]
            if not isinstance(ae, list) or not all(isinstance(x, str) for x in ae):
                errs.append("defaults.allowed_exts must be list[str]")

    # rubric checks
    if isinstance(rubric, dict):
        if "base_score" in rubric and not isinstance(rubric["base_score"], int):
            errs.append("rubric.base_score must be int")
        rules = rubric.get("rules", [])
        if rules is not None:
            if not isinstance(rules, list):
                errs.append("rubric.rules must be a list")
            else:
                for i, r in enumerate(rules):
                    if not isinstance(r, dict):
                        errs.append(f"rubric.rules[{i}] must be an object")
                        continue
                    rid = r.get("id")
                    kind = r.get("kind")
                    if not _is_str(rid):
                        errs.append(f"rubric.rules[{i}].id must be non-empty string")
                    if kind not in _ALLOWED_RULE_KINDS:
                        errs.append(
                            f"rubric.rules[{i}].kind must be one of {_ALLOWED_RULE_KINDS}"
                        )
                    if not isinstance(r.get("weight"), int):
                        errs.append(f"rubric.rules[{i}].weight must be int")
                    if not _is_str(r.get("reason")):
                        errs.append(f"rubric.rules[{i}].reason must be non-empty string")

                    # kind-specific
                    if kind in {"regex", "regex_count_ge"}:
                        if not _is_str(r.get("pattern")):
                            errs.append(f"rubric.rules[{i}].pattern must be non-empty string")
                    if kind == "regex_count_ge":
                        if not isinstance(r.get("threshold"), int):
                            errs.append(f"rubric.rules[{i}].threshold must be int")

    # redaction checks
    if isinstance(redaction, dict):
        reds = redaction.get("redactions", [])
        if reds is not None:
            if not isinstance(reds, list):
                errs.append("redaction.redactions must be a list")
            else:
                for i, rr in enumerate(reds):
                    if not isinstance(rr, dict):
                        errs.append(f"redaction.redactions[{i}] must be an object")
                        continue
                    if not _is_str(rr.get("id")):
                        errs.append(f"redaction.redactions[{i}].id must be non-empty string")
                    kind = rr.get("kind")
                    if kind not in _ALLOWED_REDACTION_KINDS:
                        errs.append(
                            f"redaction.redactions[{i}].kind must be one of {_ALLOWED_REDACTION_KINDS}"
                        )
                    if not _is_str(rr.get("pattern")):
                        errs.append(f"redaction.redactions[{i}].pattern must be non-empty string")
                    if "replace" in rr and not isinstance(rr.get("replace"), str):
                        errs.append(f"redaction.redactions[{i}].replace must be string")

    return errs
