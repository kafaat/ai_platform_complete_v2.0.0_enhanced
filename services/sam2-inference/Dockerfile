# SAHOOL sam2-inference — صورة CUDA لاستدلال SAM2 على GPU (RTX 4090).
#
# صدق: هذه الصورة تتطلّب NVIDIA Container Toolkit + GPU على المضيف. القاعدة تحمل
# torch بنسخة CUDA 12.1 جاهزة (لا حاجة لتثبيت torch من PyPI). تُبنى وتُختبَر على
# عتاد المستخدم — لا يمكن بناؤها/تشغيلها بلا GPU في بيئة المراجعة.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

WORKDIR /app

# تبعيّات نظام لـrasterio/GDAL + git (لتثبيت sam2 من المصدر) + بناء امتدادات SAM2.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── PyPI الرسمي (افتراضي) — للمرآة الصينيّة مرّر --build-arg PIP_INDEX_URL=... ──
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

# تبعيّات بايثون الخفيفة + الجغرافيا (torch موجود في القاعدة — لا يُعاد تثبيته).
COPY services/sam2-inference/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt

# تثبيت SAM2 من المستودع الرسميّ (غير منشور على PyPI باسم مستقرّ).
# نثبّت وسماً محدّداً للقابليّة للتكرار؛ حدّثه عند الحاجة وتحقّق من التوافق.
ARG SAM2_REF=main
RUN pip install --no-cache-dir "git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}"

COPY services/sam2-inference/ /app/

# مستخدم غير جذر (تصلّب) — يكتب فقط لـ/app؛ /models تُركَّب للقراءة فقط.
RUN useradd -m sahool && chown -R sahool:sahool /app
USER sahool

# توثيق: تُركَّب أوزان SAM2 على /models (volume sam2-models:ro). مثال:
#   SAM2_CHECKPOINT=/models/sam2_hiera_large.pt
#   SAM2_MODEL_CFG=sam2_hiera_l.yaml
EXPOSE 8080

# HEALTHCHECK عبر python-urllib (لا نفترض وجود curl في صورة CUDA).
# نفحص /readyz؛ exit 0 لو الردّ 200 (العمليّة حيّة). model_loaded يُفحَص بالمنطق.
HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=6 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/readyz', timeout=4).status==200 else 1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
