"""
api/field_cameras.py — مراقبة الحقول بالكاميرا (عين ميدانيّة، لا كشف آلي)

كاميرات المراقبة في الحقل قرينة بصريّة مفيدة: يراها المزارع/المهندس بنفسه،
وتوثّق حالة الحقل أرضيّاً (ما لا يراه القمر تحت الغطاء النباتي).

التمييز الجوهري (مبدأ الصدق العلمي + human-in-the-loop):
  ✅ مقبول: تسجيل الكاميرات، حفظ اللقطات الدوريّة، ربطها بنقاط الاستكشاف،
            عرضها للمزارع ليقرّر بنفسه، وإدخالها كقرينة field_obs في التظافر.
  ❌ مرفوض: الكشف الآلي بالـML (YOLO/pest detection) — يحتاج بيانات آفات
            يمنيّة مُوسَمة نفتقدها = ثقة زائفة؛ والإنذار الآلي يصطدم بـ
            human-in-the-loop. (رُفِض video-processor السابق لهذا السبب.)

أي: الكاميرا "عين" تُري المزارع، لا "عقل" يقرّر عنه. التشخيص يبقى بشريّاً
(أو عبر disease_diagnosis الشفّاف القائم على القواعد، لا ML الصندوق الأسود).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CameraType(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    FIXED = "fixed"  # كاميرا ثابتة (عمود/برج)
    MOBILE = "mobile"  # محمولة (هاتف/جهاز المزارع)
    TIMELAPSE = "timelapse"  # لقطات دوريّة مجدولة


class CameraStatus(str, Enum):  # noqa: UP042 (intentional str-mixin for JSON/Pydantic value serialization)
    ACTIVE = "active"
    OFFLINE = "offline"  # متوقّعة في الريف (كهرباء/شبكة متقطّعة)
    ARCHIVED = "archived"


@dataclass
class FieldCamera:
    """كاميرا مراقبة مسجّلة لحقل."""

    camera_id: str
    field_id: str
    name_ar: str
    camera_type: CameraType
    status: CameraStatus = CameraStatus.ACTIVE
    lat: float | None = None
    lon: float | None = None
    capture_interval_min: int | None = None  # للـtimelapse
    note_ar: str = ""

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "field_id": self.field_id,
            "name_ar": self.name_ar,
            "camera_type": self.camera_type.value,
            "status": self.status.value,
            "lat": self.lat,
            "lon": self.lon,
            "capture_interval_min": self.capture_interval_min,
            "note_ar": self.note_ar,
        }


@dataclass
class CameraSnapshot:
    """لقطة بصريّة من كاميرا (قرينة ميدانيّة)."""

    snapshot_id: str
    camera_id: str
    field_id: str
    media_uri: str  # مسار الصورة (في mediaStore/MinIO)
    captured_at: str  # ISO
    linked_pin_id: str | None = None  # ربط بنقطة استكشاف إن وُجدت
    note_ar: str = ""

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "camera_id": self.camera_id,
            "field_id": self.field_id,
            "media_uri": self.media_uri,
            "captured_at": self.captured_at,
            "linked_pin_id": self.linked_pin_id,
            "note_ar": self.note_ar,
        }


def register_camera(
    camera_id: str,
    field_id: str,
    name_ar: str,
    camera_type: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    capture_interval_min: int | None = None,
    note_ar: str = "",
) -> dict:
    """يسجّل كاميرا مراقبة لحقل (نقيّة — الحفظ في الموبايل/الـbackend عبر المستودع)."""
    try:
        ctype = CameraType(camera_type)
    except ValueError as err:
        raise ValueError(f"نوع كاميرا غير معروف: {camera_type}") from err

    cam = FieldCamera(
        camera_id=camera_id,
        field_id=field_id,
        name_ar=name_ar,
        camera_type=ctype,
        lat=lat,
        lon=lon,
        capture_interval_min=capture_interval_min,
        note_ar=note_ar,
    )
    return {
        "camera": cam.to_dict(),
        "ml_auto_detection": False,
        "purpose_ar": "عين ميدانيّة للعرض والتوثيق — لا كشف آلي",
        "disclaimer_ar": (
            "الكاميرا توثّق الحقل بصريّاً ويراها المزارع/المهندس بنفسه. لا يوجد "
            "كشف آلي للآفات بالذكاء الاصطناعي (يحتاج بيانات يمنيّة مُوسَمة نفتقدها). "
            "التشخيص بشري، أو عبر محرّك التشخيص الشفّاف القائم على القواعد."
        ),
    }


def link_snapshot_as_evidence(snapshot: CameraSnapshot) -> dict:
    """يحوّل لقطة كاميرا إلى قرينة ميدانيّة (field_obs) للتظافر.

    اللقطة قرينة بصريّة بوزن منخفض (ملاحظة ميدانيّة) — لا ترفع توصية وحدها،
    لكنّها تُسهم مع قرائن أخرى (نفس منطق evidence_corroboration).
    """
    return {
        "snapshot": snapshot.to_dict(),
        "evidence_type": "field_obs",  # يطابق EvidenceType في التظافر
        "weight_note_ar": (
            "لقطة الكاميرا قرينة بصريّة ميدانيّة (وزن منخفض). تُعرَض للمزارع "
            "وتُسهم في تظافر القرائن، لكنّها لا تُنتج تشخيصاً آليّاً ولا ترفع "
            "توصية وحدها. للتشخيص: راجعها بصريّاً أو استخدم محرّك التشخيص بالقواعد."
        ),
    }


def monitoring_summary(cameras: list[FieldCamera]) -> dict:
    """ملخّص حالة كاميرات حقل (كم نشطة/متوقّفة)."""
    active = sum(1 for c in cameras if c.status == CameraStatus.ACTIVE)
    offline = sum(1 for c in cameras if c.status == CameraStatus.OFFLINE)
    return {
        "total": len(cameras),
        "active": active,
        "offline": offline,
        "offline_note_ar": (
            "انقطاع الكاميرات متوقّع في الريف (كهرباء/شبكة متقطّعة) — "
            "النظام offline-first ويعرض آخر لقطة محفوظة عند الانقطاع."
            if offline > 0
            else ""
        ),
    }
