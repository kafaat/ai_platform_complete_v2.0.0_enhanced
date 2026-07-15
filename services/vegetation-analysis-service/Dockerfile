# SAHOOL v9 — vegetation-analysis-service Dockerfile (build context = project root)
FROM python:3.11-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY services/vegetation-analysis-service/requirements.txt /tmp/requirements.txt
# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
# FIXED: shared/ copy works because context is project root
COPY shared/ /app/shared/
COPY services/vegetation-analysis-service/main.py /app/main.py
# تفكيك المسارات: main.py يستورد router_registry الذي يضمّ routers/. غير منسوخة ⇒
# ModuleNotFoundError: 'router_registry' عند الإقلاع ⇒ تعطّل الخدمة. نسخها إلزاميّ.
COPY services/vegetation-analysis-service/router_registry.py /app/router_registry.py
COPY services/vegetation-analysis-service/routers/ /app/routers/
# vegetation_runtime.py وحدة شقيقة (P1 decomposition) يستوردها main.py:
# `from vegetation_runtime import …` (main.py:70). غير منسوخة ⇒ ModuleNotFoundError
# عند الإقلاع ⇒ تعطّل الخدمة. نسخها إلزاميّ (نفس درس router_registry).
COPY services/vegetation-analysis-service/vegetation_runtime.py /app/vegetation_runtime.py
COPY services/vegetation-analysis-service/vegetation_contracts.py /app/vegetation_contracts.py
COPY services/vegetation-analysis-service/indicator_registry.py /app/indicator_registry.py
COPY services/vegetation-analysis-service/baseline_engine.py /app/baseline_engine.py
COPY services/vegetation-analysis-service/anomaly_engine.py /app/anomaly_engine.py
COPY services/vegetation-analysis-service/anomaly_store.py /app/anomaly_store.py
COPY services/vegetation-analysis-service/anomaly_store_pg.py /app/anomaly_store_pg.py
COPY services/vegetation-analysis-service/anomaly_requests.py /app/anomaly_requests.py
COPY services/vegetation-analysis-service/anomaly_runtime.py /app/anomaly_runtime.py
COPY services/vegetation-analysis-service/ground_verification_bridge.py /app/ground_verification_bridge.py
COPY services/vegetation-analysis-service/diagnosis_engine.py /app/diagnosis_engine.py
COPY services/vegetation-analysis-service/decision_bridge.py /app/decision_bridge.py
COPY services/vegetation-analysis-service/post_execution_bridge.py /app/post_execution_bridge.py
# indicator_registry.py يقرأ ملفّ القدرات المُولَّد عند الاستيراد
# (Path(__file__).with_name("indicator_capabilities.generated.json")). غير منسوخ ⇒
# FileNotFoundError عند الإقلاع ⇒ تعطّل الخدمة. نسخه إلزاميّ.
COPY services/vegetation-analysis-service/indicator_capabilities.generated.json /app/indicator_capabilities.generated.json
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
HEALTHCHECK --interval=20s --timeout=5s CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
