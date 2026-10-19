#!/usr/bin/env bash
# Part 2: install ArgoCD, create the Application that syncs charts/quote-api
# from Git, wait until Synced+Healthy, then call the API through the Ingress.
# Idempotent: helm upgrade --install + kubectl apply.
source "$(dirname "$0")/lib.sh"

log "1/4 installing ArgoCD ($ARGOCD_CHART $ARGOCD_CHART_VERSION)"
version_flag=(--version "$ARGOCD_CHART_VERSION")
[[ "$ARGOCD_CHART" == *.tgz ]] && version_flag=()   # local chart archive (offline)
helm upgrade --install argocd "$ARGOCD_CHART" "${version_flag[@]}" \
  --namespace argocd --create-namespace \
  -f "$REPO_DIR/argocd/argocd-values.yaml" --wait --timeout 10m >/dev/null
ok "ArgoCD installed"

log "2/4 applying Application (repo: $GIT_REPO_URL @ $GIT_REVISION)"
envsubst '${GIT_REPO_URL} ${GIT_REVISION}' < "$REPO_DIR/argocd/application.yaml.tpl" | kubectl apply -f -
# ask ArgoCD to refresh now instead of waiting for the next poll
kubectl -n argocd annotate application quote-api argocd.argoproj.io/refresh=normal --overwrite >/dev/null

log "3/4 waiting for Application Synced + Healthy (max 10 min)"
app_state() {
  kubectl -n argocd get application quote-api \
    -o jsonpath='{.status.sync.status}/{.status.health.status}' 2>/dev/null
}
for i in $(seq 1 120); do
  st=$(app_state)
  [ "$st" = "Synced/Healthy" ] && break
  (( i % 6 == 0 )) && echo "   ... $st"
  sleep 5
done
if [ "$(app_state)" != "Synced/Healthy" ]; then
  kubectl -n argocd get application quote-api -o jsonpath='{.status.conditions}{"\n"}{.status.operationState.message}{"\n"}'
  kubectl -n "$APP_NS" get pods -o wide || true
  die "Application not healthy: $(app_state)"
fi
kubectl -n "$APP_NS" rollout status deploy/"$APP_NAME" --timeout=180s
ok "Application Synced/Healthy"
kubectl -n "$APP_NS" get pods -o wide -L app.kubernetes.io/version

log "4/4 calling the API through the Ingress"
retry 30 2 curl -fsS "$INGRESS_URL/api/quote" >/dev/null || die "ingress not answering"
curl -fsS "$INGRESS_URL/api/quote"; echo
ok "from the host:  curl http://localhost:8080/api/quote"
