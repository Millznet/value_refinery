from pathlib import Path
import json
from typer.testing import CliRunner

from value_refinery.cli import app

runner = CliRunner()


def test_explain_run_dir_reads_decisions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260101_000000_secops"
    exports = run_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)

    decisions = exports / "decisions.jsonl"
    decisions.write_text(
        "\n".join(
            [
                json.dumps({"decision": "kept", "path": "a.md", "score": 80}),
                json.dumps({"decision": "dropped_low", "path": "b.md", "score": 10, "reason": "low_score"}),
                json.dumps({"decision": "excluded", "path": "secret.md", "pattern": "secret*"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["explain", "--run-dir", str(run_dir), "--limit", "10"])
    assert res.exit_code == 0, res.output
    assert "dropped_low" in res.output
    assert "excluded" in res.output


def test_explain_filters_and_json(tmp_path: Path) -> None:
    d = tmp_path / "decisions.jsonl"
    d.write_text(
        "\n".join(
            [
                json.dumps({"decision": "kept", "path": "a.md"}),
                json.dumps({"decision": "dropped_low", "path": "b.md", "reason": "low_score"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    res = runner.invoke(app, ["explain", "--decisions", str(d), "--decision", "dropped_low", "--json"])
    assert res.exit_code == 0, res.output
    assert "dropped_low" in res.output
    assert "kept" not in res.output
