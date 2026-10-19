#!/usr/bin/env bash
# Part 5: validate the IaC without any cloud account (scripts/50-validate-tf.sh).
#  5b Cloudflare Terraform: fmt -check, init -backend=false, validate
#  5a Karpenter: install the REAL Karpenter CRDs (schemas only, no controller)
#     into the local cluster and server-side dry-run our manifests against
#     them - catches wrong API versions / field names / enum values, which a
#     plain YAML lint cannot.
source "$(dirname "$0")/lib.sh"

KARPENTER_VERSION=${KARPENTER_VERSION:-v1.15.0}
TF_DIR="$REPO_DIR/iac/cloudflare"
K_DIR="$REPO_DIR/iac/karpenter"
# keep provider downloads out of the bind-mounted repo
export TF_DATA_DIR=/root/.cache/tf-data/cloudflare
export TF_PLUGIN_CACHE_DIR=/root/.cache/tf-plugins
mkdir -p "$TF_PLUGIN_CACHE_DIR"

log "5b terraform fmt -check"
terraform -chdir="$TF_DIR" fmt -check -diff -recursive || die "terraform fmt: run 'terraform fmt -recursive iac/cloudflare'"
log "5b terraform init -backend=false"
terraform -chdir="$TF_DIR" init -backend=false -input=false -no-color >/dev/null
log "5b terraform validate"
terraform -chdir="$TF_DIR" validate -no-color
ok "Cloudflare Terraform valid"

log "5a installing Karpenter $KARPENTER_VERSION CRDs (schemas only)"
crd_url() {   # official GitHub raw, jsDelivr mirror as fallback
  for base in "https://raw.githubusercontent.com/aws/karpenter-provider-aws/$KARPENTER_VERSION" \
              "https://cdn.jsdelivr.net/gh/aws/karpenter-provider-aws@$KARPENTER_VERSION"; do
    curl -fsSL "$base/pkg/apis/crds/$1" && return 0
  done
  return 1
}
for crd in karpenter.sh_nodepools.yaml karpenter.k8s.aws_ec2nodeclasses.yaml; do
  crd_url "$crd" | kubectl apply --server-side --force-conflicts -f - >/dev/null || die "could not install CRD $crd"
done
kubectl wait --for=condition=Established crd/nodepools.karpenter.sh crd/ec2nodeclasses.karpenter.k8s.aws --timeout=60s >/dev/null

log "5a server-side dry-run of the GPU NodePools / EC2NodeClass"
kubectl apply --dry-run=server -f "$K_DIR/ec2nodeclass-gpu.yaml" -f "$K_DIR/nodepool-gpu.yaml"
ok "Karpenter manifests valid against the $KARPENTER_VERSION CRDs"

log "policy tests (tests/static/test_karpenter.py, test_terraform.py)"
cd "$REPO_DIR" && python3 -m pytest -q -p no:cacheprovider tests/static/test_karpenter.py tests/static/test_terraform.py
ok "Part 5 validated"
