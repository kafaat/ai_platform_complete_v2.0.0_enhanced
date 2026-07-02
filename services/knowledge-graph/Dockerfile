FROM python:3.12-slim-bookworm
WORKDIR /app
COPY services/knowledge-graph/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/sahool-platform/core /app/core
COPY services/knowledge-graph/main.py /app/main.py
ENV PYTHONPATH=/app KG_SQLITE_PATH=/data/kg.sqlite
# مستخدم غير جذري (SEC-2). /data قابل للكتابة (KG_SQLITE_PATH) — يُنشأ ويُملَّك قبل
# VOLUME كي تُحفظ الملكيّة في نقطة التركيب (تغييرات ما بعد VOLUME تُهمَل عند البناء).
RUN useradd -m sahool && mkdir -p /data && chown -R sahool:sahool /app /data
USER sahool
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
