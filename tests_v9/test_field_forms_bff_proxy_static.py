"""حُرّاس ساكنون لقناة BFF الخاصّة بالنماذج الميدانيّة (GAP-FIELD-FORMS-01 §8.6 — Slice 2).

نصّيّة صرفة (لا استيراد): service_proxy يستورد api.main كاملًا (scipy/منصّة) —
استيراده في بيئة الوحدة الدنيا يُجهض الجمع (درس fb1dee2). الحُرّاس يقرأون المصدر
ويفرضون: proxy بتوكن قناة مخصّص (لا SAHOOL_AGENT_TOKEN)، تجريد العميل من التوكن،
قائمة مسارات مغلقة (download/submissions فقط)، وتوصيل compose الراية والتوكن.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROXY = ROOT / "services/sahool-platform/api/routers/service_proxy.py"
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def _proxy_src() -> str:
    return PROXY.read_text(encoding="utf-8")


def test_field_forms_route_uses_dedicated_channel_token():
    src = _proxy_src()
    assert '"/api/field-forms/{path:path}"' in src, "مسار BFF للنماذج غائب"
    assert "X-Field-Forms-Token" in src, "حقن ترويسة القناة غائب"
    assert "_field_forms_token" in src, "دالة توكن القناة المخصّص غائبة"
    assert 'os.getenv("FIELD_FORMS_SERVICE_TOKEN"' in src
    # المنصّة لا تحقن SAHOOL_AGENT_TOKEN لقناة field-forms (عزل القنوات):
    route_body = src.split('"/api/field-forms/{path:path}"', 1)[1]
    assert "SAHOOL_AGENT_TOKEN" not in route_body, "قناة field-forms يجب ألّا تستعمل التوكن المشترك"


def test_client_service_headers_stripped():
    src = _proxy_src()
    # ترويسة القناة القادمة من العميل تُطرَد مع x-agent-token/x-tenant-id:
    assert '"x-agent-token", "x-tenant-id", "x-field-forms-token"' in src


def test_bff_path_allowlist_closed():
    src = _proxy_src()
    route_body = src.split('"/api/field-forms/{path:path}"', 1)[1]
    assert '{"download", "submissions"}' in route_body, "قائمة المسارات المغلقة غائبة/موسَّعة"
    assert "internal/field-forms/" in route_body, "الهدف الداخليّ غائب"
    # إدارة التعريفات/النشر لا تمرّ عبر BFF:
    for admin in ("definitions", "publish", "retire", "assignments"):
        assert (
            f'"{admin}"'
            not in route_body.split("allowed", 1)[1].split("raise HTTPException(404")[0]
        )


def test_compose_wires_flag_and_token_both_services():
    src = COMPOSE.read_text(encoding="utf-8")
    assert src.count("FIELD_FORMS_ENABLED") >= 1
    # التوكن يظهر في خدمتين: المنصّة (يحقن) وscout-ingest (يتحقّق) — + .env.example:
    assert src.count("FIELD_FORMS_SERVICE_TOKEN") >= 2
    assert "SCOUT_INGEST_URL" in src


def test_env_example_documents_channel():
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "FIELD_FORMS_ENABLED=0" in src, "الراية افتراضيًّا off في .env.example"
    assert "FIELD_FORMS_SERVICE_TOKEN=" in src
