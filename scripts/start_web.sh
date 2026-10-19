#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
python_bin="${RECEIPT_PYTHON:-$project_root/.venv/bin/python}"
export APP_HOST="${APP_HOST:-0.0.0.0}"
exec "$python_bin" app.py
