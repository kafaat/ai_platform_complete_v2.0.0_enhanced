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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class IssueCategory(str, Enum):
    """فئات المشاكل الميدانيّة العامّة."""
    DISEASE = "disease"              # مرض
    PEST = "pest"                    # آفة حشريّة
    WEED = "weed"                    # أعشاب ضارّة
    NUTRIENT = "nutrient"            # نقص عنصر غذائي
    WATER_STRESS = "water_stress"    # إجهاد مائي
    ABIOTIC = "abiotic"              # غير حيوي (ملوحة، حرق، رياح)
    OTHER = "other"


class Severity(str, Enum):
    LOW = "low"          # خفيف
    MEDIUM = "medium"    # متوسّط
    HIGH = "high"        # شديد


class PinStatus(str, Enum):
    """دورة حياة المشاهدة."""
    NEW = "new"                      # جديدة
    CONFIRMED = "confirmed"          # مؤكّدة (مثلاً من مهندس زراعي)
    UNDER_TREATMENT = "under_treatment"  # تحت المعالجة
    RESOLVED = "resolved"            # محلولة


class Persistence(str, Enum):
    SEASONAL = "seasonal"    # موسميّة (تختفي بنهاية الموسم)
    PERMANENT = "permanent"  # دائمة (ملوحة، انحدار — مشكلة بنيويّة)


# ─── Taxonomy: مشاكل شائعة لكلّ محصول يمني ───────────────────────
# rule-based: قوائم منسّقة (لا تشخيص آلي). الأسماء العربيّة للواجهة.
# المصدر: السياق الزراعي اليمني (تربة كلسيّة، نقص N/P/Fe/Zn شائع).

YEMEN_CROP_ISSUES: Dict[str, List[Dict[str, str]]] = {
    "wheat": [
        {"code": "wheat.rust", "category": "disease", "name_ar": "صدأ القمح"},
        {"code": "wheat.aphid", "category": "pest", "name_ar": "منّ القمح"},
        {"code": "wheat.n_deficiency", "category": "nutrient", "name_ar": "نقص نيتروجين (اصفرار عام)"},
        {"code": "wheat.fe_deficiency", "category": "nutrient", "name_ar": "نقص حديد (اصفرار بين العروق)"},
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
        {"code": "tomato.blossom_end_rot", "category": "abiotic", "name_ar": "تعفّن الطرف الزهري (نقص كالسيوم)"},
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
NUTRIENT_DEFICIENCY_GUIDE: List[Dict[str, str]] = [
    {"code": "n", "name_ar": "نقص نيتروجين", "sign_ar": "اصفرار عام يبدأ بالأوراق القديمة"},
    {"code": "p", "name_ar": "نقص فوسفور", "sign_ar": "لون أرجواني/داكن، نموّ بطيء (شائع لتثبيت الفوسفور)"},
    {"code": "fe", "name_ar": "نقص حديد", "sign_ar": "اصفرار بين العروق في الأوراق الحديثة (شائع بالتربة الكلسيّة)"},
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
    crop: Optional[str] = None
    issue_code: Optional[str] = None      # من الـtaxonomy
    note_ar: Optional[str] = None
    photo_uri: Optional[str] = None       # مسار دائم من mediaStore
    created_at: str = ""
    created_by: Optional[str] = None
    color: Optional[str] = None           # ترميز لوني (واجهة)

    def to_dict(self) -> Dict[str, Any]:
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
        }


# Yemen bbox (نفس geospatial_integrity) — تحقّق أنّ الـpin داخل اليمن
_YEMEN_BBOX = (41.0, 12.0, 54.6, 19.5)  # (min_lng, min_lat, max_lng, max_lat)


@dataclass
class PinValidationResult:
    valid: bool
    issues: List[str] = field(default_factory=list)


def validate_pin(
    lat: float,
    lng: float,
    issue_category: str,
    severity: str,
    status: str,
    persistence: str,
    crop: Optional[str] = None,
    issue_code: Optional[str] = None,
) -> PinValidationResult:
    """يتحقّق من صلاحيّة مشاهدة قبل الحفظ."""
    issues: List[str] = []

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


def get_crop_issues(crop: str) -> List[Dict[str, str]]:
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
        lat, lng, issue_category, severity, status, persistence,
        crop=kwargs.get("crop"), issue_code=kwargs.get("issue_code"),
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
        created_at=kwargs.get("created_at") or datetime.now(timezone.utc).isoformat(),
        created_by=kwargs.get("created_by"),
        color=kwargs.get("color"),
    )
