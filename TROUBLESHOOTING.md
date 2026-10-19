# Part 3 — Troubleshooting write-up

`troubleshoot/broken-app.yaml` → `troubleshoot/fixed-app.yaml` (every change is tagged `FIX #n` in the file).
Run with `scripts/30-troubleshoot.sh`; it ends with `verify.sh` printing **PASS**.
Rules respected: `default-deny` is unchanged, and no node label or taint was touched.

The issues stack on top of each other: fixing one shows the next. I fixed them one at a time, in the order they appeared,
with live `kubectl patch` commands, re-checked each time, and only then wrote the final manifest.
The commands below are the ones I actually ran (`-n troubleshoot` is omitted to keep them short).

Start with a quick look at everything:

```bash
kubectl apply -f troubleshoot/broken-app.yaml
kubectl get all,netpol -n troubleshoot -o wide
#  web-…           0/1  Pending          ai-inference-…  0/1  Pending
#  service/web-svc …  SELECTOR app=webapp          <- already suspicious
```

---

### 1. `web` stuck in Pending: requests 16Gi of memory
- **Symptom:** both `web` pods `Pending`.
- **Diagnosis:**
  ```bash
  kubectl describe pod -l app=web | grep -A3 Events
  # FailedScheduling: 0/5 nodes are available: 1 node(s) had untolerated taint(s), 4 Insufficient memory.
  kubectl describe nodes | grep -A6 "Allocatable" | grep memory     # each node has only a few GiB
  ```
- **Root cause:** `requests.memory: 16Gi` is bigger than any node's allocatable memory, so the scheduler can't place it anywhere.
  The "1 untolerated taint" part is the GPU node, which is expected here.
- **Fix:** right-size it for a static nginx: requests `50m / 32Mi`, limits `200m / 128Mi`.

### 2. `web` stuck in ContainerCreating: ConfigMap name typo
- **Symptom:** after fix 1, the pod is scheduled but stays in `ContainerCreating`.
- **Diagnosis:**
  ```bash
  kubectl get events --sort-by=.lastTimestamp | grep FailedMount
  # MountVolume.SetUp failed for volume "html" : configmap "web-conf" not found
  kubectl get configmap          # -> web-config
  ```
- **Root cause:** the volume points to `web-conf`, but the ConfigMap is called `web-config`.
- **Fix:** `configMap.name: web-config`.

### 3. `ErrImagePull` / `ImagePullBackOff`: the image tag doesn't exist
- **Symptom:** `ImagePullBackOff`.
- **Diagnosis:**
  ```bash
  kubectl describe pod -l app=web | grep -E "Failed|pull"
  # Failed to pull image "nginx:1.25.99": ... not found
  curl -s -o /dev/null -w '%{http_code}' https://hub.docker.com/v2/repositories/library/nginx/tags/1.25.99   # 404
  curl -s -o /dev/null -w '%{http_code}' https://hub.docker.com/v2/repositories/library/nginx/tags/1.25.5    # 200
  ```
- **Root cause:** nginx `1.25.99` was never released.
- **Fix:** pin a real patch release, `nginx:1.25.5`. I kept the 1.25 line so the behaviour matches what was intended.

### 4. CrashLoop / never Ready: probes hit the wrong port
- **Symptom:** the container runs but restarts every ~15 s and never becomes Ready.
- **Diagnosis:**
  ```bash
  kubectl get events --sort-by=.lastTimestamp | grep -E "Unhealthy|Killing"
  # Liveness probe failed: Get "http://10.42.3.15:8080/": connect: connection refused
  # Container nginx failed liveness probe, will be restarted
  kubectl exec deploy/web -- sh -c 'curl -s localhost:80 | head -1; curl -s localhost:8080 || echo refused'
  # <html><body><h1>TROUBLESHOOT-OK</h1>...   /   refused
  ```
- **Root cause:** stock nginx listens on **80**, but both probes target **8080**. A failing liveness probe gets the container killed over and over.
- **Fix:** set the liveness and readiness probe port to `80`.
- *Side note:* under `default-deny`, kubelet probes still reach the pod. On k3s the kube-router policy controller allows traffic that originates on the node, and the events above show probes connecting (and being refused on the wrong port). So no extra NetworkPolicy is needed for probes.

### 5. Service has no endpoints: selector mismatch
- **Symptom:** pods are `1/1 Ready`, but `verify.sh` step 6 says *no endpoints*.
- **Diagnosis:**
  ```bash
  kubectl get endpointslices -l kubernetes.io/service-name=web-svc     # ENDPOINTS <none>
  kubectl get svc web-svc -o jsonpath='{.spec.selector}'              # {"app":"webapp"}
  kubectl get pods --show-labels -l app=web                           # app=web
  ```
- **Root cause:** the Service selects `app=webapp`, but the pods are labelled `app=web`.
- **Fix:** `selector: {app: web}`.

### 6. Endpoints exist but connections are refused: wrong targetPort
- **Symptom:** after fix 5 the EndpointSlice lists the pod IPs, but on port **8080**.
- **Diagnosis:**
  ```bash
  kubectl get endpointslices -l kubernetes.io/service-name=web-svc    # PORTS 8080
  kubectl get svc web-svc -o jsonpath='{.spec.ports}'                 # targetPort 8080
  ```
- **Root cause:** `targetPort: 8080`, but the container listens on 80 (same mistake as #4).
- **Fix:** `targetPort: 80`.

### 7. `ai-inference` Pending: wrong label key, missing toleration
- **Symptom:** `Pending`.
- **Diagnosis:**
  ```bash
  kubectl describe pod -l app=ai-inference | grep -A3 Events
  # 0/5 nodes are available: 1 node(s) had untolerated taint(s), 4 node(s) didn't match Pod's node affinity/selector
  kubectl get nodes -L acme.io/node-type,node-type
  kubectl get node <gpu-node> -o jsonpath='{.spec.taints}'
  # [{"effect":"NoSchedule","key":"nvidia.com/gpu","value":"true"}]
  ```
- **Root cause:** there are two separate problems.
  (a) `nodeSelector: node-type: gpu` uses a key that doesn't exist. `prepare.sh` sets `acme.io/node-type=gpu`.
  (b) Even with the right selector, the GPU node's `nvidia.com/gpu=true:NoSchedule` taint rejects pods that don't tolerate it.
  A selector says "I want that node"; a toleration says "I accept its taint". GPU workloads need both.
- **Fix:** `nodeSelector: {acme.io/node-type: gpu}` plus a toleration for `nvidia.com/gpu=true:NoSchedule`. The node itself is untouched.

### 8. Smoke test times out: default-deny blocks DNS and HTTP
- **Symptom:** `verify.sh` step 7, *smoke test failed*, even though everything above is healthy.
- **Diagnosis:**
  ```bash
  kubectl get netpol                       # only default-deny: podSelector {} , Ingress+Egress
  kubectl run probe --rm -i --restart=Never --image=curlimages/curl:8.7.1 --labels=app=debug -- \
    curl -sS -m5 http://web-svc.troubleshoot.svc.cluster.local
  # curl: (7) Failed to connect ... Couldn't connect to server      (blocked)
  ```
  To prove the DNS rule is needed, I temporarily removed only the DNS egress rule:
  ```bash
  # nslookup: write to '10.43.0.10': Connection refused
  # curl: (28) Resolving timed out after 4000 milliseconds
  ```
- **Root cause:** `default-deny` selects every pod for both Ingress and Egress. The smoke Job (`app=smoke-client`) can't resolve DNS
  (egress to CoreDNS on port 53) and can't open TCP 80 to the web pods. The web pods also refuse all ingress.
- **Fix:** two least-privilege policies. `default-deny` is not edited.
  - `smoke-client-egress`: pods labelled `app=smoke-client` may send traffic only to kube-dns in kube-system (UDP/TCP 53) and to `app=web` on TCP 80.
  - `web-allow-from-smoke-client`: pods labelled `app=web` accept traffic only from `app=smoke-client` on TCP 80.
- **Least-privilege proof** (automated in `tests/e2e/test_30_troubleshoot.py`):
  a pod with any other label **cannot** reach web, and the smoke client **cannot** reach the Kubernetes API or anything else.

---

### Notes on the handoff itself
- With kube-router, a new pod's IP is added to the policy ipsets a moment **after** the pod starts. A client that connects immediately can get a
  spurious "connection refused" for a second or so. The provided smoke Job already retries (`--retry-connrefused`), and my tests do the same.
  It's worth knowing before you suspect your own policies.
- `verify.sh` reads `items[0]` of the `ai-inference` pods. If an old Pending pod is still terminating, it can check the wrong pod.
  `30-troubleshoot.sh` waits for the rollout and for leftover pods to go away before running it.
- `prepare.sh` labels nodes by **sort order** of the worker names (agent-0/1 = spot, agent-2 = on-demand, agent-3 = gpu) and leaves the k3d
  **server** node schedulable and unlabelled. That's harmless here, but it's why the Part 2 chart uses a *required* affinity on
  `acme.io/capacity In (spot, on-demand)`, so app pods can never land on the server or GPU node.
