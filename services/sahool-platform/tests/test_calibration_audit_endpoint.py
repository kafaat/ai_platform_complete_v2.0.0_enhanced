"""اختبار توصيل نقطة سجلّ تدقيق المعايرة (v84) + تشكيل الصفّ النقيّ.

مسار القراءة تكامليّ (يتطلّب Postgres) — هنا نؤكّد التوصيل، تسجيل الحدث، وتشكيل الصفّ
النقيّ (يفكّ JSONB) بلا قاعدة.
"""

import datetime as _dt

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.event_bus import EventType
from api.event_catalog import get_event, is_registered
from api.routers.calibration import _audit_row

pytestmark = pytest.mark.unit


def test_audit_event_registered():
    """نوع الحدث CALIBRATION_AUDIT_RECORDED مُسجَّل في EventType + event_catalog (فئة calibration)."""
    assert EventType.CALIBRATION_AUDIT_RECORDED.value == "calibration.audit.recorded"
    assert is_registered("CALIBRATION_AUDIT_RECORDED")
    ev = get_event("CALIBRATION_AUDIT_RECORDED")
    assert ev is not None and ev["category"] == "calibration"


def test_audit_endpoint_wired():
    """نقطة GET /api/v1/calibration/{region}/audit مُضمَّنة (قراءة فقط)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/calibration/{region}/audit", "GET") in routes


def test_audit_row_shaping_decodes_jsonb():
    """تشكيل صفّ نقيّ: يفكّ JSONB إن جاء نصّاً، ويطبّع created_at إلى ISO."""
    created = _dt.datetime(2026, 6, 20, 12, 0, 0, tzinfo=_dt.UTC)
    row = {
        "audit_id": "11111111-1111-1111-1111-111111111111",
        "region": "tihama",
        "action": "override_set",
        "old_values": None,
        "new_values": '{"raw_fraction": 0.5}',  # JSONB كنصّ (كما قد يُرجِعه السائق)
        "source_ar": "قياس ميدانيّ",
        "actor": "user-7",
        "created_at": created,
    }
    out = _audit_row(row)
    assert out["region"] == "tihama"
    assert out["action"] == "override_set"
    assert out["old_values"] is None  # None تبقى None (لا تلفيق)
    assert out["new_values"] == {"raw_fraction": 0.5}  # فُكّ النصّ JSONB إلى dict
    assert out["source_ar"] == "قياس ميدانيّ"
    assert out["actor"] == "user-7"
    assert out["created_at"] == created.isoformat()


def test_audit_row_shaping_passthrough_dict():
    """JSONB المُفكَّك مسبقاً (dict) يمرّ كما هو."""
    out = _audit_row(
        {
            "audit_id": "22222222-2222-2222-2222-222222222222",
            "region": "jawf",
            "action": "reverted",
            "old_values": {"root_depth_m": 0.8},
            "new_values": None,
            "source_ar": None,
            "actor": "user-9",
            "created_at": None,
        }
    )
    assert out["old_values"] == {"root_depth_m": 0.8}
    assert out["new_values"] is None
    assert out["created_at"] is None  # None لا يُطبَّع ISO
