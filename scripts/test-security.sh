#!/usr/bin/env sh

# Run every deterministic automated check for the integrated chat application.
#
# This wrapper executes the Python client, bridge, transport, and backend
# security tests, followed by the React behavior tests, JavaScript lint, and a
# production Vite build. It deliberately doesn't start PostgreSQL or application
# services: backend database and external reputation behavior are replaced with
# deterministic fakes in pytest. Use live-security-smoke.py after starting the
# real server and bridge when you want a socket-level integration check.
#
# Prerequisites:
#   1. Create .venv and install requirements-dev.txt.
#   2. Run `npm --prefix client/ui ci`.
#
# The script may be invoked from any directory. It resolves the repository root
# from its own location and exits immediately when a command fails.

set -eu

# Resolve an absolute root without depending on the caller's working directory.
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# Give focused setup errors instead of an opaque command-not-found failure.
if [ ! -x "$project_root/.venv/bin/python" ]; then
  echo "Missing .venv. Create it and install requirements-dev.txt first." >&2
  exit 1
fi

if [ ! -d "$project_root/client/ui/node_modules" ]; then
  echo "Missing UI dependencies. Run: npm --prefix client/ui ci" >&2
  exit 1
fi

cd "$project_root"

# PYTHONPATH keeps namespace-package imports stable across Python/pytest launch
# modes. The remaining commands use package scripts pinned by package-lock.json.
PYTHONPATH="$project_root" .venv/bin/python -m pytest -q
npm --prefix client/ui test
npm --prefix client/ui run lint
npm --prefix client/ui run build
