from pathlib import Path
import yaml

from value_refinery.cli import cli_run
from value_refinery.packs import load_pack


def test_pack_spec_file_path_does_not_pollute_run_dir(tmp_path: Path):
    raw = tmp_path / "raw"
    out = tmp_path / "artifacts"
    raw.mkdir()
    out.mkdir()

    (raw / "a.md").write_text("# T\n\n## A\nhello\n", encoding="utf-8")

    cfg = load_pack("secops")
    pack_path = tmp_path / "secops.yaml"
    pack_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    cli_run(
        pack=str(pack_path),
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
    assert runs, "expected run dir named with pack_id (secops)"
    assert runs[-1].parent == out, "run dir should be a direct child (no nested pack path dirs)"

    bundles = sorted((out / "bundles").glob("run_*_secops.zip"))
    assert bundles, "expected bundle name run_<id>_secops.zip"
