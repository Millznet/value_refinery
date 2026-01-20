from pathlib import Path
import yaml
from typer.testing import CliRunner

from value_refinery.cli import app
from value_refinery.packs import load_pack


def test_pack_spec_file_path_does_not_pollute_run_dir(tmp_path: Path):
    runner = CliRunner()

    raw = tmp_path / "raw"
    out = tmp_path / "artifacts"
    raw.mkdir()
    out.mkdir()

    (raw / "a.md").write_text("# T\n\n## A\nhello\n", encoding="utf-8")

    cfg = load_pack("secops")
    pack_path = tmp_path / "secops.yaml"
    pack_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "run",
            "--pack",
            str(pack_path),
            "--input",
            str(raw),
            "--out",
            str(out),
            "--min-score",
            "0",
            "--limit",
            "0",
            "--no-show",
            "--bundle",
            "--no-bundle-db",
        ],
    )
    assert res.exit_code == 0, res.output

    runs = sorted(out.glob("run_*_secops"))
    assert runs, "expected run dir named with pack_id (secops)"
    assert runs[-1].parent == out, "run dir should be a direct child of out/ (no nested pack path dirs)"

    bundles = sorted((out / "bundles").glob("run_*_secops.zip"))
    assert bundles, "expected bundle name run_<id>_secops.zip"
