#!/usr/bin/env bash
set -euo pipefail

echo "== Value Refinery smoke: secops =="
# repo root (works even if you run from elsewhere)
if command -v git >/dev/null 2>&1 && git rev-parse --show-toplevel >/dev/null 2>&1; then
  ROOT="$(git rev-parse --show-toplevel)"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
cd "$ROOT"
echo "root: $ROOT"

# activate venv if present
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "venv: ON ($(python -V))"
else
  echo "WARN: .venv/bin/activate not found; using system python"
fi

echo
echo "== 1) tests =="
python -m pytest -q

echo
echo "== 2) compile sanity =="
python -m py_compile src/value_refinery/cli.py \
  src/value_refinery/core/pipeline.py \
  src/value_refinery/core/chunk.py \
  src/value_refinery/core/bundle.py

echo
echo "== 3) install editable =="
python -m pip install -e .

echo
echo "== 4) run pipeline (secops) + bundle (no db) =="
value-refinery run \
  --pack secops \
  --input data/raw \
  --out data/artifacts \
  --show \
  --bundle \
  --no-bundle-db

echo
echo "== 5) show latest run manifest + bundles =="
latest="$(ls -1dt data/artifacts/run_*_secops | head -n 1)"
echo "latest=$latest"
sed -n '1,220p' "$latest/run_manifest.json" || true

echo
echo "bundles:"
ls -lh data/artifacts/bundles 2>/dev/null | tail -n 20 || echo "(none yet)"

echo
echo "== done =="
