"""التشديدُ الذي يُعطِّل بدل أن يحمي — يُقاس على **الوصلة** لا على طرفَيها.

**العطلُ المقيس:** `services/decision-service/main.py::_service_token_guard` يقرأ
`Authorization: Bearer` **وحدَه**؛ وعميلُ المنصّة كان يرسل `X-Agent-Token` الذي لا
يقرؤه أحد، ولا يرسل `Authorization` قطّ — صفرٌ من ٢٧ نداءً داخليّاً يمرّره. فما كان
التشديدُ معطَّلاً بل **غيرَ قابلٍ للتفعيل**: لحظةَ يضبط المشغّل
`DECISION_SERVICE_AUTH_TOKEN` كما توصي الوثيقة ترتدّ كلُّ نداءات المنصّة 401،
ويبتلعها `lexicographic_mpc_bridge` في `try` عريض فتسقط التوصيةُ الصالحة معها.
أي أنّ تفعيلَ ضابطِ الأمان يحوّل ثغرةً إلى انقطاعٍ صامت.

**ولماذا لم يمسكه اختبارٌ قائم:** لكلّ طرفٍ اختباراتُه، وكلاهما أخضر. الوسيطُ يُختبَر
بترويسةٍ تُبنى في الاختبار نفسِه، والعميلُ يُختبَر بأنّ ترويساته تحوي ما يضعه فيها.
ولا أحد ركّب **ما يرسله العميلُ فعلاً** على **ما يفرضه الوسيطُ فعلاً**. فهذا الملفّ
يفعل ذلك وحدَه: لا نصَّ يُفحَص، ولا ترويسةَ تُكتب يدويّاً.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from api.decision_service_client import decision_service_headers

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "s3rv1ce-t0ken-for-the-join"


DECISION_SERVICE_DIR = ROOT / "services" / "decision-service"


def _decision_service():
    """تُحمَّل الوحدةُ الحقيقيّة بمسارها: `services/decision-service` ليس حزمةً مستورَدة."""
    if str(DECISION_SERVICE_DIR) not in sys.path:  # جيرانُها تُستورَد بأسماءٍ عليا
        sys.path.insert(0, str(DECISION_SERVICE_DIR))
    spec = importlib.util.spec_from_file_location(
        "_decision_service_main", DECISION_SERVICE_DIR / "main.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_decision_service_main"] = module
    spec.loader.exec_module(module)
    return module


def _guard_verdict(module, headers: dict[str, str], *, required: str) -> str:
    """يُستدعى **الوسيطُ نفسُه** على ترويسةٍ كما يبنيها العميل — «مقبول» أو «401».

    ولا تُعاد كتابةُ قاعدته هنا عمداً: نسخةٌ من الشرط تنجح حين ينحرف الأصلُ عنها،
    وهي بالضبط طبقةُ الوهم التي جعلت الطرفَين أخضرَين والوصلةَ مكسورة.
    """
    import asyncio
    import os

    class _Request:
        def __init__(self) -> None:
            # الترويساتُ في Starlette غيرُ حسّاسةٍ لحالة الأحرف، والوسيطُ يقرأ
            # `authorization` صغيرةً بينما يرسل العميلُ `Authorization`.
            self.headers = {key.lower(): value for key, value in headers.items()}
            self.url = type("_Url", (), {"path": "/v1/decisions"})()

    async def _call_next(_request):
        return "reached_the_route"

    os.environ["DECISION_SERVICE_AUTH_TOKEN"] = required
    result = asyncio.run(module._service_token_guard(_Request(), _call_next))
    return "accepted" if result == "reached_the_route" else f"{result.status_code}"


def test_the_guard_reads_authorization_and_never_the_header_the_platform_used_to_send():
    """أصلُ العطل: `X-Agent-Token` ليس مقروءاً في مصدر الوسيط أصلاً."""
    source = (ROOT / "services" / "decision-service" / "main.py").read_text(encoding="utf-8")
    guard = source[source.index("async def _service_token_guard") :][:1200]
    assert 'request.headers.get("authorization"' in guard
    assert "X-Agent-Token" not in guard and "x-agent-token" not in guard.lower(), (
        "لو صار الوسيطُ يقرأ `X-Agent-Token` لتغيّر العقدُ الذي يقيسه هذا الملفّ — "
        "عدِّل الاختبار عمداً، لا تدعه يمرّ."
    )


def test_what_the_platform_sends_is_what_the_service_accepts(monkeypatch):
    """الوصلةُ نفسُها: ترويسةُ العميل الحقيقيّة تمرّ على قاعدة الوسيط الحقيقيّة."""
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", TOKEN)
    module = _decision_service()
    headers = decision_service_headers(tenant_id="t1")
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert _guard_verdict(module, headers, required=TOKEN) == "accepted"


def test_without_the_variable_the_platform_sends_no_bearer_and_the_service_refuses(monkeypatch):
    """الاتّجاه المقابل — وهو **حالةُ الإنتاج قبل هذا الإصلاح**: 401 على كلّ نداء.

    ويُبقي الاختبارُ التوافقَ الحاليّ صريحاً: بلا رمزٍ مضبوط لا تُرسَل ترويسةٌ أصلاً،
    فبيئةُ التطوير (رمزٌ غيرُ مضبوط على الخدمة) تبقى كما هي.
    """
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    module = _decision_service()
    headers = decision_service_headers(tenant_id="t1")
    assert "Authorization" not in headers
    assert _guard_verdict(module, headers, required=TOKEN) == "401"


def test_a_caller_supplied_authorization_is_not_overwritten_by_the_service_token(monkeypatch):
    """رمزُ الخدمة بديلٌ عند الغياب لا سارقٌ للترويسة: تفويضٌ صريح يبقى كما مُرّر."""
    monkeypatch.setenv("DECISION_SERVICE_TOKEN", TOKEN)
    headers = decision_service_headers(tenant_id="t1", authorization="Bearer caller-jwt")
    assert headers["Authorization"] == "Bearer caller-jwt"


def test_compose_hands_the_platform_the_same_variable_the_service_enforces():
    """الشيفرةُ وحدَها لا تُفعِّل شيئاً: بلا المتغيّر في compose يبقى الإصلاحُ خاملاً.

    وكان هذا نصفَ العطل — الاصطلاحُ قائمٌ وثلاثُ خدماتٍ تتلقّاه، والمنصّةُ (وهي
    المُنادي الأكبر) خارجه.
    """
    import re

    service = None
    seen: dict[str, set[str]] = {}
    for line in (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8").splitlines():
        header = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if header:
            service = header.group(1)
        if service and ":" in line:
            seen.setdefault(service, set()).add(line.strip().split(":", 1)[0])

    assert "DECISION_SERVICE_TOKEN" in seen.get("sahool-platform", set()), (
        "المنصّةُ لا تتلقّى `DECISION_SERVICE_TOKEN`، فلحظةَ يُفعَّل التشديدُ على الخدمة "
        "ترتدّ نداءاتُها كلُّها 401 — تعطيلٌ لا حماية."
    )
    assert "DECISION_SERVICE_AUTH_TOKEN" in seen.get("sahool-decision-service", set()), (
        "الطرفُ المُنفِّذ فقد متغيّرَه، فما عاد لِما تُرسله المنصّةُ ما يُقابله."
    )


def test_every_internal_call_path_inherits_the_header_from_one_builder():
    """٢٧ نداءً داخليّاً لا يمرّر أيٌّ منها `authorization` — فالإصلاحُ يجب أن يكون في المُنشِئ.

    لو وُضِع الرمزُ عند مواضع النداء لبقي أيُّ نداءٍ جديد بلا تفويض صامتاً. هذا
    الاختبارُ يُثبِّت أنّ المسارَين العامّين يستعملان `decision_service_headers`، فيبقى
    موضعُ الإصلاح واحداً.
    """
    source = (
        ROOT / "services" / "sahool-platform" / "api" / "decision_service_client.py"
    ).read_text(encoding="utf-8")
    for transport in ("async def decision_get_json", "async def decision_post_json"):
        body = source[source.index(transport) :][:1400]
        assert "decision_service_headers(" in body, (
            f"{transport} لا يبني ترويساته من المُنشِئ الواحد — "
            "فرمزُ الخدمة لن يصل منه، وهو بعينه شكلُ العطل الأصليّ."
        )
