from pathlib import Path
from typer.testing import CliRunner

from value_refinery.cli import app


def _latest_run_dir(out: Path) -> Path:
    runs = sorted(out.glob("run_*_secops"))
    assert runs, "no run dirs created"
    return runs[-1]


def test_vrignore_excludes_files(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "artifacts"
    raw.mkdir()
    out.mkdir()

    (raw / "keep.md").write_text("# T\n\n## A\nhello\n", encoding="utf-8")
    (raw / "secret.md").write_text("# SECRET\n\npw=123\n", encoding="utf-8")
    (raw / ".vrignore").write_text("secret.md\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "run",
            "--pack",
            "secops",
            "--input",
            str(raw),
            "--out",
            str(out),
            "--min-score",
            "0",
            "--limit",
            "0",
            "--bundle",
            "--no-bundle-db",
        ],
    )
    assert res.exit_code == 0, res.output

    run_dir = _latest_run_dir(out)
    decisions = (run_dir / "exports" / "decisions.jsonl").read_text(encoding="utf-8")
    assert "secret.md" not in decisions
    assert "keep.md" in decisions


def test_exclude_flag_excludes_files(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "artifacts"
    raw.mkdir()
    out.mkdir()

    (raw / "a.md").write_text("# A\n\n## X\nhello\n", encoding="utf-8")
    (raw / "b.md").write_text("# B\n\n## Y\nworld\n", encoding="utf-8")

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "run",
            "--pack",
            "secops",
            "--input",
            str(raw),
            "--out",
            str(out),
            "--min-score",
            "0",
            "--limit",
            "0",
            "--exclude",
            "b.md",
            "--bundle",
            "--no-bundle-db",
        ],
    )
    assert res.exit_code == 0, res.output

    run_dir = _latest_run_dir(out)
    decisions = (run_dir / "exports" / "decisions.jsonl").read_text(encoding="utf-8")
    assert "b.md" not in decisions
    assert "a.md" in decisions
