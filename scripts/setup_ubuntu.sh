#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This helper supports Debian/Ubuntu systems only." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y build-essential cmake git pkg-config libzmq3-dev python3 python3-pip python3-venv

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[full]'

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Run tests with: python -m pytest -q && ctest --test-dir build --output-on-failure"
echo "Run the backtest with: python scripts/run_backtest.py"
