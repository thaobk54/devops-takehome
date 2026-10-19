# ---- Stage 1: build dependencies into an isolated virtualenv ----------------
FROM python:3.12-alpine AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
# Optional build secret "ca": lets the image build behind a TLS-intercepting
# corporate proxy without baking the CA into any layer (absent in CI = no-op).
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install -r requirements.txt && \
    pip uninstall -y pip   # the runtime never installs anything

# ---- Stage 2: minimal runtime (alpine: all deps are pure Python, ~60 MB) -----
FROM python:3.12-alpine AS runtime
ARG APP_VERSION=dev
LABEL org.opencontainers.image.source="https://github.com/thaobk54/devops-takehome" \
      org.opencontainers.image.description="quote-api for the DevOps take-home"
# Fixed numeric UID/GID so k8s `runAsNonRoot` can verify it without /etc/passwd lookups
RUN addgroup -S -g 10001 app && \
    adduser -S -D -H -u 10001 -G app -s /sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=10001:10001 main.py gunicorn.conf.py ./
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    PORT=8000
USER 10001:10001
EXPOSE 8000
# Container-level healthcheck for plain `docker run`; k8s uses its own probes.
HEALTHCHECK --interval=10s --timeout=2s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
