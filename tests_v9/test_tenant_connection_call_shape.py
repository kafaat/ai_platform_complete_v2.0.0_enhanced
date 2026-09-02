"""TENANT-CONNECTION-CALL-SHAPE — عطلٌ يتنكّر في زيّ «القاعدة غير متاحة».

**مُكذَّبٌ بالتنفيذ لا موصوف.** ``api/main.py::tenant_connection`` توقيعُها ``(user)``
وتقرأ ``user.tenant_id`` و``user.user_id`` و``user.role`` لتضبط GUCات RLS الثلاثة.
وكان **٢٢ موضعاً** يمرّرون مُعرِّفَ المستأجِر عارياً؛ وموضعان ينادون
``main.tenant_connection_for`` — **دالّةً لا وجودَ لها**.

والسؤالُ الذي يُفرِّق التوصيفَ عن القياس: *لِمَ لم يظهر هذا قطّ؟* لأنّ ``get_pool()``
أوّلُ سطرٍ في الدالّة، فترمي ٥٠٣ **قبل** أن تمسّ الوسيط. فالشكلُ الصحيح والخاطئ
يُعطيان — في كلّ بيئةٍ بلا قاعدة، وهي بيئةُ الاختبارات وCI — **الجوابَ نفسَه بالحرف**.
``test_without_a_live_pool_both_shapes_are_indistinguishable`` هو هذا القياس، وهو
**لبُّ** الملفّ: يُثبت أنّ الاختبارات لم تكن لتراه مهما كثرت.

وحيث يظهر يكون مقنّعاً: ١٦/١٦ من مواضع ``gis_cloud_native`` داخل ``except Exception``
⇒ ٥٠٣ «القاعدة غير متاحة أو الهجرات غير مطبّقة» (جملةٌ كاذبة)؛ وفي ``irrigation_mpc``
المصائدُ fail-closed ⇒ ``{"status": "blocked", "reason": "field_not_owned"}``: يُقال
للمزارع «هذا الحقلُ ليس لك» والحقلُ حقلُه. **التصميمُ الأمينُ هو ما أخفى العطل.**

والحارسُ يُقاس في الاتّجاهين: أخضرُ على الشجرة السويّة (وإلّا كان إزعاجاً يُلتَفّ
عليه)، وأحمرُ على كلّ صنفٍ مزروعٍ على حدة.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import textwrap
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services" / "sahool-platform" / "api" / "main.py"
GUARD_SRC = ROOT / "scripts" / "ci" / "tenant_connection_call_shape_guard.py"


def _guard(**overrides):
    """يُحمَّل الحارسُ نسخةً طازجةً — فالمِسبارُ يوجّه ``ROOT``/``MAIN`` إلى رملٍ معزول."""
    spec = importlib.util.spec_from_file_location("_tcs_guard", GUARD_SRC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, value in overrides.items():
        setattr(module, key, value)
    return module


# ── ① الدالّةُ الحقيقيّةُ تُنفَّذ من مصدرها — لا تُعاد كتابتُها ─────────────
class _Conn:
    async def execute(self, *_a, **_k):
        return "OK"

    def transaction(self):
        return _Null()


class _Null:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_a):
        return False


class _Acquire:
    async def __aenter__(self):
        return _Conn()

    async def __aexit__(self, *_a):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code


class _User:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "viewer"


def _real_tenant_connection(pool):
    """يقتطع ``tenant_connection`` من ``main.py`` وينفّذها بـ``get_pool`` مُسيطَرٍ عليه.

    الاقتطاعُ من المصدر مقصود: لو غُيِّر التوقيعُ غداً تبِعه هذا الاختبارُ من نفسه،
    ولا يبقى نسخةً ثانيةً تتّفق اليوم وتنحرف غداً.
    """
    fn = next(
        n
        for n in ast.parse(MAIN.read_text(encoding="utf-8")).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "tenant_connection"
    )

    def get_pool():
        if pool is None:
            raise _HTTPException(503, "قاعدة البيانات غير مفعّلة")
        return pool

    namespace = {
        "asynccontextmanager": asynccontextmanager,
        "get_pool": get_pool,
        "HTTPException": _HTTPException,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(MAIN), "exec"), namespace)  # noqa: S102
    return namespace["tenant_connection"]


def _open(tenant_connection, arg) -> str:
    async def run():
        try:
            async with tenant_connection(arg):
                return "opened"
        except Exception as exc:  # noqa: BLE001 - النتيجةُ هي المقيس
            return f"{type(exc).__name__}: {exc}"

    return asyncio.run(run())


def test_without_a_live_pool_both_shapes_are_indistinguishable():
    """**لبُّ العطل:** بلا قاعدةٍ يُعطي الشكلان الجوابَ نفسَه — فلا اختبارٍ كان ليراه."""
    tenant_connection = _real_tenant_connection(pool=None)
    user = _User()
    wrong = _open(tenant_connection, user.tenant_id)
    right = _open(tenant_connection, user)
    assert wrong == right, "لو اختلفا لكان العطلُ مرئيّاً بلا قاعدة — وليس كذلك"
    assert "503" in wrong


def test_with_a_live_pool_the_bare_tenant_id_is_a_type_error():
    tenant_connection = _real_tenant_connection(pool=_Pool())
    user = _User()
    result = _open(tenant_connection, user.tenant_id)
    assert result.startswith("AttributeError"), result
    assert "tenant_id" in result


def test_with_a_live_pool_the_user_object_opens_the_connection():
    """الشاهدُ السويّ: بلا هذا يصير الحارسُ إزعاجاً يُلتَفّ عليه."""
    tenant_connection = _real_tenant_connection(pool=_Pool())
    assert _open(tenant_connection, _User()) == "opened"


# ── ② العقدُ مُشتَقٌّ من التعريف لا مكتوبٌ في الحارس ─────────────────────
def test_the_guard_derives_its_contract_from_the_definition():
    param, attrs = _guard().contract()
    assert param == "user"
    assert {"tenant_id", "user_id", "role"} <= attrs


# ── ③ الحارسُ في الاتّجاهين ───────────────────────────────────────────────
def test_the_repository_is_clean_today():
    assert _guard().scan() == []


def _sandbox(tmp_path: Path, router_body: str) -> dict:
    """شجرةٌ مصغّرة: ``main.py`` حقيقيّةُ العقد + راوترٌ واحدٌ يحمل الطفرة."""
    platform = tmp_path / "services" / "sahool-platform"
    (platform / "api" / "routers").mkdir(parents=True)
    (platform / "api" / "main.py").write_text(
        textwrap.dedent(
            '''
            from contextlib import asynccontextmanager

            def get_pool():
                return None

            @asynccontextmanager
            async def tenant_connection(user):
                """يضبط GUCات RLS الثلاثة."""
                pool = get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "SELECT set_config($1, $2, $3)",
                        str(user.tenant_id),
                        str(user.user_id),
                        str(user.role),
                    )
                    yield conn
            '''
        ),
        encoding="utf-8",
    )
    (platform / "api" / "routers" / "probe.py").write_text(
        textwrap.dedent(router_body), encoding="utf-8"
    )
    return {"ROOT": tmp_path, "PLATFORM": platform, "MAIN": platform / "api" / "main.py"}


def test_the_sandbox_itself_is_clean_before_any_mutation(tmp_path):
    """وإلّا لاحمرّ الحارسُ على الطفرة لعلّةٍ في الرمل لا في الطفرة."""
    env = _sandbox(
        tmp_path,
        """
        from api import main
        from api.main import tenant_connection

        async def route(user):
            async with tenant_connection(user) as conn:
                return await main.get_pool()
        """,
    )
    assert _guard(**env).scan() == []


@pytest.mark.parametrize(
    ("case", "body", "expected"),
    [
        (
            "سمةٌ بدل الكائن",
            """
            from api.main import tenant_connection

            async def route(user):
                async with tenant_connection(user.tenant_id) as conn:
                    return conn
            """,
            "tenant_connection(user.tenant_id)",
        ),
        (
            "مُعرِّفٌ عارٍ باسم السمة",
            """
            from api.main import tenant_connection

            async def route(tenant_id):
                async with tenant_connection(tenant_id) as conn:
                    return conn
            """,
            "tenant_connection(tenant_id)",
        ),
        (
            "مرجعُ main.X غيرُ معرَّف",
            """
            from api import main

            async def route(tenant_id):
                async with main.tenant_connection_for(tenant_id) as conn:
                    return conn
            """,
            "main.tenant_connection_for",
        ),
    ],
)
def test_each_planted_class_reddens_for_its_own_reason(tmp_path, case, body, expected):
    problems = _guard(**_sandbox(tmp_path, body)).scan()
    assert problems, f"{case}: الطفرةُ نجت"
    assert any(expected in p for p in problems), f"{case}: احمرّ لسببٍ آخر — {problems}"
