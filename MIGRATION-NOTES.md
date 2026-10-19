# Part 4: GitLab CI → GitHub Actions migration notes

Legacy: `ci/legacy.gitlab-ci.yml` → New: `.github/workflows/ci.yml` (+ `toolbox.yml`).
I migrated what the pipeline was *meant* to do, not the file itself.

| Legacy practice | Problem | New pipeline |
|---|---|---|
| `AWS_ACCESS_KEY_ID/SECRET` hard-coded in `variables:` | Long-lived credentials in Git, readable by everyone with repo access. Treat them as leaked even if they are "examples". | Removed. The pipeline needs no AWS access at all (GitOps). Where AWS is needed, use **OIDC → IAM role** (`aws-actions/configure-aws-credentials` + `id-token: write`), so there are no static keys anywhere. |
| `sonar_check` with `allow_failure: true` | A quality gate that can never fail is decoration. | `sast` job running **Semgrep** with `--error`: any finding fails the run, and `build` `needs: [test, sast]`. Checked by injecting `subprocess(..., shell=True)` → 3 findings → exit 1. |
| `npm test \|\| echo "tests flaky"` | Failures are swallowed, so tests stop meaning anything. | `pytest` failures fail the job. Flaky tests get fixed or quarantined explicitly, never hidden. |
| Only `$IMAGE:latest` | Not traceable, not reproducible, and rollbacks are guesswork. | Immutable `:<git-sha-12>` tag (plus `latest` as a pointer only). The Helm chart **refuses** `latest`. |
| `docker login -p $PASSWORD` | Password visible in the process list and logs. | `docker/login-action` with the ephemeral `GITHUB_TOKEN` (scoped `packages: write`, valid for one job). |
| `docker:20.10-dind` service | Privileged DinD, slow, no cache. | Buildx with the GitHub Actions cache, multi-arch (amd64 + arm64). |
| `deploy_prod`: `kubectl set image … :latest`, manual, kubeconfig in a CI variable | Imperative drift from Git, cluster-admin credentials stored in CI, no audit trail. | **GitOps:** `gitops-bump` commits the new tag to `charts/quote-api/values.yaml` and ArgoCD syncs. CI has no cluster credentials. Rollback = `git revert`. |
| `only: master` for everything | No feedback on merge requests. | `test` and `sast` (and `build` without push) run on every PR. Push, sign and deploy happen only on `main`. |
| EOL images (`node:16`, `kubectl 1.24`, `sonar-scanner 4.6`) | Unpatched CVEs, unsupported. | Current, pinned versions (Semgrep 1.180.0, Trivy 0.76.0, Python 3.12). |
| *(none)* | No supply-chain checks. | **Trivy** gate on HIGH/CRITICAL (fixable) before push, then **cosign** keyless signing by digest (bonus). |
| *(none)* | Broad default token permissions. | `permissions: contents: read` at the top; each job widens only what it needs. `concurrency` cancels superseded runs. |

The legacy pipeline builds a Node app. This repository's service is Python, so `npm` became `pytest`. The purpose of each stage is the same.

## Migrating the GitLab CI variables and secrets in a real project
1. **Inventory:** export the project/group CI variables (`GET /projects/:id/variables`) and classify each one: *config* (non-secret), *secret*, or *obsolete*.
2. **Eliminate first:** cloud keys become OIDC federation (AWS IAM role trusting `token.actions.githubusercontent.com` with `repo:<org>/<repo>:environment:production`). Registry passwords become `GITHUB_TOKEN`. A kubeconfig is not needed with GitOps.
3. **Then move what's left:** non-secret values go to GitHub **Variables** (`vars.*`), secrets to GitHub **Secrets**. Scope them to **Environments** (`staging`, `production`) with required reviewers and branch rules. Org-level secrets go only to the repos that need them. Load them with `gh secret set --env production < value` from a vault, never by pasting into the UI or committing them.
4. **Rotate** every secret that existed in GitLab when you migrate it. In particular, the keys committed in the legacy file must be revoked, because Git history is forever. Run gitleaks or `trufflehog` over the history.
5. **Run both systems in parallel** for a short period, compare the artifacts, then disable the GitLab pipeline and delete the GitLab variables.

## Repository settings needed (one time)
- Settings → Actions → General → **Workflow permissions: Read and write**, so `gitops-bump` can commit and builds can push to GHCR.
- After the first push: make the `quote-api` and `devops-toolbox` packages **public** (Package settings → Change visibility).
