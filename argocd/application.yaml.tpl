# Rendered by scripts/20-deploy.sh (envsubst) - the only manual object we create.
# Everything for the app itself comes from the Helm chart in Git.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: quote-api
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io/background   # deleting the App deletes its resources
spec:
  project: default
  source:
    repoURL: ${GIT_REPO_URL}
    targetRevision: ${GIT_REVISION}
    path: charts/quote-api
    helm:
      releaseName: quote-api
  destination:
    server: https://kubernetes.default.svc
    namespace: quote-api
  syncPolicy:
    automated:
      prune: true
      selfHeal: true      # manual kubectl edits are reverted -> Git stays the source of truth
    syncOptions:
      - CreateNamespace=true
    retry:
      limit: 5
      backoff: {duration: 10s, factor: 2, maxDuration: 3m}
