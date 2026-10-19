# Toolbox image: every CLI the scripts need, pinned, in one container.
# Binaries are copied from their *official* images (multi-stage COPY --from)
# instead of curl|sh downloads: pinned by tag, no checksum juggling, and the
# build needs only registry access.
ARG KUBECTL_VERSION=v1.34.9
ARG HELM_VERSION=3.22.1
ARG TERRAFORM_VERSION=1.16.6
ARG K6_VERSION=1.8.2
ARG K3D_VERSION=5.9.0
ARG DOCKER_VERSION=29.9.1

FROM rancher/kubectl:${KUBECTL_VERSION} AS kubectl
FROM alpine/helm:${HELM_VERSION} AS helm
FROM hashicorp/terraform:${TERRAFORM_VERSION} AS terraform
FROM grafana/k6:${K6_VERSION} AS k6
FROM ghcr.io/k3d-io/k3d:${K3D_VERSION} AS k3d
FROM docker:${DOCKER_VERSION}-cli AS docker

FROM alpine:3.22
LABEL org.opencontainers.image.source="https://github.com/thaobk54/devops-takehome" \
      org.opencontainers.image.description="Toolbox: kubectl, helm, terraform, k6, k3d, docker-cli, python/pytest"
# bash/curl/jq/git for scripts; python3 + pytest + pyyaml for the e2e test suite
# Optional build secret "ca" = support for TLS-intercepting proxies (no-op in CI)
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    apk add --no-cache bash curl jq git ca-certificates python3 py3-pytest py3-yaml gettext coreutils
COPY --from=kubectl   /bin/kubectl                    /usr/local/bin/kubectl
COPY --from=helm      /usr/bin/helm                   /usr/local/bin/helm
COPY --from=terraform /bin/terraform                  /usr/local/bin/terraform
COPY --from=k6        /usr/bin/k6                     /usr/local/bin/k6
COPY --from=k3d       /bin/k3d                        /usr/local/bin/k3d
COPY --from=docker    /usr/local/bin/docker           /usr/local/bin/docker
WORKDIR /work
# Runs as root on purpose: it needs the host Docker socket to create the k3d
# cluster. This is a local dev harness, never deployed - an explicit, reviewed
# exception rather than an accidental default.
USER root
CMD ["sleep", "infinity"]
