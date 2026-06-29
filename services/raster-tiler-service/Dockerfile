FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "titiler.application>=0.20,<0.23" "uvicorn[standard]>=0.30,<0.34"
EXPOSE 8088
CMD ["uvicorn", "titiler.application.main:app", "--host", "0.0.0.0", "--port", "8088"]
