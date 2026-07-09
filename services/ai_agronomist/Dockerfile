FROM python:3.12-slim-bookworm
WORKDIR /app
COPY services/ai_agronomist/requirements.txt /tmp/requirements.txt
# ── PyPI الرسميّ (تمّ التبديل من مرآة Tencent — كانت تُقدِّم حزمة pip بتجزئة مغلوطة) ──
# للتبديل إلى مرآة بديلة: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ أو https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt
COPY services/ai_agronomist /app/ai_agronomist
# حزمة الأدوات المشتركة (shared/ai/*) يستوردها ai_generation/main لحلقة الـHarness
# (V58+): ``from shared.ai import tool_schema/...`` — يجب تضمينها في الصورة وإلّا
# يفشل الإقلاع بـ``ModuleNotFoundError: No module named 'shared'`` (نفس نمط
# guardrails-engine الذي ينسخ shared/). سياق البناء هو جذر المستودع.
COPY shared /app/shared
ENV PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"
# مستخدم غير جذري (SEC-2 — محاذاةً لباقي الخدمات)
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
CMD ["python", "-m", "uvicorn", "ai_agronomist.main:app", "--host", "0.0.0.0", "--port", "8000"]
