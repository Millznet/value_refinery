from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from .packs import load_pack
from .core import run_pipeline
from .core.export import export_run
from .core.report import write_report
from . import legacy

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
    defaults = (cfg.get("defaults") or {})
    ms = int(min_score if min_score is not None else defaults.get("min_score", 55))
    allowed_exts = list(defaults.get("allowed_exts", [".md", ".txt", ".log", ".jsonl", ".csv"]))

    run_id = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    out = out.expanduser()
    run_dir = out / f"run_{run_id}_{pack}"
    run_dir.mkdir(parents=True, exist_ok=True)

    db_name = str(defaults.get("db_name", f"{pack}.duckdb"))
    db_path = run_dir / db_name

    manifest: dict = {
        "run_id": run_id,
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
) -> None:
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
