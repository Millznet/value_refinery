import json
from pathlib import Path

from value_refinery.cli import run as cli_run


def test_run_writes_run_summary(tmp_path: Path):
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
        bundle=False,
        bundle_out=None,
        bundle_db=False,
    )

    runs = sorted(out.glob("run_*_secops"))
    assert runs, "no run dirs created"
    run_dir = runs[-1]

    summ = run_dir / "run_summary.json"
    assert summ.exists(), "run_summary.json missing"
    data = json.loads(summ.read_text(encoding="utf-8"))

    assert data["schema_version"] == "run_summary_v1"
    assert data["input"]["files_count"] == 1
    assert isinstance(data["input"]["fingerprint_sha256"], str) and len(data["input"]["fingerprint_sha256"]) == 64
