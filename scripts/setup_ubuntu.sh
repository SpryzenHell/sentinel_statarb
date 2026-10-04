#!/usr/bin/env bash
set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This helper supports Debian/Ubuntu systems only." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y   build-essential   cmake   git   pkg-config   libzmq3-dev   python3   python3-pip   python3-venv

python3 -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12 or newer is required"' \
  || { echo "Python 3.12 or newer is required." >&2; exit 1; }

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[full]'

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel

echo
echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
echo "Verify with: python scripts/verify_installation.py"
echo "Run tests with: make test"
echo "Run the backtest with: make backtest"
