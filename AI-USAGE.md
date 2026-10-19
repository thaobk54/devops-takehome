# AI usage disclosure

> DRAFT — written while the work was done. The owner reviews and completes it before submitting.

## Tools
- **Claude (Cowork / Claude Code):** planning, scaffolding code and manifests, writing tests, running them in a sandbox (Docker + k3d), and drafting the docs.
- Every artifact was run, not just read: unit tests, image tests, `helm lint` plus policy tests, a server-side dry-run, a real k3d cluster with ArgoCD, the reclaim drill, `verify.sh`, Semgrep and Trivy, and actionlint.

## Representative prompts that moved the work forward
1. *"Read the assignment and plan it in small phases; each phase must have its own test cases that pass before moving on."* This produced `PLAN.md` and the test-first structure (`app/tests`, `tests/image`, `tests/static`, `tests/e2e`).
2. *"Placement: prefer spot, at least one replica must stay on on-demand, and the spread must stay soft enough that rescheduling works when a node is drained. Explain why a hard constraint would break the drill."* This led to the hard *capacity* spread combined with a soft *hostname* spread, verified by `25-reclaim-drill.sh`.
3. *"Before writing fixed-app.yaml, reproduce each Part 3 failure live and record the exact symptom and command."* This is why `TROUBLESHOOTING.md` contains real event messages instead of guesses.

## Where the AI was wrong or suboptimal (and how it was caught)
- **Bootstrap reported READY after a failed cluster create.** The first `bootstrap/entrypoint.sh` called `if ! bootstrap; then …`. Bash disables `set -e` inside a function used as an `if` condition, so a failed `k3d cluster create` continued, `prepare.sh` failed, and the script *still* wrote the ready marker. I caught it when a sandbox run printed `ERROR: need at least 4 worker nodes` followed by `READY`. Fix: `set -E` plus an `ERR` trap that writes a `failed` marker, which `10-wait-cluster.sh` now checks.
- **The HA ingress was missing from the first design.** The drill would have measured a *Traefik* outage whenever the single k3s Traefik replica sat on the drained spot node. I spotted this while reviewing what the drill actually measures. Fix: `15-platform.sh` runs Traefik with 2 replicas and a PDB.
- **The drill was flaky on the second run (96%, two failed connections).** The AI's first HA fix (2 Traefik replicas) was necessary but not enough. The failures lined up exactly with a Traefik pod being evicted, because Traefik stops accepting connections immediately on SIGTERM while kube-proxy still routes to it. Fix: `requestAcceptGraceTimeout=5s`, and `15-platform.sh` now waits until that flag actually reaches the Deployment. Three drills in a row, then a full re-run: 100%.
- **The image size test failed** (206 MB on `python:3.12-slim`). The AI's first Dockerfile kept pip in the venv. Switching to Alpine and uninstalling pip from the venv brought it to about 94 MB, verified by `tests/image`.
- **The suggested Semgrep suppression didn't work.** A `# nosemgrep` comment above a Dockerfile instruction is not honoured; the finding stayed. Instead of disabling the rule globally, which would also stop it checking the app Dockerfile, the root-by-design toolbox is excluded explicitly in `.semgrepignore` with the reason.
- **Two tests were wrong rather than the system.** (a) An HTTP test fired requests without reading the responses and timed out. (b) The NetworkPolicy tests failed only on a freshly started pod because kube-router programs pod IPs a moment after start. The provided smoke Job retries for the same reason, so the tests now retry too. A retry cannot turn a real *deny* into an *allow*, so this does not weaken the check. (c) A placement assertion of "3 pods on 3 nodes" was too strict after a drill. The spread is soft by design, so it became "never all on one node".
