"""
sahool_core.crop_cards.loader
==============================
مُحمّل بطاقات المحاصيل + متحقّق من مطابقة القالب المعياري.

كل بطاقة محصول تتبع القالب (_TEMPLATE.yaml): محايدة الموقع، فيزياء
وفسيولوجيا فقط، بمصادر موثّقة (FAO-56, Maas-Hoffman, ECOCROP, NGRC).
المعايرة والإنتاج ممنوعة في البطاقة (مخرجات districts/tenant).
"""
from __future__ import annotations
import re
from pathlib import Path
import yaml

CARDS_DIR = Path(__file__).parent


def _safe_id(card_id: str) -> str | None:
    """يعقّم معرّف البطاقة لمنع path traversal.
    يسمح فقط بحروف/أرقام/شرطة سفلية — يرفض المسارات الصاعدة والفواصل."""
    if not card_id or not re.fullmatch(r"[A-Za-z0-9_]+", card_id):
        return None
    return card_id

# الحقول الإلزامية في كل بطاقة (المعيار المتّبع)
REQUIRED_TOP = {"crop_id", "name_ar", "name_en", "crop_family",
                "kc", "salinity", "thermal", "governing", "modifying"}
REQUIRED_KC = {"initial", "mid", "end", "stage_days", "source"}
REQUIRED_SALINITY = {"threshold_ece_ds_m", "slope_pct_per_ds_m", "source"}
# حقول ممنوعة (تكسر حياد الموقع)
FORBIDDEN = {"zone_factor", "yield", "expected_yield", "calibration",
             "region", "farm", "tenant"}


def load_crop_card(crop_id: str) -> dict | None:
    """يحمّل بطاقة محصول بمعرّفها (مع حماية من path traversal)."""
    safe = _safe_id(crop_id)
    if safe is None:
        return None
    path = CARDS_DIR / f"{safe}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_crop_cards() -> list[str]:
    """يُرجع معرّفات كل البطاقات المتاحة (عدا القالب)."""
    return sorted(p.stem for p in CARDS_DIR.glob("*.yaml")
                  if not p.stem.startswith("_"))


def validate_crop_card(card: dict) -> dict:
    """يتحقّق أن البطاقة تتبع القالب المعياري وتحترم حياد الموقع."""
    errors = []
    missing = REQUIRED_TOP - set(card.keys())
    if missing:
        errors.append(f"حقول مفقودة: {missing}")
    if "kc" in card and (REQUIRED_KC - set(card["kc"].keys())):
        errors.append(f"kc ناقص: {REQUIRED_KC - set(card['kc'].keys())}")
    if "salinity" in card and (REQUIRED_SALINITY - set(card["salinity"].keys())):
        errors.append(f"salinity ناقص: {REQUIRED_SALINITY - set(card['salinity'].keys())}")
    # حياد الموقع: لا حقول معايرة/إنتاج/منطقة
    forbidden_found = FORBIDDEN & set(card.keys())
    if forbidden_found:
        errors.append(f"حقول تكسر حياد الموقع: {forbidden_found}")
    # كل كتلة فيزيائية يجب أن تذكر مصدرها
    for block in ("kc", "salinity"):
        if block in card and "source" not in card[block]:
            errors.append(f"{block} بلا مصدر موثّق")
    return {"valid": len(errors) == 0, "errors": errors,
            "crop_id": card.get("crop_id", "?")}


# ════════════════════════════════════════════════════════════
# بطاقات الأصناف (Varieties) — مستوى أدقّ من المحصول
# ════════════════════════════════════════════════════════════
VARIETIES_DIR = CARDS_DIR / "varieties"

REQUIRED_VARIETY = {"variety_id", "parent_crop_id", "name_ar", "name_en",
                    "passport", "distinctness", "variety_traits"}


def load_variety_card(variety_id: str) -> dict | None:
    """يحمّل بطاقة صنف بمعرّفها (مع حماية من path traversal)."""
    safe = _safe_id(variety_id)
    if safe is None:
        return None
    path = VARIETIES_DIR / f"{safe}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_variety_cards() -> list[str]:
    """يُرجع معرّفات كل الأصناف المتاحة."""
    if not VARIETIES_DIR.exists():
        return []
    return sorted(p.stem for p in VARIETIES_DIR.glob("*.yaml")
                  if not p.stem.startswith("_"))


def varieties_of_crop(crop_id: str) -> list[str]:
    """يُرجع أصناف محصول معيّن (ربط الصنف بمحصوله الأمّ)."""
    out = []
    for vid in list_variety_cards():
        v = load_variety_card(vid)
        if v and v.get("parent_crop_id") == crop_id:
            out.append(vid)
    return out


def validate_variety_card(card: dict) -> dict:
    """يتحقّق أن بطاقة الصنف تتبع UPOV/Bioversity وتربط بمحصول موجود."""
    errors = []
    missing = REQUIRED_VARIETY - set(card.keys())
    if missing:
        errors.append(f"حقول مفقودة: {missing}")
    # يجب أن يربط بمحصول أمّ موجود فعلاً
    parent = card.get("parent_crop_id")
    if parent and load_crop_card(parent) is None:
        errors.append(f"المحصول الأمّ '{parent}' غير موجود في البطاقات")
    # passport يجب أن يحوي المصدر والمنشأ (UPOV/Bioversity)
    if "passport" in card:
        if "origin_type" not in card["passport"]:
            errors.append("passport بلا origin_type (landrace/improved/introduced)")
        if "source_ar" not in card["passport"]:
            errors.append("passport بلا مصدر موثّق")
    # حياد الموقع
    forbidden = FORBIDDEN & set(card.keys())
    if forbidden:
        errors.append(f"حقول تكسر حياد الموقع: {forbidden}")
    return {"valid": len(errors) == 0, "errors": errors,
            "variety_id": card.get("variety_id", "?")}
