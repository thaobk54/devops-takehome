#!/usr/bin/env bash
# Toolbox entrypoint: bootstrap the cluster once (idempotent), then stay alive.
#   progress:  docker compose logs -f toolbox
#   ready:     /root/.kube/ready exists (also the container healthcheck)
#   failed:    /root/.kube/failed exists; fix the cause, then
#              docker compose restart toolbox
#
# NOTE: -E + ERR trap instead of `if ! bootstrap; then` - bash silently
# disables `set -e` inside a function used as an `if` condition, which would
# let a failed `k3d cluster create` continue and still write the ready marker.
set -Eeuo pipefail

CLUSTER=${CLUSTER_NAME:-acme}
KCFG=/root/.kube/config
READY=/root/.kube/ready
FAILED=/root/.kube/failed
mkdir -p /root/.kube
rm -f "$READY" "$FAILED"

log() { echo "[bootstrap $(date +%H:%M:%S)] $*"; }
on_error() {
  log "BOOTSTRAP FAILED (line $1) - see logs above; then: docker compose restart toolbox"
  touch "$FAILED"
  exec sleep infinity          # keep the container up so it can be inspected
}
trap 'on_error $LINENO' ERR

create_cluster() {
  # K3D_EXTRA_ARGS: optional extra flags (e.g. sandbox-specific tweaks).
  # shellcheck disable=SC2086
  k3d cluster create --config /work/bootstrap/k3d-config.yaml ${K3D_EXTRA_ARGS:-}
}

if k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  log "cluster '$CLUSTER' exists -> starting it (no-op if running)"
  k3d cluster start "$CLUSTER" --wait
else
  log "creating cluster '$CLUSTER' (1 server + 4 agents)"
  # one retry: on slow laptops an agent occasionally misses k3d's readiness
  # timeout; k3d rolls back automatically, so a second attempt is safe.
  create_cluster || { log "create failed, retrying once in 10s"; sleep 10; create_cluster; }
fi

# Kubeconfig for *inside* the docker network: talk to the serverlb by name
# instead of 127.0.0.1:6550 (which only exists on the host).
k3d kubeconfig get "$CLUSTER" \
  | sed -E "s#server: https://[^ ]+#server: https://k3d-${CLUSTER}-serverlb:6443#" > "$KCFG.tmp"
mv "$KCFG.tmp" "$KCFG"
chmod 600 "$KCFG"

log "waiting for 5 Ready nodes"
for _ in $(seq 1 60); do
  n=$(kubectl get nodes --no-headers 2>/dev/null | awk '$2=="Ready"' | wc -l)
  [ "$n" -ge 5 ] && break
  sleep 5
done
kubectl wait --for=condition=Ready nodes --all --timeout=120s

log "applying nodepool labels/taints (troubleshoot/prepare.sh, idempotent)"
sh /work/troubleshoot/prepare.sh

touch "$READY"
log "READY - now run ./scripts/run-all.sh"
exec sleep infinity
