from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from value_refinery.cli import app

runner = CliRunner()

def test_dry_run_json_emits_json_and_no_run_dir(tmp_path: Path) -> None:
    # Use repo sample input, but force --out to a temp dir to ensure no run_* dirs are created.
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    res = runner.invoke(
        app,
        ["run", "--pack", "secops", "--input", "data/raw", "--out", str(out_dir), "--dry-run-json"],
    )
    assert res.exit_code == 0, res.stdout

    payload = json.loads(res.stdout)
    assert payload["pack"]["id"] == "secops"
    assert "scan" in payload and "kept" in payload["scan"]
    assert payload["scan"]["root"].endswith("data/raw") or payload["input"].endswith("data/raw")

    # Dry-run should not create run_* directories under --out
    assert not any(p.name.startswith("run_") for p in out_dir.iterdir())
