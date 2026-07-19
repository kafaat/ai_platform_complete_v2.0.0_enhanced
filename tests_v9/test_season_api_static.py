"""حارس ساكن + سلوك مخزن الكائنات لواجهة إدخال المواسم (SEASON-RECORD-ENTRY-01 شريحة 2).

وحدة صرفة — ``pytest -m unit`` (لا شبكة/قاعدة). يغطّي من براهين المواصفة العشرة ما يُثبَت بلا PG:
  • بنيويّ: النقاط الستّ على scout-ingest، صفر مسار منصّة، وأسلاك الأمان موجودة في كلّ نقطة.
  • ③ سلامة المرفق: sniff magic bytes + سقف الحجم (مُثبَت أيضاً في test_season_logbook_content_safety).
  • ⑦ سقف presign ≤300ث مفروض داخل blob_store (دفاع عميق، لا عند المستدعي فقط).
  • ⑧/⑪ برهان الكائن عند القبول: مرجع ميت ⇒ object_exists False؛ وfile:// في وضع الإنتاج (S3 مهيّأة) ⇒
    False (نظام ملفّات الحاوية زائل — دليل وهميّ يُرفَض). البراهين الحيّة (RLS، 409، idempotency) في
    services/scout-ingest-service/tests/test_season_live.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SVC = _ROOT / "services" / "scout-ingest-service"
_SEASON_API = _SVC / "season_api.py"


def _load_season_api():
    if str(_SVC) not in sys.path:
        sys.path.insert(0, str(_SVC))
    import season_api  # noqa: PLC0415

    return season_api


# ── بنيويّ: النقاط + صفر مسار منصّة + أسلاك الأمان ───────────────────────────────
def test_six_endpoints_all_on_scout_ingest_internal():
    m = _load_season_api()
    paths = {(tuple(sorted(r.methods)), r.path) for r in m.router.routes}
    assert (("POST",), "/internal/seasons") in paths  # إنشاء مسودّة
    assert (("PATCH",), "/internal/seasons/{season_id}") in paths
    assert (("POST",), "/internal/seasons/{season_id}/logbook") in paths
    assert (("GET",), "/internal/seasons/{season_id}/logbook") in paths
    assert (("POST",), "/internal/seasons/{season_id}/accept") in paths
    assert (("GET",), "/internal/seasons") in paths
    assert len(m.router.routes) == 6
    # صفر مسار منصّة: كلّ المسارات داخليّة على هذه الخدمة المالكة
    for r in m.router.routes:
        assert r.path.startswith("/internal/seasons")


def test_security_wiring_present_in_source():
    """كلّ نقطة تمرّ ببوّابات الأمان؛ والقبول يزيد التصديق من الحافّة + الدور + برهان الكائن."""
    src = _SEASON_API.read_text(encoding="utf-8")
    # توكن الخدمة + المستأجِر من الحافّة على كلّ النقاط
    assert src.count("_require_service_token(") >= 6
    assert src.count("_require_tenant(") >= 6
    assert "_require_enabled()" in src  # خلف الراية
    # القبول: تصديق حافّة HMAC + دور مُراجِع + برهان وجود الكائن
    assert "verify_edge_attestation(" in src
    assert "has_reviewer_role(" in src
    assert "blob_store.object_exists(" in src
    assert "ERROR_LOGBOOK_MISSING" in src
    # المرفق: فحص محتوى + حدّ حجم مُتدفّق
    assert "detect_content_type(" in src
    assert "MAX_LOGBOOK_BYTES" in src
    assert "request.stream()" in src  # تدفّق لملفّ مؤقّت لا الذاكرة
    assert "tempfile" in src
    # PATCH/accept على موسم مقبول ⇒ 409 من النقطة نفسها
    assert "409" in src


def test_patch_rejects_after_accept_status_check():
    """④: منطق PATCH يرفض ما لم يكن الموسم untrusted (409) — الحارس من مدخله الحقيقيّ."""
    src = _SEASON_API.read_text(encoding="utf-8")
    assert 'status != "untrusted"' in src
    assert "season_not_editable_after_accept" in src


# ── ⑦ سقف presign TTL داخل blob_store ────────────────────────────────────────────
def test_presign_ttl_cap_enforced_inside_module():
    from shared.storage import blob_store

    for bad in (0, -1, 301, 3600):
        with pytest.raises(blob_store.BlobStoreError):
            blob_store.presigned_get_url("file:///x", bad)
    # 300 مسموح (الحدّ نفسه)؛ file:// يعود كما هو (تطوير)
    assert blob_store.presigned_get_url("file:///x", 300) == "file:///x"


# ── ⑧/⑪ برهان الكائن عند القبول ─────────────────────────────────────────────────
def test_object_exists_dead_ref_and_file_in_production(monkeypatch):
    from shared.storage import blob_store

    # مرجع فارغ/مجهول ⇒ False
    assert blob_store.object_exists("") is False
    assert blob_store.object_exists("weird://x") is False
    # dev (S3 معطَّلة): file:// موجود = True، غير موجود = False
    monkeypatch.setattr(blob_store, "S3_BUCKET", "")
    assert blob_store.object_exists("file:///definitely/missing/xyz") is False
    # ⑪ إنتاج (S3 مهيّأة): file:// ⇒ False دائماً (نظام ملفّات الحاوية زائل)
    monkeypatch.setattr(blob_store, "S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "http://minio:9000")
    assert blob_store.s3_enabled() is True
    assert blob_store.object_exists("file:///tmp/anything") is False


# ── مخزن الكائنات: fail-closed + تدهور مُعلَن + ① تهيئة مكسورة ────────────────────
def test_upload_dev_fallback_and_roundtrip(tmp_path, monkeypatch):
    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "S3_BUCKET", "")  # dev
    monkeypatch.setattr(blob_store, "LOCAL_DIR", str(tmp_path))
    ref = blob_store.upload_bytes("season-logbooks/t/s/abc.jpg", b"\xff\xd8\xff data", "image/jpeg")
    assert ref.startswith("file://")
    assert blob_store.object_exists(ref) is True  # dev file exists


def test_missing_keys_fail_closed_when_s3_enabled(monkeypatch):
    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "S3_BUCKET", "b")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "http://minio:9000")
    monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3_SECRET_KEY", raising=False)
    with pytest.raises(blob_store.BlobStoreError, match="ACCESS_KEY|SECRET_KEY"):
        blob_store.upload_bytes("k", b"\xff\xd8\xff", "image/jpeg")


def test_bucket_without_endpoint_is_broken_not_dev(monkeypatch):
    """①: BUCKET مضبوط بلا ENDPOINT = مكسور (لا سقوط صامت لـfile://)."""
    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "S3_BUCKET", "b")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "")
    with pytest.raises(blob_store.BlobStoreError, match="misconfigured|S3_ENDPOINT"):
        blob_store.upload_bytes("k", b"\xff\xd8\xff", "image/jpeg")


def test_endpoint_scheme_from_ssl_flag_no_silent_http(monkeypatch):
    """②: المخطّط من S3_USE_SSL صراحةً — لا استنتاج صامت من الـendpoint."""
    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "minio.example.com:9000")
    monkeypatch.setattr(blob_store, "S3_USE_SSL", "true")
    assert blob_store._endpoint_url() == "https://minio.example.com:9000"
    monkeypatch.setattr(blob_store, "S3_USE_SSL", "false")
    assert blob_store._endpoint_url() == "http://minio.example.com:9000"
