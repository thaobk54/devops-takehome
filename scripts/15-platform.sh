#!/usr/bin/env bash
# Platform hardening needed before the app: HA ingress (2 Traefik replicas + PDB)
# so the reclaim drill measures the app, not a single-replica ingress. Idempotent.
source "$(dirname "$0")/lib.sh"

log "configuring Traefik for HA (HelmChartConfig)"
kubectl apply -f "$REPO_DIR/platform/traefik-ha.yaml"
# k3s' helm-controller re-renders the chart asynchronously: wait until the
# Deployment reflects BOTH settings (replicas + graceful-shutdown flag), then
# wait for that rollout to finish.
traefik_configured() {
  [ "$(kubectl -n kube-system get deploy traefik -o jsonpath='{.spec.replicas}')" = 2 ] &&
    kubectl -n kube-system get deploy traefik -o jsonpath='{.spec.template.spec.containers[0].args}' \
      | grep -q requestAcceptGraceTimeout
}
retry 60 5 traefik_configured || die "traefik HelmChartConfig not applied"
kubectl -n kube-system rollout status deploy/traefik --timeout=180s
r=$(kubectl -n kube-system get deploy traefik -o jsonpath='{.status.readyReplicas}')
kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik -o wide
ok "ingress tier: $r Traefik replicas"
