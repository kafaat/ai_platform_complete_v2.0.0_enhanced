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
RUN SAHOOL_GIT_SHA="${SAHOOL_GIT_SHA}" SAHOOL_BUILD_ID="${SAHOOL_BUILD_ID}" SAHOOL_SOURCE_REPOSITORY="${SAHOOL_SOURCE_REPOSITORY}" SAHOOL_SOURCE_REF="${SAHOOL_SOURCE_REF}" python - <<'PYID'
import json, os, re
from pathlib import Path
sha = os.environ['SAHOOL_GIT_SHA']
build_id = os.environ['SAHOOL_BUILD_ID']
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("SAHOOL_GIT_SHA must be 40 lowercase hex characters")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", build_id):
    raise SystemExit("SAHOOL_BUILD_ID has invalid format")
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
