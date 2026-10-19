"""gunicorn settings.

1 worker process: prometheus_client's default registry is per-process, so a
single worker keeps /metrics correct without multiprocess mode. Scaling is done
horizontally by Kubernetes (HPA), not with more workers per pod.
Threads let /healthz and /readyz answer while /api/quote burns CPU, so probes
don't fail under load.
"""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = 1
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 30
graceful_timeout = 20          # < terminationGracePeriodSeconds in the chart
worker_tmp_dir = "/tmp"        # rootfs is read-only in k8s; /tmp is an emptyDir
accesslog = "-"
errorlog = "-"
