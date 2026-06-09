"""
core/data_inventory.py — قارئ سجلّ المصادر بالموضوع
=====================================================

يقرأ data_inventory.yaml ويوفّر API برمجي للوصول للمصادر.

الفائدة العمليّة:
  • تطوير: عند بناء feature جديد، اعرف ما المصادر المتاحة لـtheme
  • تشخيص: عند فشل recommendation، شف أي theme/source كان مفقوداً
  • توثيق: مرجع حيّ بدل البحث في docs

المرجع:
  منهجيّة "Theme-based Data Organization" من وثيقة البيانات الأمريكيّة:
  "إعادة رسم الخريطة حسب الموضوع، وليس حسب المؤسسة"
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataSource:
    """مصدر بيانات مُسجَّل."""

    source_id: str
    theme_id: str
    theme_name_ar: str
    source_type: str  # 'satellite' | 'drone' | 'lab' | 'model' | ...
    connector: str | None
    license: str | None
    online: str  # 'required' | 'optional' | 'never'
    ground_truth: str | None
    criticality: str  # 'A' | 'B' | 'C'
    status: str  # 'active' | 'planned' | 'rejected'
    notes: str | None
    trigger: str | None  # لـplanned status


@dataclass(frozen=True)
class Theme:
    """موضوع بيانات."""

    theme_id: str
    name_ar: str
    name_en: str
    sources: list[DataSource]


# ─── Loader ───────────────────────────────────────────────────────


# نُحمّل YAML بدون pyyaml dependency (parser بسيط للحقول التي نهتمّ بها)
# لكن لو متاح، نستخدمه
def _load_yaml(path: str) -> dict:
    """يقرأ YAML. يستخدم PyYAML لو متوفّر، وإلّا fallback ساذج."""
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        # Fallback ساذج — يكفي للبنية الحاليّة (شعلنا الـYAML بـschema بسيط)
        return _naive_yaml_parse(path)


def _naive_yaml_parse(path: str) -> dict:
    """parser ساذج للحالة الراهنة (لا nested complex)."""
    # في هذه الحالة، نتطلّب PyYAML — لا نُحاكي parser كامل
    raise RuntimeError("PyYAML غير مثبَّت. ثبّته: pip install pyyaml")


_INVENTORY_CACHE: dict[str, Theme] | None = None


def load_inventory(
    yaml_path: str | None = None,
    use_cache: bool = True,
) -> dict[str, Theme]:
    """يُرجع dict {theme_id: Theme}.

    Args:
        yaml_path: مسار data_inventory.yaml. default: مجاور لهذا الملفّ
        use_cache: استخدم cache في الذاكرة
    """
    global _INVENTORY_CACHE
    if use_cache and _INVENTORY_CACHE is not None:
        return _INVENTORY_CACHE

    if yaml_path is None:
        yaml_path = str(Path(__file__).parent / "data_inventory.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(f"لم يُعثَر على {yaml_path}")

    raw = _load_yaml(yaml_path)
    themes_raw = raw.get("themes", {})

    themes: dict[str, Theme] = {}
    for theme_id, theme_data in themes_raw.items():
        sources = []
        for src_data in theme_data.get("sources", []):
            sources.append(
                DataSource(
                    source_id=src_data["id"],
                    theme_id=theme_id,
                    theme_name_ar=theme_data.get("name_ar", theme_id),
                    source_type=src_data.get("type", "unknown"),
                    connector=src_data.get("connector"),
                    license=src_data.get("license"),
                    online=src_data.get("online", "never"),
                    ground_truth=src_data.get("ground_truth"),
                    criticality=src_data.get("criticality", "C"),
                    status=src_data.get("status", "planned"),
                    notes=src_data.get("notes"),
                    trigger=src_data.get("trigger"),
                )
            )
        themes[theme_id] = Theme(
            theme_id=theme_id,
            name_ar=theme_data.get("name_ar", theme_id),
            name_en=theme_data.get("name_en", theme_id),
            sources=sources,
        )

    if use_cache:
        _INVENTORY_CACHE = themes
    return themes


# ─── Query helpers ────────────────────────────────────────────────


def sources_for_theme(theme_id: str) -> list[DataSource]:
    """يُرجع كل المصادر لـtheme."""
    themes = load_inventory()
    if theme_id not in themes:
        raise KeyError(f"theme غير مُسجَّل: {theme_id}")
    return themes[theme_id].sources


def active_sources_for_theme(theme_id: str) -> list[DataSource]:
    """يُرجع المصادر النشطة فقط (status='active')."""
    return [s for s in sources_for_theme(theme_id) if s.status == "active"]


def sources_by_criticality(criticality: str) -> list[DataSource]:
    """يُرجع المصادر بتصنيف criticality معيّن (A/B/C)."""
    if criticality not in ("A", "B", "C"):
        raise ValueError(f"criticality يجب A/B/C، وُجِد {criticality}")
    themes = load_inventory()
    return [s for theme in themes.values() for s in theme.sources if s.criticality == criticality]


def planned_sources_with_triggers() -> list[DataSource]:
    """المصادر المُؤجَّلة + triggers — مفيد لخارطة الطريق."""
    themes = load_inventory()
    return [
        s for theme in themes.values() for s in theme.sources if s.status == "planned" and s.trigger
    ]


def find_source(source_id: str) -> DataSource | None:
    """يبحث عن مصدر بـID."""
    themes = load_inventory()
    for theme in themes.values():
        for s in theme.sources:
            if s.source_id == source_id:
                return s
    return None


def gaps_report() -> dict[str, list[str]]:
    """تقرير فجوات: مواضيع ليس فيها مصادر نشطة بـcriticality A.

    مفيد لاكتشاف ثغرات حرجة.
    """
    themes = load_inventory()
    gaps: dict[str, list[str]] = {}
    for theme_id, theme in themes.items():
        critical_active = [
            s for s in theme.sources if s.criticality == "A" and s.status == "active"
        ]
        critical_planned = [
            s for s in theme.sources if s.criticality == "A" and s.status == "planned"
        ]
        if not critical_active and critical_planned:
            gaps[theme_id] = [s.source_id for s in critical_planned]
    return gaps


def _reset_cache():
    """للاختبارات فقط."""
    global _INVENTORY_CACHE
    _INVENTORY_CACHE = None
