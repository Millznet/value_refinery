from __future__ import annotations

import json
import time
from pathlib import Path

from pathlib import Path
import yaml
import typer


from .packs import load_pack
from .core import run_pipeline
from .core.export import export_run
from .core.report import write_report
from . import legacy

import os

def _input_controls_from_env() -> dict:
    """
    Snapshot input-control env vars used by core.chunk.iter_input_files so the run manifest
    records what filtering/limits were applied.
    """
    import os

    def _int(name: str) -> int:
        v = (os.environ.get(name) or "").strip()
        if not v:
            return 0
        try:
            return int(v)
        except ValueError:
            return 0

    exclude_raw = os.environ.get("VR_EXCLUDE", "")
    exclude = []
    for line in exclude_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        exclude.append(line)

    ignore_file = os.environ.get("VR_IGNORE_FILE") or None
    no_ignore_file = os.environ.get("VR_NO_IGNORE_FILE") in ("1", "true", "TRUE", "yes", "YES")

    return {
        "exclude": exclude,
        "ignore_file": ignore_file,
        "no_ignore_file": bool(no_ignore_file),
        "max_files": _int("VR_MAX_FILES"),
        "max_bytes": _int("VR_MAX_BYTES"),
    }

app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(legacy.app, name="legacy")


# ----------------------------
# Pure functions (safe to call from tests / Python)
# ----------------------------
def run(
    *,
    pack: str = "secops",
    input: Path = Path("data/raw"),
    out: Path = Path("data/artifacts"),
    min_score: int | None = None,
    limit: int = 0,
    show: bool = False,
    bundle: bool = False,
    bundle_out: Path | None = None,
    bundle_db: bool = True,
) -> None:
    started_at = time.time()
    cfg = load_pack(pack)
    pack_id = str(cfg.get('id') or 'pack')
    # pack_spec may be a file path; pack_id is the stable short tag used for naming

    defaults = (cfg.get("defaults") or {})
    ms = int(min_score if min_score is not None else defaults.get("min_score", 55))
    allowed_exts = list(defaults.get("allowed_exts", [".md", ".txt", ".log", ".jsonl", ".csv"]))

    run_id_base = time.strftime("%Y%m%d_%H%M%S", time.localtime(started_at))

    rid_ms = int((started_at - int(started_at)) * 1000)
    run_id = f"{run_id_base}_{rid_ms:03d}"
    out = out.expanduser()
    run_dir = out / f"run_{run_id}_{pack_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    db_name = str(defaults.get("db_name", f"{pack}.duckdb"))
    db_path = run_dir / db_name

    manifest: dict = {
        "run_id": run_id,
        "pack_spec": pack,
        "schema_version": "run_manifest_v1",
        "pack": cfg,
        "input": str(input.expanduser()),
        "db": str(db_path),
        "min_score": ms,
        "limit": limit,
        "allowed_exts": allowed_exts,
        "created_at": int(time.time()),
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest["input_controls"] = _input_controls_from_env()

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    run_pipeline(
        run_id=run_id,
        pack_id=str(cfg.get("id", pack)),
        pack=cfg,
        input=input,
        db=db_path,
        out_dir=run_dir,
        manifest_path=manifest_path,
        min_score=ms,
        limit=limit,
        show=show,
        allowed_exts=allowed_exts,
    )

    paths = export_run(db_path=db_path, run_id=run_id, out_dir=run_dir, min_score=ms)
    rep = write_report(db_path=db_path, run_id=run_id, out_dir=run_dir, min_score=ms)
    # deterministic run summary (inputs/outputs fingerprints)
    from .core.summary import write_run_summary
    summary_path = write_run_summary(
        run_dir=run_dir,
        manifest=manifest,
        input_root=input,
        allowed_exts=allowed_exts,
        started_at=started_at,
        bundle_enabled=bundle,
        bundle_include_db=bundle_db,
        bundle_zip=None,
    )
    manifest["run_summary"] = str(summary_path)


    bundle_zip: Path | None = None
    if bundle:
        bundles_dir = out / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        if bundle_out is None:
            bundle_out = bundles_dir / f"run_{run_id}_{pack_id}.zip"

        from .core.bundle import create_bundle

        bundle_target = (bundle_out if bundle_out is not None else (out / "bundles")).expanduser()
        bundle_zip = create_bundle(run_dir=run_dir, out_path=bundle_target, include_db=bundle_db)
        typer.echo(f"bundle: {bundle_zip}")

    # update manifest with final artifact paths (and bundle if present)
    manifest["exports_dir"] = str(paths["exports_dir"])
    manifest["chunks_kept"] = str(paths["chunks_kept"])
    manifest["decisions"] = str(paths["decisions"])
    manifest["report"] = str(rep["report_md"])
    if bundle_zip is not None:
        manifest["bundle"] = str(bundle_zip)

    # refresh summary with bundle path (run_dir copy only)
    if "run_summary" in manifest:
        from .core.summary import write_run_summary
        write_run_summary(
            run_dir=run_dir,
            manifest=manifest,
            input_root=input,
            allowed_exts=allowed_exts,
            started_at=started_at,
            bundle_enabled=bundle,
            bundle_include_db=bundle_db,
            bundle_zip=bundle_zip,
        )

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    typer.echo(f"manifest: {manifest_path}")
    typer.echo(f"exports: {paths['exports_dir']}")
    typer.echo(f"chunks_kept: {paths['chunks_kept']}")
    typer.echo(f"decisions: {paths['decisions']}")
    typer.echo(f"report: {rep['report_md']}")


def bundle(*, run_dir: Path, out: Path | None = None, include_db: bool = True) -> Path:
    """Pure bundle helper (safe for tests/python)."""
    from .core.bundle import create_bundle

    zip_path = create_bundle(run_dir=run_dir, out_path=out, include_db=include_db)
    typer.echo(f"bundle: {zip_path}")
    return zip_path


# ----------------------------
# Typer command wrappers (CLI only)
# ----------------------------
@app.command("run")
def run_cmd(
    pack: str = typer.Option("secops", "--pack", "-p"),
    input: Path = typer.Option(Path("data/raw"), "--input", "-i"),
    out: Path = typer.Option(Path("data/artifacts"), "--out", "-o"),
    min_score: int | None = typer.Option(None, "--min-score"),
    limit: int = typer.Option(0, "--limit"),
    show: bool = typer.Option(False, "--show"),
    bundle: bool = typer.Option(False, "--bundle"),
    bundle_out: Path | None = typer.Option(None, "--bundle-out"),
    bundle_db: bool = typer.Option(True, "--bundle-db/--no-bundle-db"),


    exclude: list[str] = typer.Option([], "--exclude", help="Glob pattern to exclude (repeatable)"),

    ignore_file: Path | None = typer.Option(None, "--ignore-file", help="Ignore file override (default: .vrignore under input root)"),

    no_ignore_file: bool = typer.Option(False, "--no-ignore-file", help="Disable .vrignore usage"),

    max_files: int = typer.Option(0, "--max-files", help="Max files to read (0 = unlimited)"),

    max_bytes: int = typer.Option(0, "--max-bytes", help="Max total bytes to read (0 = unlimited)"),


    dry_run: bool = typer.Option(False, "--dry-run", help="Scan input discovery (ignore/exclude/limits) and exit"),

    dry_run_limit: int = typer.Option(50, "--dry-run-limit", help="Max paths to print per category (0 = none)"),
    dry_run_json: bool = typer.Option(False, "--dry-run-json", help="Emit dry-run scan as JSON to stdout"),
    dry_run_out: Path | None = typer.Option(None, "--dry-run-out", help="Write dry-run scan JSON to a file"),
) -> None:
    # ---- input controls (ignore/exclude/limits) ----
    # core.chunk.iter_input_files reads these env vars
    if exclude:
        os.environ["VR_EXCLUDE"] = "\n".join(exclude)
    else:
        os.environ.pop('VR_EXCLUDE', None)
    if no_ignore_file:
        os.environ['VR_NO_IGNORE_FILE'] = '1'
        os.environ.pop('VR_IGNORE_FILE', None)
    else:
        os.environ.pop('VR_NO_IGNORE_FILE', None)
        if ignore_file is not None:
            os.environ['VR_IGNORE_FILE'] = str(ignore_file)
        else:
            os.environ.pop('VR_IGNORE_FILE', None)

    if max_files:
        os.environ['VR_MAX_FILES'] = str(max_files)
    else:
        os.environ.pop('VR_MAX_FILES', None)

    if max_bytes:
        os.environ['VR_MAX_BYTES'] = str(max_bytes)
    else:
        os.environ.pop('VR_MAX_BYTES', None)
    # ---- end input controls ----

    # --dry-run: show file discovery results and exit (no DB/run-dir side effects)
    if dry_run or dry_run_json or (dry_run_out is not None):
        from collections import Counter
        from .core.chunk import scan_input_files

        cfg = load_pack(pack)
        defaults = (cfg.get("defaults") or {})
        allowed_exts = list(defaults.get("allowed_exts", [".md", ".txt", ".log", ".jsonl", ".csv"]))

        scan = scan_input_files(input.expanduser(), allowed_exts=allowed_exts)
        ic = _input_controls_from_env()


        # JSON payload (for tooling/UI)
        payload = {
            "pack": {"spec": pack, "id": cfg.get("id", pack), "version": cfg.get("version")},
            "input": str(Path(scan.get("root") or input).expanduser()),
            "allowed_exts": allowed_exts,
            "input_controls": ic,
            "scan": scan,
        }

        if dry_run_out is not None:
            outp = Path(dry_run_out).expanduser()
            outp.parent.mkdir(parents=True, exist_ok=True)
            outp.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        if dry_run_json:
            typer.echo(json.dumps(payload, indent=2))
            raise typer.Exit(code=0)

        typer.echo("== Value Refinery — dry-run (input discovery) ==")
        typer.echo(f"pack: {pack} (id={cfg.get('id', pack)})")
        typer.echo(f"input: {str(Path(scan.get('root') or input).expanduser())}")
        typer.echo(f"allowed_exts: {allowed_exts}")
        typer.echo(f"ignore_file_used: {scan.get('ignore_file_used')}")
        typer.echo(f"no_ignore_file: {scan.get('no_ignore_file')}")
        typer.echo(f"limits: {scan.get('limits')}")
        typer.echo(f"patterns: {len(scan.get('patterns') or [])}")
        if ic.get("exclude"):
            typer.echo(f"exclude (from env): {ic.get('exclude')}")

        kept = scan.get("kept") or []
        excl = scan.get("excluded") or []
        typer.echo(f"kept: {len(kept)}")
        typer.echo(f"excluded: {len(excl)}")
        if scan.get("stopped_early"):
            typer.echo(f"stopped_early: True ({scan.get('stop_reason')})")

        # excluded counts by reason
        c = Counter([e.get("reason") for e in excl])
        if c:
            typer.echo("excluded_by_reason:")
            for reason, cnt in c.most_common():
                typer.echo(f"  - {reason}: {cnt}")

        n = int(dry_run_limit) if dry_run_limit else 0
        if n > 0:
            typer.echo("")
            typer.echo(f"kept (first {n}):")
            for e in kept[:n]:
                typer.echo(f"  + {e.get('rel')}")

            typer.echo("")
            typer.echo(f"excluded (first {n}):")
            for e in excl[:n]:
                pat = e.get("pattern")
                if pat:
                    typer.echo(f"  - {e.get('reason')}: {e.get('rel')}  (pattern={pat})")
                else:
                    typer.echo(f"  - {e.get('reason')}: {e.get('rel')}")

        raise typer.Exit(code=0)


    run(
        pack=pack,
        input=input,
        out=out,
        min_score=min_score,
        limit=limit,
        show=show,
        bundle=bundle,
        bundle_out=bundle_out,
        bundle_db=bundle_db,
    )


@app.command("bundle")
def bundle_cmd(
    run_dir: Path = typer.Option(
        ...,
        "--run-dir",
        help="Run directory like data/artifacts/run_YYYYMMDD_HHMMSS_pack",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Output zip path OR a directory to place <run_dir_name>.zip",
    ),
    include_db: bool = typer.Option(
        True,
        "--include-db/--no-db",
        help="Include the run's DuckDB file in the bundle",
    ),
) -> None:
    bundle(run_dir=run_dir, out=out, include_db=include_db)

pack_app = typer.Typer(no_args_is_help=True)
app.add_typer(pack_app, name="pack")

@pack_app.command("list")
def pack_list() -> None:
    from .packs import list_builtin_packs
    for p in list_builtin_packs():
        typer.echo(p)

@pack_app.command("validate")
def pack_validate(
    pack: str = typer.Argument(..., help="Pack id (builtin) or file path (.yaml/.yml/.json)"),
) -> None:
    from .packs import load_pack
    from .packs.validate import validate_pack_dict

    cfg = load_pack(pack, validate=False)
    
    errs = validate_pack_dict(cfg)
    if errs:
        for e in errs:
            typer.echo(f"- {e}")
        raise typer.Exit(code=2)

    typer.echo("ok")

def main() -> None:
    app()

SAMPLE_MD = """\
# Sample Notes

## Incident: SSH brute force
1) Identify affected host(s)
2) Check auth logs
3) Rotate credentials
"""

README_MD = """\
# Value Refinery

Quick start:
- Put messy notes in `raw/`
- Tune the pack in `packs/secops.yaml`
- Run:
  value-refinery run --pack packs/secops.yaml --input raw --out artifacts --bundle --no-bundle-db --show
"""

@app.command("init")
def init_cmd(
    dir: Path = typer.Option(Path("."), "--dir", "-d", help="Directory to initialize"),
    pack: str = typer.Option("secops", "--pack", help="Pack id or path to a pack YAML"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files"),
) -> None:
    """Initialize a simple project scaffold (raw/, packs/, artifacts/, README)."""
    base = dir.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    raw_dir = base / "raw"
    packs_dir = base / "packs"
    artifacts_dir = base / "artifacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    packs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    sample_path = raw_dir / "sample.md"
    if sample_path.exists() and not force:
        typer.echo(f"exists (use --force): {sample_path}")
        raise typer.Exit(code=2)
    sample_path.write_text(SAMPLE_MD, encoding="utf-8")

    cfg = load_pack(pack)
    pack_out = packs_dir / "secops.yaml"
    if pack_out.exists() and not force:
        typer.echo(f"exists (use --force): {pack_out}")
    else:
        pack_out.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    readme_path = base / "README.md"
    if readme_path.exists() and not force:
        typer.echo(f"exists (use --force): {readme_path}")
    else:
        readme_path.write_text(README_MD, encoding="utf-8")

    typer.echo(f"initialized: {base}")
