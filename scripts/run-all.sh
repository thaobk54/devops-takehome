#!/usr/bin/env bash
# Entry point for the reviewer. Works from the HOST or inside the toolbox:
#   ./scripts/run-all.sh            (host: re-executes itself inside the toolbox)
# Runs every numbered script (NN-*.sh) in order; all are idempotent.
set -euo pipefail

if ! command -v k3d >/dev/null 2>&1; then
  cd "$(dirname "$0")/.."
  echo "==> host detected: running inside the toolbox container"
  # Git Bash (Windows) rewrites "/work/..." into "C:/Program Files/Git/work/...";
  # disable that conversion so the in-container path reaches docker unchanged.
  export MSYS_NO_PATHCONV=1
  exec docker compose exec -T toolbox bash /work/scripts/run-all.sh "$@"
fi

cd /work
for s in scripts/[0-9][0-9]-*.sh; do
  case "$s" in
    *99-*) continue ;;                      # teardown is never run automatically
  esac
  echo
  echo "################ $s ################"
  bash "$s"
done
echo
echo "ALL SCRIPTS COMPLETED"
