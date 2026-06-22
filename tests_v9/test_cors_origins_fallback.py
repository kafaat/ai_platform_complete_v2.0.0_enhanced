"""مرونة CORS: أسبقيّة قراءة المنشأ (origins) في api/main.py.

بقيّة الخدمات تقرأ ``CORS_ORIGINS`` بينما المنصّة كانت تقرأ ``SAHOOL_CORS_ORIGINS`` فقط.
عُدّل ``main.py`` ليقرأ ``SAHOOL_CORS_ORIGINS or CORS_ORIGINS or ""`` (الأسبقيّة لـSAHOOL_،
ثمّ CORS_ORIGINS، ثمّ فارغ ⇒ يبقى منطق dev-مفتوح/prod-مغلق). نتحقّق من الأسبقيّة سلوكيّاً
دون استيراد ``main.py`` (يحمل تبعيّات ثقيلة/DB)، ونؤكّد بقاء سلسلة الاحتياط في المصدر.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MAIN_PY = _REPO_ROOT / "services" / "sahool-platform" / "api" / "main.py"


def _resolve_cors_raw() -> str:
    """يعيد نفس تعبير الأسبقيّة المستعمَل في main.py (مصدر واحد للحقيقة في الاختبار)."""
    return os.getenv("SAHOOL_CORS_ORIGINS") or os.getenv("CORS_ORIGINS") or ""


@pytest.mark.unit
def test_sahool_var_wins_over_cors_origins(monkeypatch):
    monkeypatch.setenv("SAHOOL_CORS_ORIGINS", "https://a.sahool.ye")
    monkeypatch.setenv("CORS_ORIGINS", "https://b.example.com")
    assert _resolve_cors_raw() == "https://a.sahool.ye"


@pytest.mark.unit
def test_falls_back_to_cors_origins_when_sahool_absent(monkeypatch):
    monkeypatch.delenv("SAHOOL_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "https://b.example.com")
    assert _resolve_cors_raw() == "https://b.example.com"


@pytest.mark.unit
def test_empty_sahool_falls_back_to_cors_origins(monkeypatch):
    """قيمة فارغة لـSAHOOL_ (falsy) ⇒ ينزلق إلى CORS_ORIGINS (سلوك ``or``)."""
    monkeypatch.setenv("SAHOOL_CORS_ORIGINS", "")
    monkeypatch.setenv("CORS_ORIGINS", "https://b.example.com")
    assert _resolve_cors_raw() == "https://b.example.com"


@pytest.mark.unit
def test_default_empty_when_neither_set(monkeypatch):
    monkeypatch.delenv("SAHOOL_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _resolve_cors_raw() == ""


@pytest.mark.unit
def test_main_py_uses_fallback_chain():
    """المصدر يقرأ SAHOOL_CORS_ORIGINS ثمّ يحتاط بـCORS_ORIGINS (منع انحدار صامت)."""
    src = _MAIN_PY.read_text(encoding="utf-8")
    assert 'os.getenv("SAHOOL_CORS_ORIGINS") or os.getenv("CORS_ORIGINS")' in src, (
        "اختفت سلسلة احتياط CORS في main.py — أعِد "
        'os.getenv("SAHOOL_CORS_ORIGINS") or os.getenv("CORS_ORIGINS") or ""'
    )
