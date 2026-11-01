"""R1: مسحا التنبيهات والنضارة يسردان المستأجرين عبر مسبح المهامّ لا مسبح التطبيق.

مسبح التطبيق (NOBYPASSRLS) بلا سياق مستأجِر يرى ``fields`` فارغاً (FORCE RLS فاشلٌ-مغلق)،
فكان المسحان يُقيّمان صفر حقول دائماً. القاعدة هنا مزيّفة تحاكي RLS: الدور المُقيَّد
يُرجِع صفراً لسرد بلا سياق، ودور المهامّ (BYPASSRLS) يرى المستأجرين.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.unit

TENANTS = {
    "11111111-1111-1111-1111-111111111111": ["f-a1", "f-a2"],
    "22222222-2222-2222-2222-222222222222": ["f-b1"],
}


class _Conn:
    def __init__(self, bypass: bool):
        self.bypass = bypass

    async def fetch(self, sql, *args):
        if "DISTINCT tenant_id FROM fields" in sql:
            # محاكاة tenant_isolation: سياقٌ فارغ تحت دورٍ مُقيَّد ⇒ صفر صفوف.
            return [{"tenant_id": t} for t in TENANTS] if self.bypass else []
        return []

    async def fetchrow(self, sql, *args):
        if "pg_roles" in sql:
            return {"rolsuper": False, "rolbypassrls": self.bypass}
        return None


class _Pool:
    def __init__(self, bypass: bool):
        self.bypass = bypass

    @asynccontextmanager
    async def acquire(self):
        yield _Conn(self.bypass)


async def _noop(*_a, **_k):
    return 0


@pytest.fixture
def captured_sweeps(monkeypatch):
    """يُشغّل ``_start_scheduler`` الحقيقيّ ويلتقط المسوح المُسجَّلة بلا مُجدوِل حيّ."""
    import api.imagery_automation as imagery_mod
    import api.main as main
    import api.scheduler as sched_mod
    from api.weather_automation import weather_automation

    captured: dict = {}
    monkeypatch.setattr(sched_mod, "register_default_tasks", lambda **kw: captured.update(kw))
    monkeypatch.setattr(sched_mod, "cluster_singleton", lambda fn, **_kw: fn)
    monkeypatch.setattr(sched_mod.scheduler, "start", lambda *a, **k: None)
    monkeypatch.setattr(imagery_mod, "bind_recovery_pool", _noop)
    monkeypatch.setattr(imagery_mod.imagery_automation, "load_from_db", _noop)
    monkeypatch.setattr(weather_automation, "set_pool", lambda _p: None)
    monkeypatch.setattr(weather_automation, "load_from_db", _noop)

    listed: list[str] = []
    evaluated: list[tuple[str, str]] = []

    class _TenantConn:
        def __init__(self, tid):
            self.tid = tid

        async def fetch(self, sql, *args):
            if "SELECT field_id FROM fields" in sql:
                listed.append(self.tid)
                return [{"field_id": f} for f in TENANTS.get(self.tid, [])]
            return []

        async def fetchrow(self, *_a, **_k):
            return None

    @asynccontextmanager
    async def _tenant_connection(user):
        yield _TenantConn(str(user.tenant_id))

    async def _persist(user, field_id):
        evaluated.append((str(user.tenant_id), field_id))
        return [], None

    monkeypatch.setattr(main, "tenant_connection", _tenant_connection)
    monkeypatch.setattr(main, "_evaluate_field_alerts_persist", _persist)

    async def _start(app_pool, jobs_pool):
        monkeypatch.setattr(main, "_DB_POOL", app_pool)
        monkeypatch.setattr(main, "_JOBS_POOL", jobs_pool)
        await main._start_scheduler()
        return captured

    return _start, listed, evaluated


async def test_alerts_sweep_evaluates_every_tenant_field(captured_sweeps):
    start, listed, evaluated = captured_sweeps
    sweeps = await start(_Pool(bypass=False), _Pool(bypass=True))
    await sweeps["run_alerts_evaluation"]()
    assert sorted(listed) == sorted(TENANTS)
    assert sorted(evaluated) == sorted((t, f) for t, fs in TENANTS.items() for f in fs)


async def test_freshness_sweep_sees_every_tenant(captured_sweeps):
    start, listed, _ = captured_sweeps
    sweeps = await start(_Pool(bypass=False), _Pool(bypass=True))
    await sweeps["check_decision_freshness"]()
    assert sorted(listed) == sorted(TENANTS)


async def test_restricted_fallback_zero_is_declared_not_silent(captured_sweeps, caplog):
    """بلا مسبح مهامّ يعود السرد إلى الدور المُقيَّد: الصفرُ يُعلَن حرجاً لا «لا مستأجرين»."""
    start, listed, evaluated = captured_sweeps
    sweeps = await start(_Pool(bypass=False), None)
    with caplog.at_level(logging.CRITICAL, logger="api.sweep_tenants"):
        await sweeps["run_alerts_evaluation"]()
    assert listed == [] and evaluated == []
    assert any("JOBS_DATABASE_URL" in r.getMessage() for r in caplog.records)


async def test_bypass_role_genuine_zero_is_not_alarmed(caplog):
    from api.sweep_tenants import list_sweep_tenant_ids

    class _Empty(_Conn):
        async def fetch(self, sql, *args):
            return []

    class _EmptyPool(_Pool):
        @asynccontextmanager
        async def acquire(self):
            yield _Empty(self.bypass)

    with caplog.at_level(logging.CRITICAL, logger="api.sweep_tenants"):
        assert await list_sweep_tenant_ids(_EmptyPool(bypass=True), sweep="t") == []
    assert not caplog.records
    assert await list_sweep_tenant_ids(None, sweep="t") == []
