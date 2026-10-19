#!/usr/bin/env bash
# Part 2: spot reclaim drill.
#  1. pick a spot node that runs quote-api pods
#  2. start a curl loop against the Ingress (background, 5 req/s)
#  3. drain the node (respects the PDB, like a spot interruption handler would)
#  4. show pods rescheduling, check availability + placement afterwards
#  5. uncordon (always - via trap, even on failure / Ctrl-C)
# Pass/fail: >= MIN_SUCCESS_PCT of requests answered 200 during the drill.
source "$(dirname "$0")/lib.sh"

MIN_SUCCESS_PCT=${MIN_SUCCESS_PCT:-99}
SEL="app.kubernetes.io/name=$APP_NAME"
RESULTS=$(mktemp)
LOOP_PID=""
NODE=""

cleanup() {
  [ -n "$LOOP_PID" ] && kill "$LOOP_PID" 2>/dev/null || true
  if [ -n "$NODE" ]; then
    log "uncordon $NODE"
    kubectl uncordon "$NODE" >/dev/null || true
  fi
}
trap cleanup EXIT

pods_wide() {
  kubectl -n "$APP_NS" get pods -l "$SEL" \
    -o custom-columns='POD:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeName' --no-headers \
    | while read -r pod st node; do
        cap=$(kubectl get node "$node" -o jsonpath='{.metadata.labels.acme\.io/capacity}' 2>/dev/null)
        printf '  %-32s %-9s %-20s %s\n' "$pod" "$st" "$node" "${cap:-?}"
      done
}

log "placement BEFORE the drill"
kubectl -n "$APP_NS" rollout status deploy/"$APP_NAME" --timeout=120s >/dev/null
pods_wide

# 1. victim = a spot node currently hosting at least one replica
for n in $(kubectl get nodes -l acme.io/capacity=spot -o name | sed 's#node/##'); do
  if kubectl -n "$APP_NS" get pods -l "$SEL" --field-selector spec.nodeName="$n" --no-headers 2>/dev/null | grep -q .; then
    NODE=$n; break
  fi
done
[ -n "$NODE" ] || die "no spot node runs a quote-api replica - nothing to drill"
log "simulated spot reclaim on: $NODE"

# 2. traffic generator: one line per request "<http_code>"
(
  while true; do
    curl -s -o /dev/null -w '%{http_code}\n' --max-time 2 "$INGRESS_URL/api/quote" >>"$RESULTS" || echo 000 >>"$RESULTS"
    sleep 0.2
  done
) &
LOOP_PID=$!
sleep 3

# 3. drain (evictions honour the PodDisruptionBudget)
log "draining $NODE"
kubectl drain "$NODE" --ignore-daemonsets --delete-emptydir-data --timeout=180s

# 4. rescheduling + recovery
log "waiting for the Deployment to be fully available again"
kubectl -n "$APP_NS" rollout status deploy/"$APP_NAME" --timeout=180s
for _ in $(seq 1 30); do
  ready=$(kubectl -n "$APP_NS" get deploy "$APP_NAME" -o jsonpath='{.status.readyReplicas}')
  want=$(kubectl -n "$APP_NS" get deploy "$APP_NAME" -o jsonpath='{.spec.replicas}')
  [ "${ready:-0}" -ge "${want:-3}" ] && break
  sleep 2
done
sleep 5                                    # keep measuring a bit after recovery
kill "$LOOP_PID" 2>/dev/null || true; LOOP_PID=""

log "placement AFTER the drill (node $NODE cordoned)"
pods_wide
log "recent scheduling events"
kubectl -n "$APP_NS" get events --sort-by=.lastTimestamp \
  --field-selector involvedObject.kind=Pod 2>/dev/null | grep -E 'Scheduled|Killing|Started' | tail -8 || true

# 5. verdict
total=$(wc -l <"$RESULTS")
okc=$(grep -c '^200$' "$RESULTS" || true)
pct=$(( total > 0 ? okc * 100 / total : 0 ))
echo
echo "requests during drill: $total   200 OK: $okc   success: ${pct}%"
echo "non-200 codes: $(grep -v '^200$' "$RESULTS" | sort | uniq -c | tr '\n' ' ')"

on_node=$(kubectl -n "$APP_NS" get pods -l "$SEL" --field-selector spec.nodeName="$NODE" --no-headers 2>/dev/null | grep -c Running || true)
od=0
for n in $(kubectl -n "$APP_NS" get pods -l "$SEL" --field-selector=status.phase=Running -o jsonpath='{.items[*].spec.nodeName}'); do
  [ "$(kubectl get node "$n" -o jsonpath='{.metadata.labels.acme\.io/capacity}')" = on-demand ] && od=$((od + 1))
done
rm -f "$RESULTS"

[ "$on_node" -eq 0 ] || die "$on_node replica(s) still on drained node $NODE"
[ "$od" -ge 1 ]      || die "no replica on the on-demand node after the drill"
[ "$pct" -ge "$MIN_SUCCESS_PCT" ] || die "availability ${pct}% < ${MIN_SUCCESS_PCT}%"
ok "service survived the reclaim: ${pct}% success, >=1 replica on on-demand ($od)"
