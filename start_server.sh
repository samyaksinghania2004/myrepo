#!/usr/bin/env bash
# This script is intended for development use only. It starts the Django development server on
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Error: .venv not found in $ROOT_DIR"
  exit 1
fi
source .venv/bin/activate

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN=".venv/bin/python3"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: no Python interpreter found in $ROOT_DIR/.venv/bin"
  exit 1
fi

if [[ ! -f ".env" ]]; then
  echo "Error: .env not found in $ROOT_DIR"
  exit 1
fi
set -a
source .env
set +a

echo "Checking for missing migrations..."
if ! "$PYTHON_BIN" manage.py makemigrations --check --dry-run >/dev/null 2>&1; then
  echo
  echo "Model changes detected that are not reflected in migrations."
  echo "Run this first:"
  echo "  $PYTHON_BIN manage.py makemigrations"
  echo "  $PYTHON_BIN manage.py migrate"
  exit 1
fi

echo "Running Django checks..."
"$PYTHON_BIN" manage.py check

echo "Applying migrations..."
"$PYTHON_BIN" manage.py migrate

echo "Collecting static files..."
"$PYTHON_BIN" manage.py collectstatic --noinput

echo "Stopping old dev server if running..."
pkill -f "manage.py runserver 0.0.0.0:8002" 2>/dev/null || true

echo "Starting Django dev server on 0.0.0.0:8002 ..."
exec "$PYTHON_BIN" manage.py runserver 0.0.0.0:8002
