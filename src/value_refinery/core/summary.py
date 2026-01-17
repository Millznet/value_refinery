from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .chunk import iter_input_files


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_fingerprint(entries: list[dict[str, Any]]) -> str:
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _relpath(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except Exception:
        return p.as_posix()


def summarize_inputs(*, input_root: Path, allowed_exts: list[str]) -> dict[str, Any]:
    input_root = input_root.expanduser().resolve()
    files: list[Path] = sorted(iter_input_files(input_root, allowed_exts), key=lambda p: p.as_posix())

    entries: list[dict[str, Any]] = []
    for p in files:
        st = p.stat()
        entries.append(
            {
                "path": _relpath(p, input_root),
                "bytes": int(st.st_size),
                "sha256": _sha256_file(p),
            }
        )

    return {
        "root": str(input_root),
        "files_count": len(entries),
        "files": entries,
        "fingerprint_sha256": _stable_fingerprint(entries),
    }


def summarize_run_outputs(*, run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()

    paths: list[Path] = []
    for name in ["run_manifest.json", "run_summary.json", "report.md"]:
        p = run_dir / name
        if p.exists() and p.is_file():
            paths.append(p)

    exports_dir = run_dir / "exports"
    if exports_dir.exists() and exports_dir.is_dir():
        paths.extend([p for p in exports_dir.rglob("*") if p.is_file()])

    paths.extend([p for p in run_dir.glob("*.duckdb") if p.is_file()])

    uniq: dict[str, Path] = {}
    for p in paths:
        rp = p.resolve()
        uniq[str(rp)] = rp
    paths = sorted(uniq.values(), key=lambda p: p.as_posix())

    entries: list[dict[str, Any]] = []
    for p in paths:
        st = p.stat()
        entries.append(
            {
                "path": _relpath(p, run_dir),
                "bytes": int(st.st_size),
                "sha256": _sha256_file(p),
            }
        )

    return {
        "run_dir": str(run_dir),
        "files_count": len(entries),
        "files": entries,
        "fingerprint_sha256": _stable_fingerprint(entries),
    }


def _count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    n = 0
    with p.open("rb") as f:
        for _ in f:
            n += 1
    return n


def write_run_summary(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    input_root: Path,
    allowed_exts: list[str],
    started_at: float,
    bundle_enabled: bool,
    bundle_include_db: bool,
    bundle_zip: Path | None = None,
) -> Path:
    run_dir = run_dir.expanduser().resolve()
    summary_path = run_dir / "run_summary.json"

    inputs = summarize_inputs(input_root=input_root, allowed_exts=allowed_exts)

    chunks_kept = run_dir / "exports" / "chunks_kept.jsonl"
    decisions = run_dir / "exports" / "decisions.jsonl"
    counts = {
        "chunks_kept_lines": _count_lines(chunks_kept),
        "decisions_lines": _count_lines(decisions),
    }

    base: dict[str, Any] = {
        "schema_version": "run_summary_v1",
        "run_id": manifest.get("run_id"),
        "created_at": int(time.time()),
        "pack_id": (manifest.get("pack") or {}).get("id"),
        "pack_version": (manifest.get("pack") or {}).get("version"),
        "min_score": manifest.get("min_score"),
        "limit": manifest.get("limit"),
        "allowed_exts": allowed_exts,
        "input": inputs,
        "counts": counts,
        "timing": {"total_seconds": round(time.time() - started_at, 6)},
        "bundle": {
            "enabled": bool(bundle_enabled),
            "include_db": bool(bundle_include_db),
            "zip": (str(bundle_zip) if bundle_zip is not None else None),
        },
    }

    # write once so run_outputs can include it deterministically
    summary_path.write_text(json.dumps(base, indent=2), encoding="utf-8")

    base["outputs"] = summarize_run_outputs(run_dir=run_dir)
    base["timing"]["total_seconds"] = round(time.time() - started_at, 6)

    summary_path.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return summary_path
