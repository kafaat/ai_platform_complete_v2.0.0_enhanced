"""R1: مسحا التنبيهات والنضارة يسردان المستأجرين عبر مسبح المهامّ لا مسبح التطبيق.

مسبح التطبيق (NOBYPASSRLS) بلا سياق مستأجِر يرى ``fields`` فارغاً (FORCE RLS فاشلٌ-مغلق)،
فكان المسحان يُقيّمان صفر حقول دائماً.

بلا قاعدة مزيّفة (``FAKE-CONNECTION-ENFORCES-NOTHING-01``): المسبحان حارسان معتمان
(``object()``) لا يُجيبان أيّ استعلام، والدرزة المُرقَّعة هي **دالّة السرد نفسها**
(``api.scheduler.list_sweep_tenant_ids``) — يُقاس أيّ مسبحٍ تُسلَّم، وأنّ المسح يزور كلّ
مستأجِرٍ تُعيده. قبل الإصلاح كان المسح يُنادي ``_DB_POOL.acquire()`` مباشرةً فلا تُبلَغ
الدرزة أبداً (والحارس المعتم بلا ``acquire``) ⇒ صفر مستأجرين ⇒ الاختبار أحمر.
وحكمُ «الصفر تحت دورٍ مُقيَّد» منطقٌ صرف على صفّ ``ROLE_PROBE_SQL`` فيُختبَر مباشرةً.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit

TENANTS = (
    "11111111-1111-1111-1111-111111111111",
    "22222222-2222-2222-2222-222222222222",
)
APP_POOL = object()  # sahool_app — NOBYPASSRLS: بلا سياق يرى صفراً
JOBS_POOL = object()  # sahool_jobs — BYPASSRLS: يرى المستأجرين


@pytest.fixture
def captured_sweeps(monkeypatch):
    """يُشغّل ``_start_scheduler`` الحقيقيّ ويلتقط المسوح المُسجَّلة بلا مُجدوِل حيّ."""
    import api.imagery_automation as imagery_mod
    import api.main as main
    import api.scheduler as sched_mod
    from api.weather_automation import weather_automation

    async def _noop(*_a, **_k):
        return 0

    captured: dict = {}
    monkeypatch.setattr(sched_mod, "register_default_tasks", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sched_mod, "cluster_singleton", lambda fn, **_kw: fn)
    monkeypatch.setattr(sched_mod.scheduler, "start", lambda *a, **k: None)
    monkeypatch.setattr(imagery_mod, "bind_recovery_pool", _noop)
    monkeypatch.setattr(imagery_mod.imagery_automation, "load_from_db", _noop)
    monkeypatch.setattr(weather_automation, "set_pool", lambda _p: None)
    monkeypatch.setattr(weather_automation, "load_from_db", _noop)

    enumerations: list[tuple[object, str]] = []

    async def _list_sweep_tenant_ids(pool, *, sweep):
        enumerations.append((pool, sweep))
        # ما تراه القاعدة بكلّ دور: المُقيَّد بلا سياق ⇒ صفر؛ دور المهامّ ⇒ الكلّ.
        return list(TENANTS) if pool is JOBS_POOL else []

    monkeypatch.setattr(sched_mod, "list_sweep_tenant_ids", _list_sweep_tenant_ids)

    async def _start(app_pool, jobs_pool):
        monkeypatch.setattr(main, "_DB_POOL", app_pool)
        monkeypatch.setattr(main, "_JOBS_POOL", jobs_pool)
        await main._start_scheduler()
        return captured

    return _start, enumerations


def _visited_tenants(caplog, label: str) -> list[str]:
    """من زارهم المسح: قراءة حقول كلّ مستأجِر بسياقه تبلغ المسبح المعتم فتُعزَل وتُسجَّل باسمه."""
    return [
        tid
        for r in caplog.records
        if label in r.getMessage() and "تخطّي مستأجِر" in r.getMessage()
        for tid in TENANTS
        if tid in r.getMessage()
    ]


async def test_alerts_sweep_enumerates_through_the_jobs_pool_and_visits_every_tenant(
    captured_sweeps, caplog
):
    start, enumerations = captured_sweeps
    sweeps = await start(APP_POOL, JOBS_POOL)
    with caplog.at_level(logging.WARNING):
        await sweeps["run_alerts_evaluation"]()
    assert enumerations == [(JOBS_POOL, "أتمتة التنبيهات")]
    assert sorted(_visited_tenants(caplog, "أتمتة التنبيهات")) == sorted(TENANTS)


async def test_freshness_sweep_enumerates_through_the_jobs_pool_and_visits_every_tenant(
    captured_sweeps, caplog
):
    start, enumerations = captured_sweeps
    sweeps = await start(APP_POOL, JOBS_POOL)
    with caplog.at_level(logging.WARNING):
        await sweeps["check_decision_freshness"]()
    assert enumerations == [(JOBS_POOL, "فحص النضارة")]
    assert sorted(_visited_tenants(caplog, "فحص النضارة")) == sorted(TENANTS)


async def test_without_a_jobs_pool_the_sweep_falls_back_to_the_app_pool(captured_sweeps, caplog):
    """بلا مسبح مهامّ يعود السرد إلى مسبح التطبيق (الدور المُقيَّد) — وحكمُ صفره أدناه."""
    start, enumerations = captured_sweeps
    sweeps = await start(APP_POOL, None)
    with caplog.at_level(logging.WARNING):
        await sweeps["run_alerts_evaluation"]()
    assert enumerations == [(APP_POOL, "أتمتة التنبيهات")]
    assert _visited_tenants(caplog, "أتمتة التنبيهات") == []


def test_restricted_role_zero_is_declared_not_silent(caplog):
    from api.scheduler import declare_restricted_role_zero

    restricted = {"rolsuper": False, "rolbypassrls": False}
    with caplog.at_level(logging.CRITICAL, logger="sahool.scheduler"):
        assert declare_restricted_role_zero(restricted, sweep="t") is True
    assert any("JOBS_DATABASE_URL" in r.getMessage() for r in caplog.records)


def test_bypass_role_genuine_zero_is_not_alarmed(caplog):
    from api.scheduler import declare_restricted_role_zero

    with caplog.at_level(logging.CRITICAL, logger="sahool.scheduler"):
        for row in (
            {"rolsuper": False, "rolbypassrls": True},
            {"rolsuper": True, "rolbypassrls": False},
            None,  # تعذّر القياس ⇒ لا حكم
        ):
            assert declare_restricted_role_zero(row, sweep="t") is False
    assert not caplog.records


async def test_no_pool_lists_no_tenants():
    from api.scheduler import list_sweep_tenant_ids

    assert await list_sweep_tenant_ids(None, sweep="t") == []
