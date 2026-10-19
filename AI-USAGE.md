# AI usage disclosure

## How I worked: AI as the implementer, me as the owner and reviewer

I used AI heavily, as the assignment encourages, but in a deliberately constrained way. The AI wrote most of the first drafts of code, manifests and docs. **I defined the method, set the acceptance gates, made the decisions, ran the verification on my own machine, and controlled everything that was published.** Nothing reached the repository without passing gates I defined, and I can walk through and defend every file.

| Responsibility | Owner |
|---|---|
| Working method: small phases, each with its own test cases, which must pass before moving on | **Me** (my first instruction to the AI) |
| Language and readability rules: Python, every part explained | **Me** |
| Scope decisions: which tracks to do (Parts 4 + 5), what to cut (Part 6) and why | **Me**, with the AI's analysis as input |
| First drafts of code, Helm chart, manifests, tests, docs | AI |
| Verification gates: sandbox run → full run on my own machine → green CI, before any push | **Me** (I required local verification *before* pushing) |
| Running the Golden Rule on a clean machine (WSL Ubuntu + Docker) and reading the results | **Me** |
| Approving what gets published: commits via GitHub Desktop, repo settings, package visibility | **Me** |
| Correcting the AI when its output was wrong (see below) | Caught by the gates I set, fixed and re-verified before acceptance |

## Tools
- **Claude (Cowork / Claude Code):** implementation drafts, test authoring, sandbox execution (Docker + k3d), documentation drafts.
- **My own environment:** WSL Ubuntu + Docker 29.9 for the real Golden Rule runs; GitHub Desktop for every commit and push; GitHub Actions for CI.

## Verification I performed myself (not trusting AI-reported results)
- `local-test.sh pre` on my machine before the first push: harness, cluster, Part 3, static and e2e tests → 29/29 passed.
- `local-test.sh full` after CI was green, pulling the **published** images from GHCR and the chart from GitHub, exactly as a reviewer would: all scripts completed, reclaim drill at 100% (50/50 requests), `verify.sh` PASS, Part 5 validated, e2e 24/24.
- Watched every CI run until it was green. When the first run failed, I did not accept "it works in the sandbox": the fix had to pass on the real CI runner first.

## Representative prompts that moved the work forward
1. *"Read the assignment and plan it in small phases; each phase must have its own test cases. Code in Python with explanations. Setup and verification must run in a sandbox or directly on my machine."* This set the rule that nothing counts as done without a passing test. It produced `PLAN.md` and the test layers (`app/tests`, `tests/image`, `tests/static`, `tests/e2e`).
2. *"Placement: prefer spot, at least one replica must stay on on-demand, and the spread must stay soft enough that rescheduling works when a node is drained. Explain why a hard constraint would break the drill."* I asked for the reasoning, not just YAML, so I could judge the trade-off myself. It led to a hard *capacity* spread plus a soft *hostname* spread, proven by `25-reclaim-drill.sh`.
3. *"Save code to my repo only after it has been tested and the local run succeeds, before pushing to the remote."* This made my machine, not the AI's sandbox, the source of truth for "works". It is how the Windows/Git Bash path bug and the non-root CI bug were caught before submission.

## Where the AI was wrong or suboptimal (and how it was caught)
Each of these was caught by a verification gate, not by trusting the AI's own claim that it was done. Each fix was re-verified before I accepted it.

- **Bootstrap reported READY after a failed cluster create.** The first `bootstrap/entrypoint.sh` used `if ! bootstrap; then …`. Bash disables `set -e` inside a function used as an `if` condition, so a failed `k3d cluster create` carried on and still wrote the ready marker: a false green. Caught when a test run showed `ERROR: need at least 4 worker nodes` followed by `READY`. Fix: `set -E` plus an `ERR` trap that writes a `failed` marker, which `10-wait-cluster.sh` checks.
- **The reclaim drill was flaky (96%, 2 failed requests on the second run).** The AI's first answer, 2 Traefik replicas, was necessary but not sufficient. The failures lined up with a Traefik pod being evicted: Traefik stops accepting on SIGTERM while kube-proxy still routes to it. Fix: `requestAcceptGraceTimeout=5s`, plus making `15-platform.sh` wait until that flag actually reaches the Deployment. Accepted only after three consecutive 100% drills and a full re-run.
- **The first CI run was red.** A Terraform test the AI wrote cached providers under `/root/.cache`. That works in a root sandbox but fails on GitHub's non-root runner. Caught by the "green CI before submission" gate. Fix: cache under `$HOME`, re-tested as a non-root user, then CI green.
- **Golden Rule broken on Windows Git Bash.** `docker compose exec … /work/scripts/run-all.sh` gets its path rewritten to `C:/Program Files/Git/work/...`. Caught while preparing the on-my-machine run. Fix: `MSYS_NO_PATHCONV=1` in `run-all.sh`.
- **Image size (206 MB on `python:3.12-slim`)**, pip left in the venv. Caught by the size test in `tests/image`. Alpine plus removing pip brought it to about 94 MB.
- **Ineffective SAST suppression.** The suggested `# nosemgrep` comment isn't honoured in Dockerfiles. Rather than disabling the rule globally, which would also blind it for the app's Dockerfile, the root-by-design toolbox is excluded explicitly in `.semgrepignore`, with the reason written down.
- **Tests that were wrong rather than the system.** (a) An HTTP test that never read its responses. (b) NetworkPolicy tests racing kube-router on freshly started pods; now they retry like the provided smoke Job, and a retry can't turn a real *deny* into an *allow*. (c) A post-drill placement assertion stricter than the soft-spread design. A test is code too, and it gets the same scrutiny.

## What I take away
AI made me faster at producing drafts. It did not make the drafts correct. Correctness came from the gates: tests per phase, a real machine, green CI. Three of the issues above (the false READY, the 96% drill, the non-root CI failure) would have shipped if I had accepted the AI's "done". I own this submission, including the parts the AI drafted, and I'm happy to walk through any of it live.
