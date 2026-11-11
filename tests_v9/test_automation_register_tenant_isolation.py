"""عزل المستأجرين في تسجيل أتمتة الطقس/الصور — لا كتابة عبر مسبح المهامّ (BYPASSRLS).

``POST /api/v1/automation/weather/register`` كان يمرّر ``field_id`` غير مُتحقَّق منه إلى
``weather_automation.register_location_persistent`` الذي يكتب على ``self._pool`` — مسبح
المهامّ (``sahool_jobs``، BYPASSRLS) — بـ``ON CONFLICT (location_key) DO UPDATE SET
field_id=EXCLUDED.field_id``: فيتجاوز سياسة v73 ويستولي مستأجِرٌ على ارتباط موقع حقل
غيره. هذه الاختبارات تثبّت:
  • حقلٌ لا يملكه المستأجِر ⇒ 404 ولا كتابة إطلاقاً (لا ذاكرة ولا قاعدة).
  • الكتابة تمرّ عبر اتّصال المستأجِر (``tenant_connection``) لا عبر مسبح المهامّ.
  • نقطة الصور الشقيقة تتحقّق من الملكيّة قبل الحفظ عبر مسبح المهامّ.
  • عقد معماريّ: لا موجِّه تحت ``api/routers/`` يستدعي مسار الكتابة عبر مسبح المهامّ.
"""

from __future__ import annotations

import ast
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_CORE = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
_ROUTERS = _CORE / "api" / "routers"
_TENANT = "00000000-0000-0000-0000-0000000000a1"


def _load():
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    import api.main  # noqa: F401 — يحلّ دورة استيراد الموجِّهات
    import api.routers.automation as automation

    return automation


class _TenantConn:
    def __init__(self, owned: set[str]):
        self.owned = owned
        self.calls: list[tuple[str, tuple]] = []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        if "FROM fields" in sql:
            field_id, tenant = args
            return 1 if (field_id in self.owned and tenant == _TENANT) else None
        return None

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "INSERT 0 1"


class _JobsPoolMustNotBeUsed:
    def acquire(self):
        raise AssertionError("مسار الطلب كتب عبر مسبح المهامّ (BYPASSRLS)")


def _user():
    return SimpleNamespace(tenant_id=_TENANT, user_id="u1", role="farmer")


@pytest.fixture
def wired(monkeypatch):
    automation = _load()
    from api.weather_automation import WeatherAutomation

    wa = WeatherAutomation()
    wa.set_pool(_JobsPoolMustNotBeUsed())
    conn = _TenantConn(owned={"f-own"})
    opened: list[object] = []

    @asynccontextmanager
    async def tenant_connection(user):
        opened.append(user)
        yield conn

    monkeypatch.setattr(automation, "weather_automation", wa)
    monkeypatch.setattr(automation, "tenant_connection", tenant_connection)
    return SimpleNamespace(mod=automation, wa=wa, conn=conn, opened=opened)


@pytest.mark.asyncio
async def test_foreign_field_is_rejected_and_nothing_is_written(wired):
    with pytest.raises(HTTPException) as e:
        await wired.mod.weather_register_endpoint(
            lat=15.0, lon=44.0, field_id="f-of-another-tenant", user=_user()
        )
    assert e.value.status_code == 404
    assert not any("weather_automation_locations" in sql for sql, _ in wired.conn.calls)
    assert wired.wa.registered_count() == 0


@pytest.mark.asyncio
async def test_owned_field_is_written_on_the_tenant_connection_not_the_jobs_pool(wired):
    out = await wired.mod.weather_register_endpoint(
        lat=15.0, lon=44.0, field_id="f-own", user=_user()
    )
    assert out["registered"] is True and out["field_id"] == "f-own"
    assert wired.opened, "لم يُفتح اتّصال المستأجِر"
    inserts = [(s, a) for s, a in wired.conn.calls if "weather_automation_locations" in s]
    assert len(inserts) == 1
    sql, args = inserts[0]
    # لا سرقة لارتباط صفّ قائم (قد يملكه مستأجِرٌ آخر غير مرئيّ تحت FORCE RLS).
    assert "DO NOTHING" in sql and "DO UPDATE" not in sql
    assert args[-1] == "f-own"
    # الذاكرة تُحدَّث بعد الالتزام فقط.
    assert wired.wa.registered_count() == 1


@pytest.mark.asyncio
async def test_global_location_without_field_skips_ownership_but_stays_on_tenant_conn(wired):
    await wired.mod.weather_register_endpoint(lat=16.0, lon=45.0, field_id=None, user=_user())
    assert not any("FROM fields" in s for s, _ in wired.conn.calls)
    assert any("weather_automation_locations" in s for s, _ in wired.conn.calls)


@pytest.mark.asyncio
async def test_imagery_register_rejects_a_foreign_field_before_the_jobs_pool_write(
    wired, monkeypatch
):
    persisted: list[str] = []

    async def register_field_persistent(field_id, bbox, tenant_id=None):
        persisted.append(field_id)

    monkeypatch.setattr(
        wired.mod.imagery_automation, "register_field_persistent", register_field_persistent
    )
    req = SimpleNamespace(field_id="f-of-another-tenant", bbox=[44.0, 15.0, 44.1, 15.1])
    with pytest.raises(HTTPException) as e:
        await wired.mod.imagery_register_field_endpoint(req=req, user=_user())
    assert e.value.status_code == 404
    assert persisted == []


def _router_sources():
    for path in sorted(_ROUTERS.glob("*.py")):
        yield path, path.read_text(encoding="utf-8")


def test_routers_do_not_write_through_the_jobs_pool():
    """الموجِّهات تخدم طلبات مستأجِر: لا تلمس مسبح المهامّ ولا مسار كتابة الطقس المبنيّ عليه."""
    offenders: list[str] = []
    for path, src in _router_sources():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.alias):
                name = node.name
            if name in {"_JOBS_POOL", "register_location_persistent"}:
                offenders.append(f"{path.name}:{getattr(node, 'lineno', '?')}:{name}")
    assert not offenders, offenders


def test_architecture_guard_sees_the_routers_directory():
    # حارسٌ لا يرى شيئاً يمرّ صامتاً — تأكيد أنّ المجموعة غير فارغة وتشمل automation.
    names = {p.name for p, _ in _router_sources()}
    assert "automation.py" in names and len(names) > 10, os.fspath(_ROUTERS)
