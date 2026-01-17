from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .validate import validate_pack_dict


PACKS_DIR = Path(__file__).parent


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _load_pack_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"pack file not found: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        cfg = yaml.safe_load(_read_text(path)) or {}
    elif path.suffix.lower() == ".json":
        cfg = json.loads(_read_text(path))
    else:
        raise ValueError(f"unsupported pack extension: {path.suffix} (use .yaml/.yml/.json)")

    if not isinstance(cfg, dict):
        raise ValueError("pack file must parse to a JSON/YAML object (mapping)")
    return cfg


def _resolve_builtin_pack(spec: str) -> Path | None:
    # allow "secops" -> packs/secops.yaml (or yml/json)
    candidates = [
        PACKS_DIR / f"{spec}.yaml",
        PACKS_DIR / f"{spec}.yml",
        PACKS_DIR / f"{spec}.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


def list_builtin_packs() -> list[str]:
    out: set[str] = set()
    for p in PACKS_DIR.glob("*.yaml"):
        out.add(p.stem)
    for p in PACKS_DIR.glob("*.yml"):
        out.add(p.stem)
    for p in PACKS_DIR.glob("*.json"):
        out.add(p.stem)
    # ignore python modules
    out.discard("__init__")
    out.discard("validate")
    return sorted(out)


def load_pack(spec: str | Path, *, validate: bool = True) -> dict[str, Any]:
    """
    Load a pack either by builtin id (e.g. "secops") or by file path
    (e.g. "./packs/acme.yaml").

    If validate=True, raises ValueError with a readable message on invalid packs.
    """
    path: Path | None = None

    if isinstance(spec, Path):
        path = spec
    else:
        # if it looks like a path or exists on disk, treat as file path
        maybe = Path(spec).expanduser()
        if maybe.exists():
            path = maybe
        elif any(spec.lower().endswith(ext) for ext in (".yaml", ".yml", ".json")):
            path = maybe
        else:
            # builtin id
            path = _resolve_builtin_pack(spec)

    if path is None:
        raise FileNotFoundError(
            f"unknown pack '{spec}'. builtin={list_builtin_packs()} or pass a file path"
        )

    cfg = _load_pack_file(path)

    if validate:
        errs = validate_pack_dict(cfg)
        if errs:
            msg = "invalid pack:\n- " + "\n- ".join(errs)
            raise ValueError(msg)

    return cfg
