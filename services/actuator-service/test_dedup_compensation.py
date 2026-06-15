#!/usr/bin/env python3
"""اختبارات نقيّة لخطّاف Saga في خدمة المُشغّلات (actuator-service).

نختبر دالّتي القرار النقيّتين فقط (إزالة التكرار + الأمر العكسيّ) بزمن مُموَّه،
دون لمس MQTT/DB. هذا متعمَّد: مسار MQTT/DB غير قابل للاختبار وحدويّاً بسهولة،
لذا فُصِل القرار في دالّة نقيّة (_dedup_should_fire) ونُختبرها هي.

ملاحظة صدق: استيراد main.py يستلزم aiomqtt (قد يكون غير مثبّت في بيئة الاختبار)،
فنُموّه الوحدة قبل الاستيراد كي يبقى الاختبار مستقلّاً عن الوسيط.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

# موّه aiomqtt إن لم يكن مثبّتاً (لا نحتاج وسيطاً حقيقيّاً لاختبار الدوالّ النقيّة).
if "aiomqtt" not in sys.modules:
    try:
        import aiomqtt  # noqa: F401
    except ImportError:
        _stub = types.ModuleType("aiomqtt")
        _stub.Client = object  # كافٍ للاستيراد فقط
        sys.modules["aiomqtt"] = _stub

# اضبط النافذة قبل الاستيراد كي تُقرأ القيمة الافتراضيّة المتوقَّعة في الوحدة.
os.environ.setdefault("ACTUATOR_DEDUP_WINDOW_SEC", "60")

_MAIN_PATH = Path(__file__).resolve().parent / "main.py"
_spec = importlib.util.spec_from_file_location("actuator_main_under_test", _MAIN_PATH)
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)


def test_dedup_first_fire_allowed():
    """أوّل إطلاق لمفتاح غير معروف ⇒ مسموح، ويُسجَّل في المخزن."""
    store: dict = {}
    key = ("t1", "f1", "valve-1", "open")
    assert main._dedup_should_fire(key, now=100.0, window_sec=60.0, store=store) is True
    assert key in store


def test_dedup_duplicate_within_window_blocked():
    """تكرار نفس المفتاح ضمن النافذة ⇒ يُحجب."""
    store: dict = {}
    key = ("t1", "f1", "valve-1", "open")
    assert main._dedup_should_fire(key, now=100.0, window_sec=60.0, store=store) is True
    # بعد 10ث (< 60) ⇒ مكرّر
    assert main._dedup_should_fire(key, now=110.0, window_sec=60.0, store=store) is False
    # بعد 30ث إضافيّة (المجموع 40 < 60) ⇒ ما زال مكرّراً
    assert main._dedup_should_fire(key, now=140.0, window_sec=60.0, store=store) is False


def test_dedup_after_window_allowed():
    """مرور النافذة كاملة ⇒ يُسمح بإعادة الإطلاق."""
    store: dict = {}
    key = ("t1", "f1", "valve-1", "open")
    assert main._dedup_should_fire(key, now=100.0, window_sec=60.0, store=store) is True
    # عند 160 بالضبط (الفرق = 60 ⇒ >= النافذة) ⇒ مسموح
    assert main._dedup_should_fire(key, now=160.0, window_sec=60.0, store=store) is True


def test_dedup_distinct_keys_independent():
    """أوامر متمايزة (جهاز/أمر مختلف) لا يحجب بعضها بعضاً."""
    store: dict = {}
    k_open = ("t1", "f1", "valve-1", "open")
    k_close = ("t1", "f1", "valve-1", "close")
    k_other_dev = ("t1", "f1", "valve-2", "open")
    assert main._dedup_should_fire(k_open, now=100.0, window_sec=60.0, store=store) is True
    assert main._dedup_should_fire(k_close, now=100.0, window_sec=60.0, store=store) is True
    assert main._dedup_should_fire(k_other_dev, now=100.0, window_sec=60.0, store=store) is True


def test_dedup_window_zero_disables_guard():
    """نافذة صفر ⇒ الحارس معطّل (كلّ إطلاق مسموح)."""
    store: dict = {}
    key = ("t1", "f1", "valve-1", "open")
    assert main._dedup_should_fire(key, now=1.0, window_sec=0.0, store=store) is True
    assert main._dedup_should_fire(key, now=1.0, window_sec=0.0, store=store) is True


def test_dedup_prunes_stale_entries():
    """تُنظَّف المدخلات الأقدم من النافذة كي لا ينمو المخزن بلا حدّ."""
    store: dict = {}
    old_key = ("t1", "f1", "old-dev", "open")
    new_key = ("t1", "f1", "new-dev", "open")
    main._dedup_should_fire(old_key, now=100.0, window_sec=60.0, store=store)
    # إطلاق مفتاح آخر بعد مرور النافذة على القديم ⇒ يُحذف القديم
    main._dedup_should_fire(new_key, now=200.0, window_sec=60.0, store=store)
    assert old_key not in store
    assert new_key in store


def test_inverse_command_known_pairs():
    """الأوامر ذات العكس الواضح تُعيد عكسها (غير حسّاسة لحالة الأحرف/الفراغ)."""
    assert main._inverse_command("open") == "close"
    assert main._inverse_command("CLOSE") == "open"
    assert main._inverse_command(" on ") == "off"
    assert main._inverse_command("off") == "on"
    assert main._inverse_command("start") == "stop"
    assert main._inverse_command("stop") == "start"


def test_inverse_command_unknown_returns_none():
    """أمر بلا عكس واضح ⇒ None (⇐ يتطلّب تعويضاً يدويّاً، لا تخمين)."""
    assert main._inverse_command("pulse") is None
    assert main._inverse_command("") is None
    assert main._inverse_command("set_speed") is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
