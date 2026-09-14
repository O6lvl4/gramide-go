#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${ALMIDE_BIN:-almide}"

"$compiler" test
"$compiler" build cli/main.almd --release -o gramide_go
./gramide_go gen-table | diff -u src/table.almd - \
  || { echo "src/table.almd is not what the grammar compiles to: ./gramide_go gen-table > src/table.almd"; exit 1; }
python3 ci/smoke.py
python3 ci/symbols.py

# A per-file ratchet, not a target. Each file is held where it stands, so a
# clean one cannot rot up to the worst one. Numbers only ever fall;
# --write-baseline records a fall.
if command -v codopsy-almd >/dev/null; then cx=codopsy-almd
elif command -v codopsy_almd >/dev/null; then cx=codopsy_almd
else cx=""; fi
if [ -n "$cx" ]; then
  "$cx" --quiet --baseline .codopsy-almd.json src/
else
  echo "codopsy-almd not on PATH: structural check skipped (almide install github.com/O6lvl4/codopsy-almd)"
fi
