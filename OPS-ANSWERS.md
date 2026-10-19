# Part 7 — Ops answers

## 1. EKS 1.33 → 1.35, zero downtime

The control plane moves **one minor at a time**, so this is two passes (1.33→1.34→1.35). Each pass goes in this order:

1. **Pre-flight.** Read EKS Upgrade Insights and the release notes. Scan for removed APIs (`pluto`/`kubent`). Confirm CNI, ingress, operators and charts support the target. Rehearse on staging.
2. **Control plane.** `aws eks update-cluster-version`. Managed and in place; the API stays available.
3. **Add-ons** for the new minor: **vpc-cni** first, then **kube-proxy** (never newer than the control plane), **CoreDNS** (≥2 replicas plus a PDB), **EBS/EFS CSI**. Use managed add-ons with `--resolve-conflicts PRESERVE`.
4. **Workers.** Bump the AMI (AL2023/Bottlerocket). Karpenter drift replaces nodes under its disruption budgets; managed node groups do surge updates. PDBs, ≥2 replicas, topology spread and `preStop` keep services up during drains. Kubelet may lag the API by up to 3 minors, so nodes never block the next control-plane pass.

**Top risks:**

1. **Removed/changed APIs** break workloads. Mitigation: scan, test on staging, pin charts.
2. **Drains stall or cause outages.** Causes: `maxUnavailable: 0` PDBs, single replicas, `do-not-disrupt`. Mitigation: audit beforehand, roll one AZ/pool at a time.
3. **Add-on/OS incompatibility.** Examples: an old vpc-cni, newer kubelets refusing cgroup v1. Mitigation: follow the add-on order above, AL2023/Bottlerocket only. Control-plane upgrades can't be rolled back, so the staging rehearsal and backups (Velero, GitOps) are the real safety net.

## 2. Spot reclaims paging at 3 AM

A reclaim is a *planned* capacity loss. It shouldn't page; user-visible symptoms should.

- **Handle reclaims explicitly.** Karpenter (or NTH) consumes the EC2 interruption warning via EventBridge/SQS, then cordons and drains the node and counts `karpenter_interruption_received_messages_total`. The node leaves before kubelet ever goes "unreachable".
- **Scope node alerts.** Join `KubeNodeUnreachable` with `kube_node_labels`: it **pages** for `capacity-type=on-demand`. For spot nodes it opens a **ticket** only if the node is still unreachable after 15 min with **no** interruption event and no deletion timestamp. That last case is a real failure, so it is still caught.
- **Alertmanager inhibition and grouping.** An interruption or termination event inhibits node alerts for that node. Group by nodepool/AZ, so one event means one notification.
- **Page on symptoms and capacity.** SLO burn rate (errors, p99), pods `Pending` >10 min, Deployment below desired replicas or PDB minimum for 10 min, >30% of a nodepool lost in 15 min (mass reclaim / AZ event). Node failures that matter surface here even on spot.
- **Review.** Demote any alert that pages without requiring action.

## 3. Cloudflare in front, mobile LCP 5 s

1. **Field data first.** Use CrUX/PSI to confirm slow real-user mobile LCP, and identify the LCP element (HTML wait vs hero image).
2. **Headers.** `curl -sI -A '<mobile UA>' https://site/`, repeated:
   - `cf-cache-status`: `DYNAMIC` means not eligible; Cloudflare doesn't cache HTML by default, so it needs a Cache Rule "Eligible for cache". `BYPASS` means a rule or cookie skips the cache. `MISS` every time means a fragmented cache key or TTL 0.
   - Also check `age` (should grow), origin `cache-control` (`private`/`no-store`/`max-age=0`), `set-cookie` on HTML, and `vary: User-Agent` (cache split per device).
3. **Rules.** Check Cache Rules vs legacy Page Rules (later Cache Rules override earlier ones), whether the expressions really match host and path, and cache-key settings (`utm_*`/`fbclid` query strings, cookies, device type).
4. **Origin.** Compare TTFB direct to origin (`curl --resolve site:443:<origin-ip> -w '%{time_starttransfer}'`) with TTFB via Cloudflare. If a HIT is fast but a MISS takes 3 s, fix both: the origin (SSR/app cache) and the hit ratio (edge TTL, `stale-while-revalidate`, Tiered Cache).
5. **Verify.** Check the HIT ratio, then multi-region TTFB, then LCP. If HTML hits the cache and LCP is still slow, the culprit is the asset: hero image size/format, render-blocking CSS/JS, missing `preload`/`fetchpriority`.

## 4. Application secrets on EKS

| | **External Secrets Operator + AWS Secrets Manager** | **Sealed Secrets / SOPS in Git** |
|---|---|---|
| Source of truth | One store for every cluster | Encrypted files per repo/cluster |
| Rotation | Native in AWS; ESO re-syncs | Re-encrypt, commit, redeploy |
| Access & audit | IAM via Pod Identity/IRSA per namespace; CloudTrail on every read | Whoever holds the key; Git history |
| Multi-cluster | Same secret consumed by N clusters | Re-seal per cluster or manage KMS keys |

**Pick ESO + Secrets Manager.** With several production clusters, a startup needs one place to create, rotate and audit secrets. ESO keeps GitOps intact: the `ExternalSecret` lives in Git, the value never does. Each cluster's ESO gets least-privilege IAM, for example a `/prod/<app>/*` path only. Add EKS envelope encryption with a customer-managed KMS key, tight `get secrets` RBAC, and file mounts instead of environment variables. SOPS remains handy for ESO's own bootstrap credentials.
