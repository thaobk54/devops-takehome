#!/usr/bin/env bash
# Wait until the compose bootstrap finished (cluster up + nodepools labeled).
source "$(dirname "$0")/lib.sh"

log "waiting for bootstrap (docker compose logs -f toolbox shows progress)"
for _ in $(seq 1 120); do
  [ -f /root/.kube/ready ] && break
  [ -f /root/.kube/failed ] && die "bootstrap FAILED - check: docker compose logs toolbox"
  sleep 5
done
[ -f /root/.kube/ready ] || die "bootstrap did not finish in 10 min - check: docker compose logs toolbox"

kubectl get nodes -L acme.io/capacity -L acme.io/node-type
spot=$(kubectl get nodes -l acme.io/capacity=spot --no-headers | wc -l)
od=$(kubectl get nodes -l acme.io/capacity=on-demand --no-headers | wc -l)
gpu=$(kubectl get nodes -l acme.io/node-type=gpu --no-headers | wc -l)
[ "$spot" -ge 2 ] && [ "$od" -ge 1 ] && [ "$gpu" -ge 1 ] || die "nodepool labels missing (spot=$spot od=$od gpu=$gpu)"

log "waiting for core add-ons (coredns, traefik, metrics-server)"
kubectl -n kube-system rollout status deploy/coredns --timeout=180s
retry 60 5 kubectl -n kube-system get deploy/traefik >/dev/null 2>&1 || die "traefik not installed"
kubectl -n kube-system rollout status deploy/traefik --timeout=180s
kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
ok "cluster ready: spot=$spot on-demand=$od gpu=$gpu"
