#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Error: cloudflared is not installed on this machine."
  echo
  echo "Install cloudflared, then run this script again."
  echo "It will create an HTTPS link for ClubsHub on port 8002."
  exit 1
fi

echo "Starting HTTPS tunnel for ClubsHub..."
echo "Keep this terminal open while you use the app on your phone."
echo

exec cloudflared tunnel --url http://127.0.0.1:8002
