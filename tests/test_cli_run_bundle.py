from pathlib import Path
import json

from value_refinery.cli import run as cli_run


def test_cli_run_creates_bundle(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "artifacts"
    raw.mkdir(parents=True)
    out.mkdir(parents=True)

    (raw / "sample.md").write_text("# Title\n\n## A\nhello\n\n## B\nworld\n", encoding="utf-8")

    cli_run(
        pack="secops",
        input=raw,
        out=out,
        min_score=0,
        limit=0,
        show=False,
        bundle=True,
        bundle_out=None,
        bundle_db=False,
    )

    runs = sorted(out.glob("run_*_secops"))
    assert runs, "no run dirs created"
    run_dir = runs[-1]

    man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert man["schema_version"] == "run_manifest_v1"
    assert "bundle" in man
    assert Path(man["bundle"]).exists()
