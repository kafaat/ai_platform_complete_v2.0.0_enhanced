"""تخزين كائنات اختياري (S3/MinIO) لـCOGs المؤشّرات المقصوصة.

الهدف: جعل تخزين الـCOG قابلاً للتوصيل (pluggable) ليكون النظام قابلاً للتوسّع
أفقيّاً. اليوم يُكتب الـCOG على القرص المحلّي (UPLOAD_DIR) ويُخزَّن cog_url
كـ`file:///path` — وهذا لا يعمل عبر عدّة مضيفين (COG على مضيف ليس على آخر).

عند ضبط S3 (S3_BUCKET + S3_ENDPOINT) نرفع الـCOG ونخزّن `s3://bucket/key`،
والقراءة تتمّ عبر GDAL `/vsis3/`. عند عدم الضبط نُبقي سلوك `file://` الحالي
حرفيّاً دون أيّ تغيير.

⚠ boto3 اختياريّ: مطلوب فقط عند ضبط S3_*؛ مسار file:// يعمل دونه. لذا
import boto3 محروس داخل الدوالّ (try/except) كي يستورد هذا الموديول بلا boto3.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("raster-service.object_store")

# ─── الإعداد من البيئة ────────────────────────────────────────────
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "")
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_USE_SSL = os.getenv("S3_USE_SSL", "false")


def _use_ssl() -> bool:
    return str(S3_USE_SSL).strip().lower() in ("1", "true", "yes", "on")


def _endpoint_host() -> str:
    """يجرّد المخطّط (http/https) من S3_ENDPOINT ليُرجِع host:port فقط — هذا ما
    يتوقّعه GDAL في AWS_S3_ENDPOINT (بلا scheme)."""
    ep = S3_ENDPOINT.strip()
    for prefix in ("https://", "http://"):
        if ep.startswith(prefix):
            ep = ep[len(prefix) :]
            break
    return ep.rstrip("/")


def _endpoint_url() -> str:
    """URL كامل بمخطّط (http/https) لـboto3 — يتطلّب scheme، عكس GDAL.

    FIX: تمرير S3_ENDPOINT الخام (host:port بلا scheme) إلى boto3 endpoint_url
    يرمي 'Invalid endpoint' فيسقط الرفع لـfile://. نبني المخطّط من S3_USE_SSL.
    """
    host = _endpoint_host()
    if not host:
        return ""
    scheme = "https" if _use_ssl() else "http"
    return f"{scheme}://{host}"


def enabled() -> bool:
    """True فقط إذا ضُبط كلٌّ من S3_BUCKET و S3_ENDPOINT."""
    return bool(S3_BUCKET) and bool(S3_ENDPOINT)


def gdal_configure() -> None:
    """يضبط متغيّرات بيئة GDAL/AWS كي تعمل rasterio `/vsis3/` ضدّ MinIO.

    آمنٌ للاستدعاء دائماً (no-op إن لم يكن enabled()). يُستدعى مرّة عند الاستيراد.
    """
    if not enabled():
        return
    os.environ["AWS_S3_ENDPOINT"] = _endpoint_host()
    if S3_ACCESS_KEY:
        os.environ["AWS_ACCESS_KEY_ID"] = S3_ACCESS_KEY
    if S3_SECRET_KEY:
        os.environ["AWS_SECRET_ACCESS_KEY"] = S3_SECRET_KEY
    os.environ["AWS_DEFAULT_REGION"] = S3_REGION
    os.environ["AWS_HTTPS"] = "YES" if _use_ssl() else "NO"
    # MinIO يستخدم path-style (bucket في المسار) لا virtual-hosting (bucket في النطاق).
    os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
    # تحسين القراءة الجزئيّة من /vsis3 (لا فهرسة دليل عند الفتح).
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif"


def upload_cog(local_path: str, key: str) -> str:
    """يرفع COG محلّي إلى الدلو تحت `key` ويُرجِع `s3://{bucket}/{key}`.

    عند أيّ فشل (boto3 مفقود، شبكة، إلخ) يسجّل تحذيراً ويُرجِع
    `file://{local_path}` (تدهور لطيف — لا يرفع استثناءً أبداً). إن لم يكن
    enabled() يُرجِع `file://{local_path}` مباشرة.
    """
    if not enabled():
        return f"file://{local_path}"
    try:
        import boto3
        from botocore.client import Config

        client = boto3.client(
            "s3",
            endpoint_url=_endpoint_url(),
            aws_access_key_id=S3_ACCESS_KEY or None,
            aws_secret_access_key=S3_SECRET_KEY or None,
            region_name=S3_REGION,
            use_ssl=_use_ssl(),
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        # أنشئ الدلو إن لم يكن موجوداً (best-effort — قد يكون موجوداً سلفاً).
        try:
            client.head_bucket(Bucket=S3_BUCKET)
        except Exception:  # noqa: BLE001 — الدلو غير موجود/لا صلاحية رأس → جرّب الإنشاء
            try:
                client.create_bucket(Bucket=S3_BUCKET)
            except Exception as _ce:  # noqa: BLE001 — قد يكون موجوداً (سباق) أو لا صلاحية
                logger.warning("create_bucket(%s) failed (continuing): %s", S3_BUCKET, _ce)
        client.upload_file(local_path, S3_BUCKET, key)
        return f"s3://{S3_BUCKET}/{key}"
    except Exception as _e:  # noqa: BLE001 — أيّ فشل → تدهور لطيف إلى file://
        logger.warning(
            "upload_cog to s3://%s/%s failed, falling back to file://%s: %s",
            S3_BUCKET,
            key,
            local_path,
            _e,
        )
        return f"file://{local_path}"


def to_gdal_path(uri: str) -> str:
    """يحوّل URI مخزَّن إلى مسار تفهمه rasterio.open / tile_render.

    `s3://b/k` → `/vsis3/b/k`؛ `file://p` → `p`؛ أيّ شيء آخر يُعاد كما هو.
    """
    if uri.startswith("s3://"):
        return "/vsis3/" + uri[len("s3://") :]
    if uri.startswith("file://"):
        return uri[len("file://") :]
    return uri


def exists_locally(uri: str) -> bool:
    """فحص التوافر: لـ`file://` نفحص القرص؛ لـ`s3://`/`/vsis3` نُرجِع True
    (نؤجّل التحقّق من الوجود إلى rasterio — لا نستعلم عن الكائن هنا)."""
    if uri.startswith("file://"):
        return os.path.exists(uri[len("file://") :])
    if uri.startswith("s3://") or uri.startswith("/vsis3"):
        return True
    # مسار قرص خام (بلا scheme) — افحصه كما هو.
    return os.path.exists(uri)


# اضبط GDAL مرّة عند الاستيراد (no-op إن لم يُضبط S3).
gdal_configure()
