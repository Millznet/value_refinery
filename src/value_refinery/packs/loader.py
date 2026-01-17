from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Dict

import yaml


def _read_text(rel: str) -> str:
    # wheel-safe
    try:
        p = resources.files("value_refinery.packs").joinpath(rel)
        return p.read_text(encoding="utf-8")
    except Exception:
        # source/editable fallback
        p2 = Path(__file__).resolve().parent / rel
        return p2.read_text(encoding="utf-8")


def load_pack(name: str) -> Dict[str, Any]:
    pack = yaml.safe_load(_read_text(f"{name}/pack.yaml")) or {}
    if not isinstance(pack, dict):
        pack = {}

    # optional extras
    try:
        rub = yaml.safe_load(_read_text(f"{name}/rubric.yaml")) or {}
        if isinstance(rub, dict):
            pack["rubric"] = rub
    except Exception:
        pack["rubric"] = {}

    try:
        red = yaml.safe_load(_read_text(f"{name}/redaction.yaml")) or {}
        if isinstance(red, dict):
            pack["redaction"] = red
    except Exception:
        pack["redaction"] = {}

    return pack
