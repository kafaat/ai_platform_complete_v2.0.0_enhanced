"""كلُّ مسارٍ مُسجَّل في ``main.py`` يُسمّيه اختبارٌ واحدٌ على الأقلّ — راتشِتٌ أساسُه صفر.

``SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01``: الأربعةُ التي أُغلِقت قبل هذا
(``test_crop_stress_endpoints.py``) أُغلِقت لأنّها حملت العطل، لا لأنّ آليّةً أغلقتها —
والستّةُ الباقية (ثمانيةٌ مقيسةً على ``bcb7f0ed``) بقيت مكشوفةً للصنف نفسه. شهدها الآن
``test_routes_witnessed_through_the_request_path.py``، وهذا الاختبارُ يمنع أن يُسجَّل مسارٌ
جديد بلا شاهد: الأساسُ ``UNWITNESSED_BASELINE`` فارغ، فلا يُرفَع.

**القياس** كما قاسه السجلّ حين فُتِحت الفجوة: بادئةُ المسار قبل أوّل ``{`` (فيُحتسَب ما
يُبنى بـf-string كـ``/tile-data/{z}/…``)، مبحوثةً في نصّ ``tests/*.py`` **عدا هذا الملفّ**
(وإلّا شهد لنفسه). وللمسار الكامل بلا معاملات: مطابقةٌ تنتهي بعلامة اقتباس أو ``?`` —
فـ``/health`` لا يُحتسَب مشهوداً بظهور ``/healthz``.

**حدُّ صدق:** «يُسمّيه اختبار» أضعفُ من «يُختبَر سلوكُه» — ورودُ المسار نصّاً لا يعني
تأكيداً على جوابه. فالرقمُ سقفٌ متفائل لا أرضيّة، والراتشِتُ يمنع **الغياب التامّ** للشاهد
وهو ما حمل العطلَ فعلاً. ولا يرى مساراً يُسجَّل خارج ``main.py`` (``APIRouter`` مُضمَّن):
الخدمةُ اليوم لا تستعمل واحداً، والكاشفُ يُحمِر إن ظهر ``include_router`` كي لا يعمى صامتاً.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = SERVICE_DIR / "tests"
_SELF = Path(__file__).resolve()
_METHODS = frozenset({"get", "post", "put", "patch", "delete"})

#: مساراتٌ مُعلَنةٌ دَيناً بلا شاهد — **فارغ**، ولا يُضاف إليه: الشاهدُ يُكتب مع المسار.
UNWITNESSED_BASELINE: frozenset[tuple[str, str]] = frozenset()


def registered_routes(source: str) -> list[tuple[str, str]]:
    """``app.<verb>("/path")(handler)`` و``@app.<verb>("/path")`` — نقيّة، من نصّ ``main.py``."""
    routes: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _METHODS
            and isinstance(func.value, ast.Name)
            and func.value.id == "app"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            routes.append((func.attr.upper(), node.args[0].value))
    return sorted(set(routes))


def is_named(path: str, corpus: str) -> bool:
    if "{" in path:
        return path.split("{", 1)[0] in corpus
    return re.search(re.escape(path) + r"[\"'?]", corpus) is not None


def unwitnessed(routes: list[tuple[str, str]], corpus: str) -> set[tuple[str, str]]:
    return {(m, p) for m, p in routes if not is_named(p, corpus)}


def _corpus() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(TESTS_DIR.glob("*.py"))
        if p.resolve() != _SELF
    )


def test_every_route_registered_in_main_is_named_by_at_least_one_test():
    source = (SERVICE_DIR / "main.py").read_text(encoding="utf-8")
    assert "include_router" not in source, (
        "main.py يضمّ APIRouter — الكاشفُ لا يرى مساراته؛ وسِّعه قبل أن يعمى صامتاً"
    )
    routes = registered_routes(source)
    assert len(routes) >= 29, f"الكاشفُ لم يجد إلّا {len(routes)} مساراً — أيعمى عن صيغة تسجيل؟"
    missing = unwitnessed(routes, _corpus()) - UNWITNESSED_BASELINE
    assert not missing, (
        "SERVICE-ROUTES-WITNESSED-ONLY-AT-THE-PURE-CORE-01: مسارٌ مُسجَّل لا يُسمّيه أيُّ اختبار — "
        "اكتب له اختبارَ طلبٍ عبر TestClient(main.app): "
        + ", ".join(f"{m} {p}" for m, p in sorted(missing))
    )


def test_the_baseline_is_lowered_when_a_route_gains_a_witness():
    routes = registered_routes((SERVICE_DIR / "main.py").read_text(encoding="utf-8"))
    stale = UNWITNESSED_BASELINE - unwitnessed(routes, _corpus())
    assert not stale, f"الأساسُ يصف كوناً زال — خفِّضه: {sorted(stale)}"


def test_the_detector_sees_both_registration_styles_and_prefix_matches():
    """تكذيبٌ ذاتيّ: كاشفٌ يمرّ على شجرةٍ سليمة يمرّ أيضاً لو لم يفعل شيئاً."""
    source = (
        "app.get('/healthz')(rt.healthz)\n"
        "app.post('/v1/x/agro/y')(rt.y)\n"
        "@app.get('/runtime-identity')\ndef f():\n    return 1\n"
        "app.get('/v1/x/tile/{z}/{x}')(rt.tile)\n"
        "other.get('/not-app')(h)\n"
    )
    routes = registered_routes(source)
    assert routes == [
        ("GET", "/healthz"),
        ("GET", "/runtime-identity"),
        ("GET", "/v1/x/tile/{z}/{x}"),
        ("POST", "/v1/x/agro/y"),
    ]
    corpus = "client.get('/healthz')\nclient.get(f'/v1/x/tile/{z}/{x}')\n"
    assert unwitnessed(routes, corpus) == {("GET", "/runtime-identity"), ("POST", "/v1/x/agro/y")}
    # `/health` لا يُشهَد بظهور `/healthz` (البادئةُ وحدها كانت ستعدّه مشهوداً).
    assert not is_named("/health", "client.get('/healthz')")
    assert is_named("/health", 'client.get("/health")')
