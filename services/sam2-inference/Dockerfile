# SAHOOL sam2-inference — صورة CUDA لاستدلال SAM2 على GPU (RTX 4090/5090).
#
# صدق: هذه الصورة تتطلّب NVIDIA Container Toolkit + GPU على المضيف. القاعدة تحمل
# torch بنسخة CUDA حديثة جاهزة (افتراضي CUDA 12.8 لـRTX 50/Blackwell) (لا حاجة لتثبيت torch من PyPI). تُبنى وتُختبَر على
# عتاد المستخدم — لا يمكن بناؤها/تشغيلها بلا GPU في بيئة المراجعة.
ARG PYTORCH_CUDA_IMAGE=pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime
FROM ${PYTORCH_CUDA_IMAGE}

WORKDIR /app

# تبعيّات نظام لـrasterio/GDAL + git (لتثبيت sam2 من المصدر) + بناء امتدادات SAM2.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── PyPI الرسمي افتراضياً؛ يمكن استخدام Alibaba mirror عبر build arg ──
# Alibaba override: --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

# تبعيّات بايثون الخفيفة + الجغرافيا (torch موجود في القاعدة — لا يُعاد تثبيته).
COPY services/sam2-inference/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --timeout 300 --retries 10 -r /tmp/requirements.txt

# تثبيت SAM2 من المستودع الرسميّ (غير منشور على PyPI باسم مستقرّ).
# نثبّت وسماً محدّداً للقابليّة للتكرار؛ حدّثه عند الحاجة وتحقّق من التوافق.
#
# ⚠️ أداء البناء (درس حقليّ): بلا الرايتين أدناه علِق التثبيت 20+ دقيقة عند
#   «Installing build dependencies: still running…»:
#   • --no-build-isolation: يُعيد استخدام torch الموجود في صورة القاعدة بدل إنشاء
#     بيئة بناء معزولة تُعيد تنزيل torch/CUDA الضخمة من الصفر. (torch/setuptools
#     حاضران في pytorch/pytorch الأساس.)
#   • SAM2_BUILD_CUDA=0: يتخطّى تصريف امتداد CUDA الاختياريّ (connected-components
#     postprocessing) بـnvcc — يُستخدَم بديل PyTorch النقيّ (أبطأ قليلاً لتلك العمليّة
#     فقط، لا يؤثّر على دقّة القناع). فعّله لاحقاً (=1) إن أردت النواة الأسرع.
ARG SAM2_REF=main
ENV SAM2_BUILD_CUDA=0
# ضمان توفّر خلفيّة البناء لـ--no-build-isolation (setuptools/wheel/torch حاضرة عادةً
# في صورة pytorch الأساس؛ نثبّتها صراحةً كتأمين ضدّ صورة قاعدة نحيلة).
RUN pip install --timeout 300 --retries 10 --no-cache-dir --upgrade "setuptools>=61.0" wheel \
    && pip install --timeout 300 --retries 10 --no-cache-dir --no-build-isolation \
        "git+https://github.com/facebookresearch/sam2.git@${SAM2_REF}"

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
