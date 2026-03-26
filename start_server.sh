#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "Error: .venv not found in $ROOT_DIR"
  exit 1
fi

source .venv/bin/activate

if [[ ! -f ".env" ]]; then
  echo "Error: .env not found in $ROOT_DIR"
  exit 1
fi

set -a
source .env
set +a

echo "Checking for missing migrations..."
if ! python manage.py makemigrations --check --dry-run >/dev/null 2>&1; then
  echo
  echo "Model changes detected that are not reflected in migrations."
  echo "Run this first:"
  echo "  python manage.py makemigrations"
  echo "  python manage.py migrate"
  exit 1
fi

echo "Running Django checks..."
python manage.py check

echo "Applying migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Stopping old dev server if running..."
pkill -f "manage.py runserver 0.0.0.0:8002" 2>/dev/null || true

echo "Starting Django dev server on 0.0.0.0:8002 ..."
exec python manage.py runserver 0.0.0.0:8002
