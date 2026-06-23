"""اختبار إغلاق H2: علم نشر NATS (default off) — البوّابة النقيّة.

يقفل `nats_publishers_enabled` (يحرس تشغيل OutboxWorker → NATS): OFF افتراضيّاً ⇒ الأحداث
تبقى في outbox (record_decision_only)، لا يُشغَّل الناشر؛ ON (env truthy) ⇒ يُشغَّل. لا قاعدة/شبكة.
التسجيل الذرّيّ للأحداث (events+outbox) مستقلّ عن العلم — لا يُفقَد شيء عند OFF (صدق).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.event_bus import NATS_PUBLISHERS_FLAG, nats_publishers_enabled
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_flag_name_is_stable():
    assert NATS_PUBLISHERS_FLAG == "FEATURE_NATS_PUBLISHERS"


def test_disabled_by_default(monkeypatch):
    """لا env ⇒ معطّل (record_decision_only، لا ناشر) — السلوك الآمن الافتراضيّ."""
    monkeypatch.delenv(NATS_PUBLISHERS_FLAG, raising=False)
    assert nats_publishers_enabled() is False


def test_enabled_on_truthy(monkeypatch):
    """قيم truthy ⇒ مُفعَّل (publish_event)."""
    for val in ("1", "true", "TRUE", "yes", "on", " On "):
        monkeypatch.setenv(NATS_PUBLISHERS_FLAG, val)
        assert nats_publishers_enabled() is True, val


def test_disabled_on_falsy(monkeypatch):
    """قيم falsy/فارغة ⇒ معطّل (لا تشغيل عرضيّ للناشر)."""
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(NATS_PUBLISHERS_FLAG, val)
        assert nats_publishers_enabled() is False, val
