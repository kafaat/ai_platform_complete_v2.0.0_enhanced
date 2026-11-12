"""
api/scouting_pins.py — نموذج المشاهدات الميدانيّة (Scouting Pins)

المرحلة ١، البند ٨ من خارطة الطريق. نظير FieldView Scouting Pins، مُكيَّف
للسياق اليمني.

Pin = موقع GPS + صورة + نوع مشكلة (taxonomy يمنيّة) + شدّة + حالة +
علم موسمي/دائم + ملاحظة. offline-first (يُخزَّن في SQLite ويُزامَن).

هذا المنطق pure (تحقّق + taxonomy)؛ الحفظ في الموبايل (SQLite) والمزامنة
(syncEngine) والصور (mediaStore) موجودة فعلاً. الـbackend يتحقّق ويصنّف.

المبدأ: "rule-based قبل ML" — التصنيف هنا قائم على قوائم منسّقة، لا تشخيص آلي.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import HTTPException


class IssueCategory(StrEnum):
    """فئات المشاكل الميدانيّة العامّة."""

    DISEASE = "disease"  # مرض
    PEST = "pest"  # آفة حشريّة
    WEED = "weed"  # أعشاب ضارّة
    NUTRIENT = "nutrient"  # نقص عنصر غذائي
    WATER_STRESS = "water_stress"  # إجهاد مائي
    ABIOTIC = "abiotic"  # غير حيوي (ملوحة، حرق، رياح)
    OTHER = "other"


class Severity(StrEnum):
    LOW = "low"  # خفيف
    MEDIUM = "medium"  # متوسّط
    HIGH = "high"  # شديد


class PinStatus(StrEnum):
    """دورة حياة المشاهدة."""

    NEW = "new"  # جديدة
    CONFIRMED = "confirmed"  # مؤكّدة (مثلاً من مهندس زراعي)
    UNDER_TREATMENT = "under_treatment"  # تحت المعالجة
    RESOLVED = "resolved"  # محلولة


class Persistence(StrEnum):
    SEASONAL = "seasonal"  # موسميّة (تختفي بنهاية الموسم)
    PERMANENT = "permanent"  # دائمة (ملوحة، انحدار — مشكلة بنيويّة)


# ─── Taxonomy: مشاكل شائعة لكلّ محصول يمني ───────────────────────
# rule-based: قوائم منسّقة (لا تشخيص آلي). الأسماء العربيّة للواجهة.
# المصدر: السياق الزراعي اليمني (تربة كلسيّة، نقص N/P/Fe/Zn شائع).

YEMEN_CROP_ISSUES: dict[str, list[dict[str, str]]] = {
    "wheat": [
        {"code": "wheat.rust", "category": "disease", "name_ar": "صدأ القمح"},
        {"code": "wheat.aphid", "category": "pest", "name_ar": "منّ القمح"},
        {
            "code": "wheat.n_deficiency",
            "category": "nutrient",
            "name_ar": "نقص نيتروجين (اصفرار عام)",
        },
        {
            "code": "wheat.fe_deficiency",
            "category": "nutrient",
            "name_ar": "نقص حديد (اصفرار بين العروق)",
        },
    ],
    "barley": [
        {"code": "barley.net_blotch", "category": "disease", "name_ar": "تبقّع شبكي"},
        {"code": "barley.aphid", "category": "pest", "name_ar": "منّ الشعير"},
        {"code": "barley.n_deficiency", "category": "nutrient", "name_ar": "نقص نيتروجين"},
    ],
    "coffee": [
        {"code": "coffee.leaf_rust", "category": "disease", "name_ar": "صدأ أوراق البنّ"},
        {"code": "coffee.berry_borer", "category": "pest", "name_ar": "ثاقبة ثمار البنّ"},
        {"code": "coffee.zn_deficiency", "category": "nutrient", "name_ar": "نقص زنك"},
    ],
    "qat": [
        {"code": "qat.water_stress", "category": "water_stress", "name_ar": "إجهاد مائي"},
        {"code": "qat.scale", "category": "pest", "name_ar": "حشرة قشريّة"},
    ],
    "dates": [
        {"code": "dates.dubas", "category": "pest", "name_ar": "دوباس النخيل"},
        {"code": "dates.bayoud", "category": "disease", "name_ar": "مرض البيوض"},
        {"code": "dates.weevil", "category": "pest", "name_ar": "سوسة النخيل الحمراء"},
    ],
    "mango": [
        {"code": "mango.anthracnose", "category": "disease", "name_ar": "أنثراكنوز المانجو"},
        {"code": "mango.hopper", "category": "pest", "name_ar": "نطّاط أوراق المانجو"},
    ],
    "citrus": [
        {"code": "citrus.greening", "category": "disease", "name_ar": "تخضّر الموالح (HLB)"},
        {"code": "citrus.leafminer", "category": "pest", "name_ar": "صانعة أنفاق الموالح"},
        {"code": "citrus.fe_deficiency", "category": "nutrient", "name_ar": "نقص حديد"},
    ],
    "tomato": [
        {"code": "tomato.late_blight", "category": "disease", "name_ar": "اللفحة المتأخّرة"},
        {"code": "tomato.tuta", "category": "pest", "name_ar": "حفّار أوراق الطماطم (توتا)"},
        {"code": "tomato.whitefly", "category": "pest", "name_ar": "الذبابة البيضاء"},
        {
            "code": "tomato.blossom_end_rot",
            "category": "abiotic",
            "name_ar": "تعفّن الطرف الزهري (نقص كالسيوم)",
        },
    ],
    "pepper": [
        {"code": "pepper.powdery_mildew", "category": "disease", "name_ar": "البياض الدقيقي"},
        {"code": "pepper.thrips", "category": "pest", "name_ar": "التربس"},
    ],
    "onion": [
        {"code": "onion.purple_blotch", "category": "disease", "name_ar": "التبقّع الأرجواني"},
        {"code": "onion.thrips", "category": "pest", "name_ar": "تربس البصل"},
    ],
    "potato": [
        {"code": "potato.late_blight", "category": "disease", "name_ar": "اللفحة المتأخّرة"},
        {"code": "potato.tuber_moth", "category": "pest", "name_ar": "فراشة درنات البطاطس"},
    ],
    "sorghum": [
        {"code": "sorghum.midge", "category": "pest", "name_ar": "ذبابة الذرة الرفيعة"},
        {"code": "sorghum.smut", "category": "disease", "name_ar": "التفحّم"},
    ],
    "alfalfa": [
        {"code": "alfalfa.weevil", "category": "pest", "name_ar": "سوسة البرسيم"},
        {"code": "alfalfa.aphid", "category": "pest", "name_ar": "منّ البرسيم"},
    ],
}

# أعراض نقص العناصر الشائعة في التربة الكلسيّة اليمنيّة (دليل بصري rule-based)
NUTRIENT_DEFICIENCY_GUIDE: list[dict[str, str]] = [
    {"code": "n", "name_ar": "نقص نيتروجين", "sign_ar": "اصفرار عام يبدأ بالأوراق القديمة"},
    {
        "code": "p",
        "name_ar": "نقص فوسفور",
        "sign_ar": "لون أرجواني/داكن، نموّ بطيء (شائع لتثبيت الفوسفور)",
    },
    {
        "code": "fe",
        "name_ar": "نقص حديد",
        "sign_ar": "اصفرار بين العروق في الأوراق الحديثة (شائع بالتربة الكلسيّة)",
    },
    {"code": "zn", "name_ar": "نقص زنك", "sign_ar": "أوراق صغيرة، مسافات قصيرة بين العقد"},
]


@dataclass
class ScoutingPin:
    """مشاهدة ميدانيّة واحدة."""

    pin_id: str
    field_id: str
    lat: float
    lng: float
    issue_category: IssueCategory
    severity: Severity
    status: PinStatus
    persistence: Persistence
    crop: str | None = None
    issue_code: str | None = None  # من الـtaxonomy
    note_ar: str | None = None
    photo_uri: str | None = None  # مسار دائم من mediaStore
    created_at: str = ""
    created_by: str | None = None
    color: str | None = None  # ترميز لوني (واجهة)
    # v257: مصدر الموقع (gps|manual|field_centroid|unknown) ودقّة GPS بالأمتار (لـgps فقط).
    location_source: str = "unknown"
    accuracy_m: float | None = None
    # v257: مستند الصورة في سجلّ المستندات — ليس من هويّة الدبّوس (لا يدخل مقارنة الإعادة).
    photo_document_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pin_id": self.pin_id,
            "field_id": self.field_id,
            "lat": self.lat,
            "lng": self.lng,
            "issue_category": self.issue_category.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "persistence": self.persistence.value,
            "crop": self.crop,
            "issue_code": self.issue_code,
            "note_ar": self.note_ar,
            "photo_uri": self.photo_uri,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "color": self.color,
            "location_source": self.location_source,
            "accuracy_m": self.accuracy_m,
        }


# v257: مصادر الموقع المقبولة (مطابقة لقيد scouting_pins_location_source_ck).
LOCATION_SOURCES = frozenset({"gps", "manual", "field_centroid", "unknown"})

# Yemen bbox (نفس geospatial_integrity) — تحقّق أنّ الـpin داخل اليمن
_YEMEN_BBOX = (41.0, 12.0, 54.6, 19.5)  # (min_lng, min_lat, max_lng, max_lat)


@dataclass
class PinValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)


def validate_pin(
    lat: float,
    lng: float,
    issue_category: str,
    severity: str,
    status: str,
    persistence: str,
    crop: str | None = None,
    issue_code: str | None = None,
    location_source: str = "unknown",
    accuracy_m: float | None = None,
) -> PinValidationResult:
    """يتحقّق من صلاحيّة مشاهدة قبل الحفظ."""
    issues: list[str] = []

    # v257: الدقّة صفة قياس GPS؛ موقع يدويّ أو مركز حقل أو مجهول لا يحمل دقّة.
    if location_source not in LOCATION_SOURCES:
        issues.append(f"مصدر الموقع غير صالح: {location_source}")
    elif accuracy_m is not None and (location_source != "gps" or accuracy_m < 0):
        issues.append("دقّة الموقع تخصّ قراءة GPS فقط (وتكون غير سالبة)")

    # إحداثيّات داخل اليمن
    min_lng, min_lat, max_lng, max_lat = _YEMEN_BBOX
    if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
        issues.append(f"الإحداثيّات ({lat}, {lng}) خارج حدود اليمن")

    # enums صالحة
    for value, enum_cls, label in [
        (issue_category, IssueCategory, "فئة المشكلة"),
        (severity, Severity, "الشدّة"),
        (status, PinStatus, "الحالة"),
        (persistence, Persistence, "الدوام"),
    ]:
        try:
            enum_cls(value)
        except ValueError:
            issues.append(f"{label} غير صالحة: {value}")

    # لو issue_code معطى، تحقّق أنّه ضمن taxonomy المحصول
    if issue_code and crop:
        valid_codes = {i["code"] for i in YEMEN_CROP_ISSUES.get(crop, [])}
        if valid_codes and issue_code not in valid_codes:
            issues.append(f"رمز المشكلة {issue_code} غير معروف للمحصول {crop}")

    return PinValidationResult(valid=len(issues) == 0, issues=issues)


def get_crop_issues(crop: str) -> list[dict[str, str]]:
    """يُرجع قائمة المشاكل الشائعة لمحصول (للقوائم المنسدلة في الواجهة)."""
    return YEMEN_CROP_ISSUES.get(crop, [])


def make_pin(
    pin_id: str,
    field_id: str,
    lat: float,
    lng: float,
    issue_category: str,
    severity: str = "medium",
    status: str = "new",
    persistence: str = "seasonal",
    **kwargs,
) -> ScoutingPin:
    """يبني ScoutingPin بعد التحقّق (يرفع ValueError لو غير صالح)."""
    result = validate_pin(
        lat,
        lng,
        issue_category,
        severity,
        status,
        persistence,
        crop=kwargs.get("crop"),
        issue_code=kwargs.get("issue_code"),
        location_source=kwargs.get("location_source") or "unknown",
        accuracy_m=kwargs.get("accuracy_m"),
    )
    if not result.valid:
        raise ValueError("; ".join(result.issues))

    return ScoutingPin(
        pin_id=pin_id,
        field_id=field_id,
        lat=lat,
        lng=lng,
        issue_category=IssueCategory(issue_category),
        severity=Severity(severity),
        status=PinStatus(status),
        persistence=Persistence(persistence),
        crop=kwargs.get("crop"),
        issue_code=kwargs.get("issue_code"),
        note_ar=kwargs.get("note_ar"),
        photo_uri=kwargs.get("photo_uri"),
        created_at=kwargs.get("created_at") or datetime.now(UTC).isoformat(),
        created_by=kwargs.get("created_by"),
        color=kwargs.get("color"),
        location_source=kwargs.get("location_source") or "unknown",
        accuracy_m=kwargs.get("accuracy_m"),
    )


# ─── الإدامة (RLS، best-effort) — انتقلت من api/routers/fields.py: حدّ حجم الراوتر وحدّ عدد الوحدات ───

# v257: صورة الدبّوس في مخزن المرفقات القائم — البايتات في ``shared.storage.blob_store`` (المسار
# العامّ الوحيد لتخزين الكائنات) والبيانات الوصفيّة في سجلّ ``documents`` (v29، RLS بالمستأجِر).
# المفتاح خادميّ (مستأجِر + بصمة الدبّوس + بصمة المحتوى)، والنوع من magic bytes (JPEG/PNG فقط)،
# والحجم يُقاس على البايتات بعد فكّ base64. مُعرِّف المستند حتميّ من (المستأجِر، الدبّوس)، فإعادة
# الرفع لا تُنشئ مستنداً ثانياً.
MAX_PIN_PHOTO_BYTES = 8 * 1024 * 1024
PIN_PHOTO_PREFIX = "scouting-pin-photos"
_PHOTO_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


@dataclass(frozen=True)
class PinPhoto:
    """صورة مفكوكة ومفحوصة، جاهزة للتخزين."""

    data: bytes
    content_type: str
    ext: str
    sha256: str


def decode_pin_photo(content_b64: str, declared_sha256: str | None = None) -> PinPhoto:
    """يفكّ base64 ويفحص الحجم والنوع (magic bytes) والبصمة المعلنة إن وُجدت."""
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "pin_photo_not_base64") from exc
    if not data:
        raise HTTPException(422, "pin_photo_empty")
    if len(data) > MAX_PIN_PHOTO_BYTES:
        raise HTTPException(413, "pin_photo_too_large")
    detected = next(((ct, ext) for sig, ct, ext in _PHOTO_MAGIC if data.startswith(sig)), None)
    if detected is None:
        raise HTTPException(415, "pin_photo_unsupported_type")
    sha = hashlib.sha256(data).hexdigest()
    if declared_sha256 is not None and declared_sha256 != sha:
        raise HTTPException(422, "pin_photo_sha256_mismatch")
    return PinPhoto(data=data, content_type=detected[0], ext=detected[1], sha256=sha)


def pin_photo_document_id(tenant_id: Any, pin_id: str) -> str:
    """مُعرِّف مستند صورة الدبّوس: حتميّ من (المستأجِر، الدبّوس) — صورة واحدة لكلّ دبّوس."""
    return "pinph_" + hashlib.sha256(f"{tenant_id}\x00{pin_id}".encode()).hexdigest()[:32]


def pin_photo_key(tenant_id: Any, pin_id: str, photo: PinPhoto) -> str:
    """مفتاح الكائن: ``scouting-pin-photos/<tenant>/<sha(pin_id)>/<sha(content)>.<ext>``.

    ``pin_id`` نصّ من العميل، فلا يدخل المسار إلّا مُجزّأً (لا ``..`` ولا ``/``).
    """
    pin_hash = hashlib.sha256(str(pin_id).encode()).hexdigest()[:32]
    return f"{PIN_PHOTO_PREFIX}/{tenant_id}/{pin_hash}/{photo.sha256}.{photo.ext}"


def pin_photo_ref_belongs_to(ref: Any, tenant_id: Any) -> bool:
    """دفاع عمق للتنزيل: المرجع مفتاحٌ كتبه هذا المسار تحت مستأجِر المستدعي.

    ``documents.storage_ref`` قابل للكتابة عبر ``POST /api/v1/documents``، فلا يُقرأ منه إلّا
    مرجع ``s3://<bucket>/scouting-pin-photos/<tenant>/…`` أو ``file://…/scouting-pin-photos/<tenant>/…``.
    """
    if not isinstance(ref, str) or ".." in ref:
        return False
    prefix = f"{PIN_PHOTO_PREFIX}/{tenant_id}/"
    if ref.startswith("s3://"):
        parts = ref[len("s3://") :].split("/", 1)
        return len(parts) == 2 and parts[1].startswith(prefix)
    return ref.startswith("file://") and f"/{prefix}" in ref


def _blob_store():
    from shared.storage import blob_store  # كسول: لا إعداد S3 عند استيراد الوحدة

    return blob_store


async def _attach_pin_photo(conn: Any, user: Any, pin: Any, photo: PinPhoto) -> None:
    """يربط الصورة بالدبّوس داخل معاملة الإدامة نفسها؛ إعادة المحتوى نفسه لا تُكرّر شيئاً."""
    tenant = str(user.tenant_id)
    current = await conn.fetchval(
        "SELECT photo_document_id FROM scouting_pins "
        "WHERE pin_id=$1 AND tenant_id=$2::uuid FOR UPDATE",
        pin.pin_id,
        tenant,
    )
    key = pin_photo_key(tenant, pin.pin_id, photo)
    doc_id = current or pin_photo_document_id(tenant, pin.pin_id)
    stored = await conn.fetchrow("SELECT storage_ref FROM documents WHERE doc_id=$1", doc_id)
    if stored is not None:
        if not str(stored["storage_ref"] or "").endswith("/" + key):
            raise HTTPException(409, "pin_photo_conflict: للدبّوس صورة أخرى محفوظة")
    else:
        store = _blob_store()
        try:
            ref = await asyncio.to_thread(store.upload_bytes, key, photo.data, photo.content_type)
        except store.BlobStoreError as exc:
            raise HTTPException(503, "pin_photo_store_unavailable") from exc
        await conn.execute(
            "INSERT INTO documents (doc_id, tenant_id, category, field_id, title, storage_ref, "
            " content_type, size_bytes, uploaded_by) "
            "VALUES ($1, $2::uuid, 'image', $3, $4, $5, $6, $7, $8) "
            "ON CONFLICT (doc_id) DO NOTHING",
            doc_id,
            tenant,
            pin.field_id,
            f"صورة مشاهدة ميدانيّة {pin.pin_id}"[:200],
            ref,
            photo.content_type,
            len(photo.data),
            str(user.user_id),
        )
    if current is None:
        await conn.execute(
            "UPDATE scouting_pins SET photo_document_id=$3 WHERE pin_id=$1 AND tenant_id=$2::uuid",
            pin.pin_id,
            tenant,
            doc_id,
        )
    pin.photo_document_id = doc_id


async def persist_scouting_pin(
    user: Any,
    pin: Any,
    *,
    pool_ready: bool,
    connect: Callable[[Any], Any],
    photo: PinPhoto | None = None,
) -> bool:
    """يُثبّت الدبّوس؛ ``True`` لو ثُبِّت (أو كان موجوداً مطابقاً)، ``False`` لو تعذّرت القاعدة.

    * حقلٌ ليس ضمن مستأجِر المستدعي ⇒ 404 (فحصٌ تحت RLS قبل الإدراج).
    * إعادة إرسال مطابقة ⇒ تُرجَع القيمة المخزَّنة (``created_at`` الأصليّ).
    * المُعرِّف نفسه بمحتوى مختلف (ومنه مصدر الموقع ودقّته) ⇒ 409.
    * ``photo`` (v257) تُربط في المعاملة نفسها؛ صورة مختلفة لدبّوس له صورة ⇒ 409، وتعذّر
      المخزن ⇒ 503 (تُلغى المعاملة كلّها فيعيد العميل المحاولة).
    * ``created_at`` يُمرَّر قيمة datetime إلى ``::timestamptz`` (النصّ كان يُرفَض بصمت).
    SQL بارامتريّ بالكامل.
    """
    if not pool_ready:
        return False
    try:
        async with connect(user) as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM fields WHERE field_id=$1 AND tenant_id=$2::uuid",
                pin.field_id,
                str(user.tenant_id),
            )
            if not exists:
                raise HTTPException(404, "الحقل غير موجود ضمن هذا المستأجر")
            result = await conn.execute(
                "INSERT INTO scouting_pins "
                "(pin_id, tenant_id, field_id, lat, lng, issue_category, severity, "
                " status, persistence, crop, issue_code, note_ar, photo_uri, color, "
                " created_by, location_source, accuracy_m, created_at) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, "
                " $13, $14, $15, $16, $17, $18::timestamptz) "
                "ON CONFLICT (pin_id) DO NOTHING",
                pin.pin_id,
                str(user.tenant_id),
                pin.field_id,
                pin.lat,
                pin.lng,
                pin.issue_category.value,
                pin.severity.value,
                pin.status.value,
                pin.persistence.value,
                pin.crop,
                pin.issue_code,
                pin.note_ar,
                pin.photo_uri,
                pin.color,
                pin.created_by,
                pin.location_source,
                pin.accuracy_m,
                datetime.fromisoformat(pin.created_at),
            )
            if result == "INSERT 0 0":
                previous = await conn.fetchrow(
                    "SELECT * FROM scouting_pins WHERE pin_id=$1 AND tenant_id=$2::uuid",
                    pin.pin_id,
                    str(user.tenant_id),
                )
                if previous is None or any(
                    previous[key] != value
                    for key, value in pin.to_dict().items()
                    if key != "created_at"
                ):
                    raise HTTPException(409, "معرّف الدبوس مستخدم لمشاهدة مختلفة")
                pin.created_at = previous["created_at"].isoformat()
                pin.photo_document_id = dict(previous).get("photo_document_id")
            if photo is not None:
                await _attach_pin_photo(conn, user, pin, photo)
        return True
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — إدامة best-effort: تعذّر القاعدة ⇒ persisted=false
        logging.warning("scouting pin persistence failed for pin %s", pin.pin_id)
        return False


async def load_pin_photo(
    user: Any, doc_id: str, *, connect: Callable[[Any], Any]
) -> tuple[bytes, str]:
    """بايتات صورة دبّوس ونوعها لـ ``GET /api/v1/documents/{doc_id}?content=true``.

    تُقرأ تحت RLS المستأجِر: مستند لا يربطه دبّوسٌ مرئيّ للمستدعي، أو مرجعه ليس مفتاحاً كتبه
    هذا المسار تحت مستأجِره ⇒ 404 (مستأجِر آخر لا يعرف حتّى أنّ المستند موجود).
    """
    async with connect(user) as conn:
        row = await conn.fetchrow(
            "SELECT d.storage_ref, d.content_type FROM documents d WHERE d.doc_id = $1 "
            "AND EXISTS (SELECT 1 FROM scouting_pins p WHERE p.photo_document_id = d.doc_id)",
            doc_id,
        )
    if row is None or not pin_photo_ref_belongs_to(row["storage_ref"], user.tenant_id):
        raise HTTPException(404, "صورة الدبّوس غير موجودة")
    store = _blob_store()
    try:
        data = await asyncio.to_thread(store.read_bytes, row["storage_ref"], MAX_PIN_PHOTO_BYTES)
    except store.BlobStoreError as exc:
        raise HTTPException(503, "pin_photo_store_unavailable") from exc
    return data, row["content_type"] or "application/octet-stream"


def pin_photo_view(document_id: str | None, **meta: Any) -> dict[str, Any] | None:
    """ما يراه العميل من صورة الدبّوس: المستند ومسار فتحه (لا المرجع الداخليّ للمخزن)."""
    if not document_id:
        return None
    return {
        "document_id": document_id,
        "status": "stored",
        "content_url": f"/api/v1/documents/{document_id}?content=true",
        **{k: v for k, v in meta.items() if v is not None},
    }


async def create_scouting_pin(
    field_id: str, req: Any, user: Any, *, persist: Callable[..., Any]
) -> dict[str, Any]:
    """جسم ``POST /api/v1/fields/{field_id}/pins`` (المسار في الراوتر غلاف رفيع — حدّ حجمه).

    تحقّق ⇒ إدامة تحت RLS (best-effort) ⇒ الدبّوس مُطبَّعاً مع ``persisted`` و``photo``.
    """
    if req.field_id != field_id:
        raise HTTPException(422, "معرّف الحقل لا يطابق المسار")
    try:
        pin = make_pin(
            req.pin_id,
            field_id,
            req.lat,
            req.lng,
            req.issue_category,
            req.severity,
            req.status,
            req.persistence,
            crop=req.crop,
            issue_code=req.issue_code,
            note_ar=req.note_ar,
            photo_uri=req.photo_uri,
            color=req.color,
            created_by=user.user_id,
            location_source=req.location_source,
            accuracy_m=req.accuracy_m,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    photo = decode_pin_photo(req.photo.content_b64, req.photo.sha256) if req.photo else None
    persisted = await persist(user, pin, photo)
    out = pin.to_dict()
    out["persisted"] = persisted
    if photo is not None and not persisted:
        out["photo"] = {"status": "not_stored"}  # القاعدة غير متاحة: يعيد العميل الإرسال
    elif photo is not None:
        out["photo"] = pin_photo_view(
            pin.photo_document_id,
            content_type=photo.content_type,
            size_bytes=len(photo.data),
            sha256=photo.sha256,
        )
    else:
        out["photo"] = pin_photo_view(pin.photo_document_id)
    return out
