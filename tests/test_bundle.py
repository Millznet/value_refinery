from pathlib import Path
from value_refinery.core.bundle import create_bundle


def test_create_bundle_builds_zip(tmp_path: Path):
    run_dir = tmp_path / "run_20260116_999999_secops"
    exports = run_dir / "exports"
    exports.mkdir(parents=True)

    (run_dir / "run_manifest.json").write_text('{"run_id":"x"}', encoding="utf-8")
    (run_dir / "report.md").write_text("# report", encoding="utf-8")
    (exports / "chunks_kept.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (exports / "decisions.jsonl").write_text('{"b":2}\n', encoding="utf-8")
    (run_dir / "secops.duckdb").write_bytes(b"duckdb")

    out = create_bundle(run_dir=run_dir, out_path=tmp_path / "bundles", include_db=True)
    assert out.exists()
    assert out.suffix == ".zip"
