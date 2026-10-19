#!/usr/bin/env bash
# Remove everything (run from the HOST): k3d cluster, toolbox, volumes, network.
# The cluster must go first: its node containers are attached to the compose network.
set -uo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T toolbox k3d cluster delete acme 2>/dev/null \
  || docker rm -f $(docker ps -aq --filter label=k3d.cluster=acme) 2>/dev/null
docker compose down -v --remove-orphans
