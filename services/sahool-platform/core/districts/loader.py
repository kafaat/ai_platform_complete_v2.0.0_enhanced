"""
sahool_core.districts.loader
=============================
مُحمّل طبقة المعرفة الإقليميّة (districts) + متحقّق من القالب.

خلافاً لبطاقات المحاصيل (محايدة الموقع)، طبقة districts إقليميّة بالتصميم:
تحمل **نوافذ خطر الآفات** (pest risk windows) لكلّ منطقة زراعيّة-بيئيّة.
هذا ما تشير إليه بطاقات المحاصيل: «نوافذ الخطر الإقليمية تعيش في
districts/<region>/pests.yaml».

كلّ نافذة خطر مُسنَدة بمصدر معرفيّ (FAO/ICARDA IPM أو قرينة زراعيّة معروفة)؛
هذه قرائن معرفيّة (knowledge priors) تُصقَل لاحقاً ببيانات المسح/الإرشاد المحلّيّة،
ولا تُختلَق فيها تقاويم محلّية دقيقة زوراً.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

DISTRICTS_DIR = Path(__file__).parent


def _safe_id(district_id: str) -> str | None:
    """يعقّم معرّف المنطقة لمنع path traversal.
    يسمح فقط بحروف/أرقام/شرطة سفلية — يرفض المسارات الصاعدة والفواصل."""
    if not district_id or not re.fullmatch(r"[A-Za-z0-9_]+", district_id):
        return None
    return district_id


# الحقول الإلزامية في كلّ منطقة
REQUIRED_TOP = {
    "district_id",
    "name_ar",
    "agro_ecological_zone_ar",
    "altitude_range_m",
    "pest_windows",
}
# الحقول الإلزامية في كلّ نافذة خطر
REQUIRED_WINDOW = {
    "pest",
    "pest_ar",
    "crops",
    "risk_months",
    "severity",
    "scouting_cue_ar",
    "source",
}
VALID_SEVERITY = {"low", "medium", "high"}


def load_district(district_id: str) -> dict | None:
    """يحمّل منطقة بمعرّفها (مع حماية من path traversal)."""
    safe = _safe_id(district_id)
    if safe is None:
        return None
    path = DISTRICTS_DIR / f"{safe}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_districts() -> list[str]:
    """يُرجع معرّفات كلّ المناطق المتاحة (عدا الملفّات الخاصّة _*)."""
    return sorted(p.stem for p in DISTRICTS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def _validate_window(win: dict, idx: int, errors: list) -> None:
    """يتحقّق من نافذة خطر واحدة."""
    if not isinstance(win, dict):
        errors.append(f"نافذة[{idx}] ليست قاموساً")
        return
    miss = REQUIRED_WINDOW - set(win.keys())
    if miss:
        errors.append(f"نافذة[{idx}] ينقصها: {miss}")
        return
    if not isinstance(win["crops"], list) or not win["crops"]:
        errors.append(f"نافذة[{idx}] crops يجب أن تكون قائمة غير فارغة")
    months = win["risk_months"]
    if not isinstance(months, list) or not months:
        errors.append(f"نافذة[{idx}] risk_months يجب أن تكون قائمة غير فارغة")
    else:
        for m in months:
            if not isinstance(m, int) or not (1 <= m <= 12):
                errors.append(f"نافذة[{idx}] risk_month خارج النطاق 1..12: {m}")
    if win["severity"] not in VALID_SEVERITY:
        errors.append(f"نافذة[{idx}] severity غير صالحة: {win['severity']}")


def validate_district(card: dict | None) -> dict:
    """يتحقّق أن المنطقة تتبع القالب المعياري (نوافذ خطر مُسنَدة بمصادر)."""
    errors: list[str] = []
    if not isinstance(card, dict):
        return {"valid": False, "errors": ["البطاقة ليست قاموساً"], "district_id": "?"}
    missing = REQUIRED_TOP - set(card.keys())
    if missing:
        errors.append(f"حقول مفقودة: {missing}")
    windows = card.get("pest_windows")
    if not isinstance(windows, list):
        errors.append("pest_windows يجب أن تكون قائمة")
    else:
        for i, win in enumerate(windows):
            _validate_window(win, i, errors)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "district_id": card.get("district_id", "?"),
    }


def active_pests(district_id: str, month: int) -> list[dict]:
    """يُرجع نوافذ الخطر التي يقع فيها الشهر `month` (1..12) لمنطقة معيّنة.

    صدق بلا اختلاق: قائمة فارغة إن جُهِلت المنطقة أو الشهر خارج النطاق أو لا
    تنطبق نافذة على الشهر المطلوب.
    """
    if not isinstance(month, int) or not (1 <= month <= 12):
        return []
    card = load_district(district_id)
    if card is None:
        return []
    windows = card.get("pest_windows")
    if not isinstance(windows, list):
        return []
    out: list[dict] = []
    for win in windows:
        if isinstance(win, dict) and month in (win.get("risk_months") or []):
            out.append(win)
    return out
