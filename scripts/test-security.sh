#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ ! -x "$project_root/.venv/bin/python" ]; then
  echo "Missing .venv. Create it and install requirements-dev.txt first." >&2
  exit 1
fi

if [ ! -d "$project_root/client/ui/node_modules" ]; then
  echo "Missing UI dependencies. Run: npm --prefix client/ui ci" >&2
  exit 1
fi

cd "$project_root"
PYTHONPATH="$project_root" .venv/bin/python -m pytest -q
npm --prefix client/ui test
npm --prefix client/ui run lint
npm --prefix client/ui run build
