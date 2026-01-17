from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .chunk import iter_input_files


def _sha256_file(p: Path, *, max_bytes: int | None = None) -> str:
    h = hashlib.sha256()
    read = 0
    with p.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            read += len(chunk)
            if max_bytes is not None and read >= max_bytes:
                break
    return h.hexdigest()


def _stable_fingerprint(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _relpath(p: Path, root: Path) -> str:
    try:
        return p.relative_to(root).as_posix()
    except Exception:
        return p.as_posix()


def _safe_git(args: list[str]) -> str | None:
    try:
        cp = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
        return cp.stdout.strip()
    except Exception:
        return None


def _env_fingerprint() -> dict[str, Any]:
    return {
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "git": {
            "commit": _safe_git(["rev-parse", "HEAD"]),
            "branch": _safe_git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "dirty": (_safe_git(["status", "--porcelain"]) not in (None, "")),
        },
    }


def summarize_inputs(*, input_root: Path, allowed_exts: list[str]) -> dict[str, Any]:
    input_root = input_root.expanduser().resolve()
    files: list[Path] = sorted(iter_input_files(input_root, allowed_exts), key=lambda p: p.as_posix())

    entries: list[dict[str, Any]] = []
    total_bytes = 0

    for p in files:
        st = p.stat()
        total_bytes += int(st.st_size)

        # large-file behavior: partial hash (deterministic-ish) + size/mtime
        max_bytes = None if st.st_size <= 25 * 1024 * 1024 else 4 * 1024 * 1024

        entries.append(
            {
                "path": _relpath(p, input_root),
                "bytes": int(st.st_size),
                "mtime": int(st.st_mtime),
                "sha256": _sha256_file(p, max_bytes=max_bytes),
                "hash_truncated": bool(max_bytes is not None),
            }
        )

    fp = _stable_fingerprint(entries)
    return {
        "root": str(input_root),
        "allowed_exts": list(allowed_exts),
        # test expects files_count
        "files_count": len(entries),
        # keep old naming too (harmless)
        "file_count": len(entries),
        "total_bytes": int(total_bytes),
        "files": entries,
        "fingerprint_sha256": fp,
    }


def summarize_outputs(*, run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()

    candidates: list[Path] = []
    for name in ["run_manifest.json", "run_summary.json", "report.md", "report.json"]:
        p = run_dir / name
        if p.exists() and p.is_file():
            candidates.append(p)

    exports_dir = run_dir / "exports"
    if exports_dir.exists() and exports_dir.is_dir():
        candidates.extend([p for p in exports_dir.rglob("*") if p.is_file()])

    entries: list[dict[str, Any]] = []
    for p in sorted(candidates, key=lambda x: x.as_posix()):
        st = p.stat()
        entries.append(
            {
                "path": _relpath(p, run_dir),
                "bytes": int(st.st_size),
                "mtime": int(st.st_mtime),
                "sha256": _sha256_file(p),
            }
        )

    fp = _stable_fingerprint(entries)
    return {"run_dir": str(run_dir), "artifacts": entries, "fingerprint_sha256": fp}


def write_run_summary(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    input_root: Path,
    allowed_exts: list[str],
    started_at: float,
    bundle_enabled: bool,
    bundle_include_db: bool,
    bundle_zip: Path | None,
) -> Path:
    run_dir = run_dir.expanduser().resolve()
    summary_path = run_dir / "run_summary.json"

    finished_at = time.time()

    pack_cfg = manifest.get("pack") or {}
    pack_fingerprint = _stable_fingerprint(pack_cfg)

    inp = summarize_inputs(input_root=input_root, allowed_exts=allowed_exts)
    outp = summarize_outputs(run_dir=run_dir)

    summary: dict[str, Any] = {
        "schema_version": "run_summary_v1",
        "created_at": int(time.time()),
        "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir),
        "timing": {
            "started_at": float(started_at),
            "finished_at": float(finished_at),
            "duration_ms": int((finished_at - started_at) * 1000),
        },
        "env": _env_fingerprint(),
        "pack": {
            "id": pack_cfg.get("id"),
            "version": pack_cfg.get("version"),
            "fingerprint_sha256": pack_fingerprint,
            "spec": manifest.get("pack_spec"),
        },
        # what tests expect:
        "input": inp,
        "output": outp,
        # aliases (won't hurt anything, helps compatibility):
        "inputs": inp,
        "outputs": outp,
        "bundle": {
            "enabled": bool(bundle_enabled),
            "include_db": bool(bundle_include_db),
            "zip": str(bundle_zip) if bundle_zip else None,
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary_path
