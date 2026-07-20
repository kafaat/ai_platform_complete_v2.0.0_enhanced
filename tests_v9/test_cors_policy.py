"""وحدة: مُعقِّم CORS المركزيّ (shared.security.cors_policy) + حارس ساكن ضدّ الانحدار.

تدقيق عميق كشف: خدمات تقرأ CORS_ORIGINS بـ``.split(",")`` خام (يُبقي الفراغات والقيم
الفارغة) وبلا رفض wildcard مع credentials. هذا الملفّ يثبّت السلوك المُعقَّم ويمنع عودة
النمط الخام على أيّ خدمة (حارس لا عائق — يوجّه إلى المُعقِّم الواحد).

وحدة صرفة — ``pytest -m unit``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.security.cors_policy import parse_cors_origins, wildcard_with_credentials

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]


def test_strips_whitespace_and_drops_empty_tokens():
    assert parse_cors_origins("https://a.io, ,https://b.io ", production=True) == [
        "https://a.io",
        "https://b.io",
    ]


def test_wildcard_with_credentials_is_dropped_never_returned():
    # wildcard مع credentials مرفوض: يُسقَط، ولا يبقى في القائمة.
    out = parse_cors_origins("*,https://ok.io", allow_credentials=True, production=True)
    assert out == ["https://ok.io"]
    assert "*" not in out


def test_wildcard_only_with_credentials_falls_closed_in_production():
    assert parse_cors_origins("*", allow_credentials=True, production=True) == []


def test_no_config_production_is_fail_closed():
    assert parse_cors_origins("", production=True) == []
    assert parse_cors_origins(None, production=True) == []


def test_no_config_development_gets_localhost_defaults():
    out = parse_cors_origins("", production=False)
    assert out and all(o.startswith("http://") for o in out)
    assert "http://localhost:3000" in out


def test_wildcard_without_credentials_is_allowed():
    # بلا credentials، wildcard مسموح (لا يُسقَط).
    out = parse_cors_origins("*", allow_credentials=False, production=True)
    assert out == ["*"]


def test_wildcard_with_credentials_detector():
    assert wildcard_with_credentials("*", allow_credentials=True) is True
    assert wildcard_with_credentials("*", allow_credentials=False) is False
    assert wildcard_with_credentials("https://a.io", allow_credentials=True) is False


def test_no_service_uses_raw_cors_split_pattern():
    """حارس ساكن: لا خدمة تقرأ CORS_ORIGINS بـ.split(",") خام — يجب المرور بالمُعقِّم."""
    raw = re.compile(r'os\.getenv\(\s*["\']CORS_ORIGINS["\'][^)]*\)\s*\.split\(')
    offenders: list[str] = []
    for base in ("services", "shared"):
        for py in (_ROOT / base).rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            if raw.search(py.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(py.relative_to(_ROOT)))
    assert not offenders, (
        f"raw CORS_ORIGINS.split() must route through parse_cors_origins: {offenders}"
    )
