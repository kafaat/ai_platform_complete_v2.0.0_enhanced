FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*
COPY services/auth/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY shared/ /app/shared/
COPY services/auth/main.py /app/main.py
# تفكيك المسارات (#557): main.py يستورد `from router_registry import register_routers`
# الذي يضمّ وحدات routers/. غير منسوخة ⇒ ModuleNotFoundError: 'router_registry' عند
# الإقلاع ⇒ تعطّل auth (unhealthy). نسخها إلزاميّ (نفس درس otp.py أدناه).
COPY services/auth/router_registry.py /app/router_registry.py
COPY services/auth/routers/ /app/routers/
# otp.py وحدة شقيقة نقيّة (مفصولة عن fastapi للاختبار في CI) يستوردها main.py:
# `from otp import …`. كانت غير منسوخة ⇒ ModuleNotFoundError: No module named 'otp'
# عند الإقلاع. نسخها إلزاميّ.
COPY services/auth/otp.py /app/otp.py
# mfa_crypto.py وحدة شقيقة نقيّة (V29.5 — تشفير السرّ/recovery/قفل) يستوردها main.py:
# `import mfa_crypto` (main.py:163). كانت غير منسوخة ⇒ ModuleNotFoundError:
# No module named 'mfa_crypto' عند الإقلاع ⇒ auth unhealthy. نسخها إلزاميّ.
COPY services/auth/mfa_crypto.py /app/mfa_crypto.py
# mfa_runtime.py وحدة شقيقة (P0 auth decomposition — مساعدو MFA DB/تدقيق/anti-replay)
# يستوردها main.py: `from mfa_runtime import …`. غير منسوخة ⇒ ModuleNotFoundError
# عند الإقلاع ⇒ auth unhealthy. نسخها إلزاميّ (نفس درس otp/mfa_crypto).
COPY services/auth/mfa_runtime.py /app/mfa_runtime.py

# Immutable source identity: generated at image build, never overridden at runtime.
ARG SAHOOL_GIT_SHA
ARG SAHOOL_BUILD_ID
ARG SAHOOL_SOURCE_REPOSITORY=
ARG SAHOOL_SOURCE_REF=
# Railway sets RAILWAY_GIT_COMMIT_SHA on GitHub-triggered builds (empty on config-triggered
# ones): a hand-set SAHOOL_GIT_SHA that contradicts it fails the build instead of stamping
# a stale identity (auth-main served a0bba343 while built from cfb47067, 2026-09-20).
# When SAHOOL_GIT_SHA is unset the stamp derives from RAILWAY_GIT_COMMIT_SHA: pinning the variable
# broke every autodeploy after each merge (measured 2026-09-21, deployment 5d9cfdb1).
ARG RAILWAY_GIT_COMMIT_SHA=
# RAILWAY_DEPLOYMENT_ID arrived empty at build time (measured 2026-09-21, fdb7fee6), so an
# unpinned SAHOOL_BUILD_ID falls back to railway-<built commit[:12]>; all-empty still fails.
ARG RAILWAY_DEPLOYMENT_ID=
RUN SAHOOL_GIT_SHA="${SAHOOL_GIT_SHA}" SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID}" SAHOOL_SOURCE_REPOSITORY="${SAHOOL_SOURCE_REPOSITORY}" SAHOOL_SOURCE_REF="${SAHOOL_SOURCE_REF}" RAILWAY_GIT_COMMIT_SHA="${RAILWAY_GIT_COMMIT_SHA}" RAILWAY_DEPLOYMENT_ID="${RAILWAY_DEPLOYMENT_ID}" python - <<'PYID'
import json, os, re
from pathlib import Path
trig = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
sha = os.environ.get("SAHOOL_GIT_SHA") or trig
deployment = os.environ.get("RAILWAY_DEPLOYMENT_ID", "")
build_id = os.environ.get("SAHOOL_BUILD_ID") or (
    f"railway-{deployment}" if deployment else (f"railway-{trig[:12]}" if trig else "")
)
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be 40 lowercase hex characters (set it, or build from a GitHub trigger so RAILWAY_GIT_COMMIT_SHA supplies it)")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", build_id):
    raise SystemExit("SAHOOL_BUILD_ID has invalid format")
if trig and trig != sha:
    raise SystemExit(f"SAHOOL_GIT_SHA {sha} contradicts the commit the platform built {trig} - unset the pinned variable or set it to the built commit")
Path("/app/.sahool-build-metadata.json").write_text(json.dumps({
    "service": 'auth-service',
    "git_sha": sha,
    "build_id": build_id,
    "source_repository": os.environ.get("SAHOOL_SOURCE_REPOSITORY", ""),
    "source_ref": os.environ.get("SAHOOL_SOURCE_REF", ""),
}, sort_keys=True) + "\n", encoding="utf-8")
PYID
RUN chmod 0444 /app/.sahool-build-metadata.json
LABEL org.opencontainers.image.revision="${SAHOOL_GIT_SHA}" \
      org.opencontainers.image.source="${SAHOOL_SOURCE_REPOSITORY}" \
      org.opencontainers.image.ref.name="${SAHOOL_SOURCE_REF}" \
      io.sahool.build-id="${SAHOOL_BUILD_ID}"

RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
