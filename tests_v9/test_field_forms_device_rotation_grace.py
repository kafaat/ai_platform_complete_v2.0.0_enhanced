"""§9.2.1 — نافذة سماح تدوير device-key (اختبار وحدة للمساعِدة _device_rotation_grace_ok).

يتحقّق من العقد الأربعة:
  1. الافتراضيّ (غير مضبوط ⇒ 0) ⇒ النافذة مغلقة تمامًا: حتّى توكن حديث جدًّا يبقى مرفوضًا
     (سلوك fail-closed القائم لا يتغيّر ما لم تُضبَط النافذة عمدًا).
  2. نافذة موجبة ⇒ توكن أُصدر ضمنها مقبول.
  3. نافذة موجبة ⇒ توكن أُصدر خارجها (أقدم من النافذة) مرفوض.
  4. issued_at مفقود/غير رقميّ ⇒ مرفوض حتّى مع نافذة موجبة (fail-closed).

دالّة صرفة تقرأ FIELD_FORMS_DEVICE_ROTATION_GRACE_SECONDS من البيئة — لا HTTP ولا DB.
تتخطّى إن غاب fastapi (استيراد field_forms_api يجرّه) — كنمط اختبارات field-forms القائمة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="importing field_forms_api pulls fastapi at module load")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "scout-ingest-service"))

import field_forms_api as api  # noqa: E402

ENV = "FIELD_FORMS_DEVICE_ROTATION_GRACE_SECONDS"
NOW = 1_000_000.0


def test_default_closed_rejects_even_fresh_token(monkeypatch):
    """الافتراضيّ (غير مضبوط ⇒ 0) ⇒ النافذة مغلقة: توكن حديث جدًّا يبقى مرفوضًا."""
    monkeypatch.delenv(ENV, raising=False)
    assert api._device_rotation_grace_ok({"issued_at": NOW}, NOW) is False
    # قيمة 0 صريحة = مغلقة أيضًا.
    monkeypatch.setenv(ENV, "0")
    assert api._device_rotation_grace_ok({"issued_at": NOW}, NOW) is False


def test_positive_grace_accepts_token_within_window(monkeypatch):
    """نافذة موجبة (3600) ⇒ توكن أُصدر قبل 100ث (< النافذة) مقبول."""
    monkeypatch.setenv(ENV, "3600")
    assert api._device_rotation_grace_ok({"issued_at": NOW - 100}, NOW) is True


def test_positive_grace_rejects_token_outside_window(monkeypatch):
    """نافذة موجبة (3600) ⇒ توكن أُصدر قبل 7200ث (> النافذة) مرفوض."""
    monkeypatch.setenv(ENV, "3600")
    assert api._device_rotation_grace_ok({"issued_at": NOW - 7200}, NOW) is False


def test_missing_or_invalid_issued_at_rejected(monkeypatch):
    """issued_at مفقود أو غير رقميّ ⇒ مرفوض حتّى مع نافذة موجبة (fail-closed).

    كذلك قيمة نافذة غير صالحة (ValueError) ⇒ 0 ⇒ مرفوضة.
    """
    monkeypatch.setenv(ENV, "3600")
    assert api._device_rotation_grace_ok({}, NOW) is False
    assert api._device_rotation_grace_ok({"issued_at": "not-a-number"}, NOW) is False
    monkeypatch.setenv(ENV, "not-an-int")
    assert api._device_rotation_grace_ok({"issued_at": NOW}, NOW) is False
