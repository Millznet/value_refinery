from pathlib import Path
from value_refinery.cli import init_cmd


def test_init_creates_scaffold(tmp_path: Path):
    proj = tmp_path / "proj"
    init_cmd(dir=proj, pack="secops", force=False)

    assert (proj / "raw" / "sample.md").exists()
    assert (proj / "packs" / "secops.yaml").exists()
    assert (proj / "artifacts").exists()
    assert (proj / "README.md").exists()
