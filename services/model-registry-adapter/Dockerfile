FROM python:3.13-slim
WORKDIR /app
COPY adapter.py worker.py runtime.py service.py ./
RUN useradd --system --uid 10001 runtime
USER 10001
ENV PYTHONUNBUFFERED=1 PORT=8099
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/readyz',timeout=2)"
CMD ["python", "service.py"]
