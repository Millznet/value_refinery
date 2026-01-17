from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .builtins import BUILTIN_PACKS
from .validate import validate_pack_dict

PACKS_DIR = Path(__file__).parent


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _load_pack_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"pack file not found: {path}")

    suf = path.suffix.lower()
    if suf in {".yaml", ".yml"}:
        cfg = yaml.safe_load(_read_text(path)) or {}
    elif suf == ".json":
        cfg = json.loads(_read_text(path))
    else:
        raise ValueError(f"unsupported pack extension: {path.suffix} (use .yaml/.yml/.json)")

    if not isinstance(cfg, dict):
        raise ValueError("pack file must parse to an object (mapping)")
    return cfg


def _resolve_builtin_pack_file(spec: str) -> Path | None:
    for ext in (".yaml", ".yml", ".json"):
        p = PACKS_DIR / f"{spec}{ext}"
        if p.exists() and p.is_file():
            return p
    return None


def list_builtin_packs() -> list[str]:
    out: set[str] = set(BUILTIN_PACKS.keys())
    for p in PACKS_DIR.glob("*.yaml"):
        out.add(p.stem)
    for p in PACKS_DIR.glob("*.yml"):
        out.add(p.stem)
    for p in PACKS_DIR.glob("*.json"):
        out.add(p.stem)
    out.discard("__init__")
    out.discard("validate")
    out.discard("builtins")
    return sorted(out)


def load_pack(spec: str | Path, *, validate: bool = True) -> dict[str, Any]:
    """
    Load a pack either by builtin id (e.g. "secops") or by file path
    (e.g. "./packs/acme.yaml").

    validate=True => raises ValueError with readable errors.
    """
    path: Path | None = None

    if isinstance(spec, Path):
        path = spec
    else:
        maybe = Path(spec).expanduser()
        if maybe.exists() or any(spec.lower().endswith(ext) for ext in (".yaml", ".yml", ".json")):
            path = maybe
        else:
            path = _resolve_builtin_pack_file(spec)

    if path is not None:
        cfg = _load_pack_file(path)
    else:
        # fallback builtins (important for packaged installs that omit YAML)
        if isinstance(spec, str) and spec in BUILTIN_PACKS:
            cfg = BUILTIN_PACKS[spec]
        else:
            raise FileNotFoundError(
                f"unknown pack '{spec}'. builtin={list_builtin_packs()} or pass a file path"
            )

    if validate:
        errs = validate_pack_dict(cfg)
        if errs:
            raise ValueError("invalid pack:\n- " + "\n- ".join(errs))

    return cfg
