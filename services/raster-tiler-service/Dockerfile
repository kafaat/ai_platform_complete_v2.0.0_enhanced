FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# libexpat1 مطلوبة من rasterio (عبر GDAL) — غائبة في صورة slim الافتراضيّة
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
# ── PyPI الرسميّ (تمّ التبديل من مرآة Tencent — كانت تُقدِّم حزمة pip بتجزئة مغلوطة) ──
# للتبديل إلى مرآة بديلة: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ أو https://mirrors.cloud.tencent.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple/
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir "titiler.application>=0.20,<0.23" "uvicorn[standard]>=0.30,<0.34"
EXPOSE 8088
# مستخدم غير جذري (SEC-2). لا يوجد /app منسوخ؛ titiler يقرأ COG عن بُعد فقط.
# useradd -m يوفّر HOME قابلًا للكتابة لأيّ ذاكرة مؤقّتة من GDAL/rasterio.
RUN useradd -m sahool
USER sahool
CMD ["uvicorn", "titiler.application.main:app", "--host", "0.0.0.0", "--port", "8088"]
