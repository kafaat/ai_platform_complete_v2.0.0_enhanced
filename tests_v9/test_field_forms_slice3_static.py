"""حُرّاس ساكنون لـGAP-FIELD-FORMS-01 Slice 3 (الخادميّة): بوّابة الإدخال + قوننة
الهويّة + استبعاد الإسقاط + readyz حقيقيّ.

نصّيّة صرفة (لا استيراد): الوحدات تستورد asyncpg/المنصّة كاملةً — استيرادها في بيئة
الوحدة الدنيا يُجهض الجمع. الحُرّاس يقرأون المصدر ويُثبّتون القرارات الخمسة كي لا
تنحدر لاحقًا. مُعلَّمة unit.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parent.parent
NGINX = ROOT / "nginx/nginx.v9.conf"
PROXY = ROOT / "services/sahool-platform/api/routers/service_proxy.py"
FF_API = ROOT / "services/scout-ingest-service/field_forms_api.py"
PROJECTION = ROOT / "shared/contracts/ingest/projection.py"
INGEST_MAIN = ROOT / "services/scout-ingest-service/main.py"


def test_nginx_field_forms_ingress_to_platform_bff():
    """(1) بوّابة: /api/field-forms/ لها كتلة صريحة → platform_backend (لا تسقط إلى 404)."""
    src = NGINX.read_text(encoding="utf-8")
    assert "location /api/field-forms/" in src, "كتلة nginx للنماذج الميدانيّة غائبة"
    block = src.split("location /api/field-forms/", 1)[1].split("location ", 1)[0]
    assert "proxy_pass http://platform_backend/api/field-forms/" in block, (
        "يجب أن تمرّ عبر المنصّة (BFF) لتفرض JWT وتحقن توكن القناة"
    )


def test_bff_strips_client_authorization_and_cookie():
    """(2) BFF: مصادقة العميل (Authorization/Cookie) لا تُمرَّر للخدمات الداخليّة."""
    src = PROXY.read_text(encoding="utf-8")
    # حارس الشريحة 2 يبقى سليمًا (الترويسات الثلاث):
    assert '"x-agent-token", "x-tenant-id", "x-field-forms-token"' in src
    # الشريحة 3 تضيف تجريد authorization/cookie:
    assert '{"authorization", "cookie"}' in src, "تجريد مصادقة العميل غائب"


def test_field_forms_identity_is_server_canonical():
    """(3) قوننة الهويّة: provider/server يُشتقّان خادميًّا؛ قيَم العميل خارج الديدوب والتخزين."""
    src = FF_API.read_text(encoding="utf-8")
    assert 'CANONICAL_PROVIDER = "sahool-field-forms"' in src
    assert 'FIELD_FORMS_SERVER_ID = os.getenv("FIELD_FORMS_SERVER_ID"' in src
    # مفتاح الديدوب يستعمل الثوابت لا body.provider/body.server:
    dedup = src.split("dedup_key = derive_dedup_key(", 1)[1].split(")", 1)[0]
    assert "CANONICAL_PROVIDER" in dedup and "FIELD_FORMS_SERVER_ID" in dedup
    assert "body.provider" not in dedup and "body.server" not in dedup, (
        "قيمة العميل provider/server يجب ألّا تدخل مفتاح الديدوب (منع انتحال الخانة)"
    )
    # التخزين (INSERT external_submissions) يسجّل القيَم الخادميّة القانونيّة:
    insert = src.split("INSERT INTO external_submissions", 1)[1]
    assert "CANONICAL_PROVIDER" in insert and "FIELD_FORMS_SERVER_ID" in insert


def test_projection_excludes_field_forms_as_dead_letter():
    """(4) استبعاد الإسقاط: kind=field_form ⇒ dead_letter مُصنَّف بدل صفّ مشاهدة كلّه NULL."""
    proj = PROJECTION.read_text(encoding="utf-8")
    assert 'FIELD_FORM_KIND = "field_form"' in proj
    assert 'ProjectionSkip(reason="field_forms_not_projectable")' in proj
    body = proj.split("def project_submission", 1)[1]
    assert 'payload.get("kind") == FIELD_FORM_KIND' in body
    # الخدمة تزرع العلامة خادميًّا في normalized_payload:
    api = FF_API.read_text(encoding="utf-8")
    assert "from shared.contracts.ingest.projection import FIELD_FORM_KIND" in api
    assert '"kind": FIELD_FORM_KIND' in api


def test_readyz_is_real_db_check_fail_closed():
    """(5) readyz: فحص DB فعليّ (SELECT 1) + 503 fail-closed بدل "degraded" الكاذبة."""
    src = INGEST_MAIN.read_text(encoding="utf-8")
    ready = src.split("async def readyz", 1)[1].split("\n@", 1)[0].split("\ndef ", 1)[0]
    assert 'await conn.fetchval("SELECT 1")' in ready, "readyz لا يفحص DB فعليًّا"
    assert "status_code=503" in ready, "readyz يجب أن يفشل مُغلَقًا (503)"
    assert '"degraded"' not in ready, "لا جاهزيّة إيجابيّة كاذبة"
