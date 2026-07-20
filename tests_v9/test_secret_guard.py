"""وحدة: الحارس المركزيّ للأسرار الافتراضيّة/الضعيفة (shared.security.secret_guard).

تدقيق عميق رصد افتراضات سرّ حرفيّة (مثل ``webhook_secret="dev-secret"``). هذا الحارس
يعمّم نمط رفض ZLMediaKit القائم، ويمنع عودة الأسرار الافتراضيّة الحرفيّة في شيفرة الإنتاج.

وحدة صرفة — ``pytest -m unit``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shared.security.secret_guard import is_weak_secret, weak_secret_error

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]


def test_empty_secret_rejected_in_production():
    assert weak_secret_error("X", "", production=True) is not None
    assert weak_secret_error("X", None, production=True) is not None


def test_known_weak_values_rejected_in_production():
    for v in ("dev-secret", "changeme", "sahool-zlm-dev-secret", "DEV-SECRET"):
        assert weak_secret_error("X", v, production=True) is not None


def test_short_secret_rejected_in_production():
    assert weak_secret_error("X", "abc123", production=True, min_len=16) is not None


def test_strong_secret_accepted_in_production():
    assert weak_secret_error("X", "S7r0ng-Rand0m-Secret-9f2a1b", production=True) is None


def test_non_production_skips_check():
    assert weak_secret_error("X", "dev-secret", production=False) is None
    assert weak_secret_error("X", "", production=False) is None


def test_is_weak_secret_detector():
    assert is_weak_secret("") is True
    assert is_weak_secret("dev-secret") is True
    assert is_weak_secret("a-real-strong-secret-value") is False


def test_no_production_module_ships_weak_default_secret_literal():
    """حارس ساكن: لا افتراض حرفيّ لسرّ ضعيف في shared/ و services/ (عدا الاختبارات وتعريف الحارس)."""
    # نمط: اسم يحوي secret/password/token يُسنَد افتراضاً لقيمة ضعيفة حرفيّة.
    weak_literal = re.compile(
        r'(secret|password|passwd|token)\w*\s*(:\s*str)?\s*=\s*["\'](dev-secret|changeme|change-me|password|secret)["\']',
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for base in ("shared", "services"):
        for py in (_ROOT / base).rglob("*.py"):
            parts = py.parts
            if "__pycache__" in parts or "tests" in parts or py.name.startswith("test_"):
                continue
            # تعريف الحارس نفسه يُعدّد القيم الضعيفة كبيانات (لا كأسرار افتراضيّة).
            if py.name == "secret_guard.py":
                continue
            if weak_literal.search(py.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(py.relative_to(_ROOT)))
    assert not offenders, f"weak default-secret literals in production code: {offenders}"
