FROM python:3.12-slim-bookworm
WORKDIR /app
COPY services/rag-retrieval/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/sahool-platform/core /app/core
# SEC-3: shared gateway-trusted identity helpers (shared.security.trusted_tenant).
# Must be copied or the container crashes at import (ModuleNotFoundError: shared).
COPY shared /app/shared
COPY services/rag-retrieval/main.py /app/main.py
ENV PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"
# مستخدم غير جذري (SEC-2 — محاذاةً لباقي الخدمات)
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
