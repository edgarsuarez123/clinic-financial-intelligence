#!/usr/bin/env bash
# Upgrade existing synthetic configuration and containers without resetting data.
set -euo pipefail
environment=${1:?Usage: bash scripts/upgrade_demo.sh dev\|test username}
username=${2:?Supply the existing demo username}
case "$environment" in dev|test) ;; *) echo "Only dev/test upgrades are supported" >&2; exit 1 ;; esac
cd "$(dirname "$0")/.."
compose=(docker compose --env-file "environments/$environment/.env" -p "clinic-$environment")
config="$PWD/environments/$environment/config"
test -f "$config/ingestion.json"
"${compose[@]}" build migrate api worker web
"${compose[@]}" run --rm migrate
"${compose[@]}" run --rm --user "$(id -u):$(id -g)" -v "$config:/demo-config" migrate python -m app.ingestion.demo "$username" --output /demo-config/ingestion.json --confirm-disposable --extend-existing
"${compose[@]}" run --rm --user "$(id -u):$(id -g)" -v "$config:/demo-config" migrate python -m app.analytics.demo --source /demo-config/ingestion.json --output /demo-config/analytics.json --extend-existing
"${compose[@]}" up -d --force-recreate api worker web
echo "Upgrade complete. Reload the React app on your configured WEB_PORT (dev default: 3000)."
