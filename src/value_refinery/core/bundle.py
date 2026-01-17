from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_bundle(*, run_dir: Path, out_path: Path | None, include_db: bool = True) -> Path:
    """Create a zip bundle for a run directory.

    Bundle includes:
      - run_manifest.json
      - report.md
      - exports/* (jsonl exports)
      - optional *.duckdb
      - bundle_manifest.json (inside zip)
    """

    run_dir = run_dir.expanduser().resolve()
    if not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"run_dir not found or not a directory: {run_dir}")

    # Output path semantics:
    # - None => <run_dir>/bundle.zip
    # - existing dir => <dir>/<run_dir.name>.zip
    # - non-existing path with no suffix => treat as dir => <path>/<run_dir.name>.zip
    # - file path => ensure .zip suffix
    if out_path is None:
        zip_path = run_dir / "bundle.zip"
    else:
        out_path = out_path.expanduser()
        if out_path.exists() and out_path.is_dir():
            out_path.mkdir(parents=True, exist_ok=True)
            zip_path = out_path / f"{run_dir.name}.zip"
        elif out_path.suffix == "":
            # treat no-suffix path as a directory (common CLI usage)
            out_path.mkdir(parents=True, exist_ok=True)
            zip_path = out_path / f"{run_dir.name}.zip"
        else:
            zip_path = out_path
            if zip_path.suffix != ".zip":
                zip_path = zip_path.with_suffix(".zip")

    zip_path.parent.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []

    # core run artifacts
    for name in ["run_manifest.json", "report.md"]:
        p = run_dir / name
        if p.exists() and p.is_file():
            files.append(p)

    # exports
    exports_dir = run_dir / "exports"
    if exports_dir.exists() and exports_dir.is_dir():
        files.extend([p for p in exports_dir.rglob("*") if p.is_file()])

    # optionally include db
    if include_db:
        files.extend([p for p in run_dir.glob("*.duckdb") if p.is_file()])

    # stable order + de-dupe
    uniq: dict[str, Path] = {}
    for p in files:
        rp = p.resolve()
        uniq[str(rp)] = rp
    files = sorted(uniq.values(), key=lambda p: p.as_posix())

    manifest = {
        "bundle_version": "0.0.1",
        "created_at": int(time.time()),
        "run_dir": str(run_dir),
        "files": [],
    }

    for p in files:
        rel = p.relative_to(run_dir).as_posix()
        st = p.stat()
        manifest["files"].append(
            {
                "path": rel,
                "bytes": int(st.st_size),
                "sha256": _sha256_file(p),
            }
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("bundle_manifest.json", json.dumps(manifest, indent=2))
        for p in files:
            arc = p.relative_to(run_dir).as_posix()
            z.write(p, arcname=arc)

    return zip_path
