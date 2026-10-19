#!/usr/bin/env bash
# Shared helpers, sourced by every numbered script.
set -euo pipefail
export KUBECONFIG=${KUBECONFIG:-/root/.kube/config}
REPO_DIR=${REPO_DIR:-/work}
GH_OWNER=${GH_OWNER:-thaobk54}
GH_REPO=${GH_REPO:-devops-takehome}
APP_NS=quote-api
APP_NAME=quote-api
# Ingress entrypoint as seen from inside the docker network (host uses localhost:8080)
INGRESS_URL=${INGRESS_URL:-http://k3d-acme-serverlb:80}

c_info=$'\e[36m'; c_ok=$'\e[32m'; c_err=$'\e[31m'; c_off=$'\e[0m'
log()  { echo "${c_info}==> $*${c_off}"; }
ok()   { echo "${c_ok}OK  $*${c_off}"; }
die()  { echo "${c_err}ERR $*${c_off}" >&2; exit 1; }

# retry <attempts> <sleep> <cmd...>
retry() {
  local n=$1 s=$2; shift 2
  for ((i = 1; i <= n; i++)); do "$@" && return 0; sleep "$s"; done
  return 1
}

require_inside_toolbox() {
  [ -f /.dockerenv ] && command -v k3d >/dev/null || die "run inside the toolbox: docker compose exec toolbox bash $0"
}

# GitOps source. Defaults to this repo on GitHub; override for forks/mirrors.
GIT_REPO_URL=${GIT_REPO_URL:-https://github.com/${GH_OWNER}/${GH_REPO}.git}
GIT_REVISION=${GIT_REVISION:-main}
# ArgoCD Helm chart (OCI on GHCR - no `helm repo add` needed). Pinned.
ARGOCD_CHART=${ARGOCD_CHART:-oci://ghcr.io/argoproj/argo-helm/argo-cd}
ARGOCD_CHART_VERSION=${ARGOCD_CHART_VERSION:-10.10.5}
export GIT_REPO_URL GIT_REVISION
