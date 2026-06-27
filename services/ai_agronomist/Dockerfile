FROM python:3.12-slim-bookworm
WORKDIR /app
COPY services/ai_agronomist/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/ai_agronomist /app/ai_agronomist
ENV PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "ai_agronomist.main:app", "--host", "0.0.0.0", "--port", "8000"]
