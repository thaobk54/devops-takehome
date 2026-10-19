#!/usr/bin/env bash
# Part 3: apply the fixed manifests and run the provided verifier.
# Fixes are documented in TROUBLESHOOTING.md (diff: broken-app.yaml vs fixed-app.yaml).
source "$(dirname "$0")/lib.sh"
cd "$REPO_DIR/troubleshoot"

log "applying fixed-app.yaml"
kubectl apply -f fixed-app.yaml
kubectl -n troubleshoot rollout status deploy/web --timeout=120s
kubectl -n troubleshoot rollout status deploy/ai-inference --timeout=120s
# verify.sh reads items[0] of the ai-inference pods: wait until old pods are gone
kubectl -n troubleshoot wait --for=delete pod -l app=ai-inference \
  --field-selector=status.phase!=Running --timeout=60s 2>/dev/null || true

log "running troubleshoot/verify.sh"
out=$(sh ./verify.sh 2>&1) || true
echo "$out"
echo "$out" | tail -1 | grep -qx PASS || die "verify.sh did not PASS"
ok "Part 3 verified: PASS"
