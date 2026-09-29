"""حارس: عامل استهلاك raster_cache_invalidations (FINDING-005) + إخلاء الكاش (FINDING-010).

يؤكّد سلوكيّاً: دوالّ الإبطال/الإخلاء في main تعمل على بنية المسار الصحيحة، والعامل
يطالب المعلّقات (FOR UPDATE SKIP LOCKED)، يُبطِل، ويُنهي الحالة؛ ومربوط كخدمة compose
خلف راية تفعيل.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
RASTER = REPO / "services" / "raster-service"
WORKER = RASTER / "cache_invalidation_worker.py"
MAINT = RASTER / "tile_cache_maint.py"
COMPOSE = REPO / "docker-compose.v9.yml"


def _load_maint():
    """يحمّل tile_cache_maint (وحدة خفيفة، اسم فريد — بلا تصادم مع main العامّ)."""
    spec = importlib.util.spec_from_file_location("raster_tile_cache_maint", MAINT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _tile_path(maint, tenant, field, index, date, z, x, y, v) -> str:
    return os.path.join(
        maint.tile_cache_field_dir(tenant, field),
        maint.safe_cache_segment(index),
        maint.safe_cache_segment(date),
        maint.safe_cache_segment(v),
        str(z),
        f"{x}_{y}.png",
    )


# ─── FINDING-010: prune + invalidate helpers (behavioural) ────────────────────


def test_invalidate_field_tile_cache_removes_only_that_field(tmp_path, monkeypatch) -> None:
    maint = _load_maint()
    monkeypatch.setattr(maint, "UPLOAD_DIR", str(tmp_path), raising=True)
    f1 = _tile_path(maint, "tenantX", "fieldA", "NDVI", "2026-01-01", 12, 1, 2, "v1")
    f2 = _tile_path(maint, "tenantX", "fieldB", "NDVI", "2026-01-01", 12, 1, 2, "v1")
    for p in (f1, f2):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(b"x")
    deleted = maint.invalidate_field_tile_cache("tenantX", "fieldA")
    assert deleted == 1, "يجب حذف بلاطة fieldA فقط"
    assert not os.path.exists(f1), "بلاطة fieldA يجب أن تُحذَف"
    assert os.path.exists(f2), "بلاطة fieldB يجب ألّا تُمَسّ"


def test_prune_tile_cache_deletes_by_ttl(tmp_path, monkeypatch) -> None:
    maint = _load_maint()
    monkeypatch.setattr(maint, "UPLOAD_DIR", str(tmp_path), raising=True)
    old = _tile_path(maint, "t", "f", "NDVI", "2020-01-01", 12, 1, 2, "old")
    new = _tile_path(maint, "t", "f", "NDVI", "2026-01-01", 12, 3, 4, "new")
    for p in (old, new):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(b"x")
    stale = time.time() - 7200
    os.utime(old, (stale, stale))
    stats = maint.prune_tile_cache(ttl_seconds=3600, max_bytes=0)
    assert stats["deleted_ttl"] == 1, "يجب حذف الملفّ المتجاوز TTL فقط"
    assert not os.path.exists(old) and os.path.exists(new)


def test_prune_disabled_when_no_ttl_or_quota(tmp_path, monkeypatch) -> None:
    maint = _load_maint()
    monkeypatch.setattr(maint, "UPLOAD_DIR", str(tmp_path), raising=True)
    p = _tile_path(maint, "t", "f", "NDVI", "2026-01-01", 12, 1, 2, "v")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(b"x")
    stats = maint.prune_tile_cache(ttl_seconds=0, max_bytes=0)
    assert stats["deleted_ttl"] == 0 and stats["deleted_quota"] == 0
    assert os.path.exists(p), "بلا TTL/حصّة: لا حذف"


# ─── FINDING-005: worker claims + processes queue ─────────────────────────────


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.executed: list[str] = []
        self.calls: list[tuple[str, tuple]] = []

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Txn()

    async def fetch(self, _sql, *_a):
        return self._rows

    async def execute(self, sql, *args):
        self.executed.append(sql)
        self.calls.append((sql, args))
        return "UPDATE 1"


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Acq()


def _load_worker():
    sys.modules.setdefault("asyncpg", types.ModuleType("asyncpg"))
    rs = str(RASTER)
    if rs not in sys.path:
        sys.path.insert(0, rs)
    spec = importlib.util.spec_from_file_location("cache_invalidation_worker", WORKER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_worker_claims_and_marks_processed(monkeypatch) -> None:
    mod = _load_worker()
    # لا نلمس القرص: نُبدّل الإبطال بعدّاد.
    monkeypatch.setattr(
        mod.tile_cache_maint, "invalidate_field_tile_cache", lambda t, f: 3, raising=True
    )
    rows = [
        {
            "id": 1,
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "field_id": "f1",
            "reason": "geom",
        }
    ]
    conn = _FakeConn(rows)
    n = asyncio.run(mod.run_once(_FakePool(conn)))
    assert n == 1, "صفّ واحد يجب أن يُعالَج"
    joined = " ".join(conn.executed)
    assert "status='processing'" in joined, "يجب المطالبة بالصفّ (processing)"
    assert "asset_status='stale'" in joined, "يجب وسم أصول الحقل stale"
    assert "status='processed'" in joined, "يجب إنهاء الصفّ processed"


# ─── نطاقُ الوسم: ما سبق التغييرَ المُسمّى وحدَه (مقيسٌ حيّاً 2026-09-29) ─────────────────
# كان العاملُ يَسِم كلَّ أصلٍ ``ready`` للحقل، فإبطالُ ``field.created`` وَسَم صورَ Sentinel-2
# التي أُنتِجت **بعد** الإنشاء بثوانٍ (مصغّراتٌ 404). الشاهدُ السلوكيّ على قاعدةٍ حيّة في
# ``test_d1_raster_invalidation_owner_api_integration.py``؛ وهنا الوصلُ بلا قاعدة: ما يقرؤه
# العاملُ من صفّ الطابور يصل فعلاً إلى عبارة الوسم.

# لحظةٌ بالصيغة التي تكتبها القاعدةُ فعلاً (``to_jsonb(now())``، مقيسةٌ على PG16).
_CHANGED_AT = "2026-09-29T22:46:37.958391+00:00"


def _queued_row(metadata, created_at=None):
    from datetime import UTC, datetime

    return {
        "id": 7,
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "field_id": "fld_new",
        "reason": "field.created",
        # asyncpg يُعيد العمودَ نصّاً بلا codec — كما يصل العاملَ حيّاً.
        "metadata": json.dumps(metadata) if isinstance(metadata, dict) else metadata,
        "created_at": created_at or datetime(2026, 9, 29, 22, 46, 40, tzinfo=UTC),
    }


def test_scope_is_the_named_revision_and_the_instant_the_platform_recorded() -> None:
    from datetime import datetime

    mod = _load_worker()
    row = _queued_row(
        {
            "geometry_revision": 1,
            "geometry_changed_at": _CHANGED_AT,
            "request_id": "field.created:fld_new:rev1",
            "scope": ["tiles", "indices", "zones"],
        }
    )
    assert mod.invalidation_scope(row) == (1, datetime.fromisoformat(_CHANGED_AT))


def test_scope_falls_back_to_the_queue_time_and_never_guesses() -> None:
    from datetime import UTC, datetime

    mod = _load_worker()
    queued = datetime(2026, 9, 29, 22, 46, 40, tzinfo=UTC)
    # نيّةٌ أقدم من العقد (بلا لحظة) ⇒ وصولُ الأمر إلى المالك، لا «كلُّ جاهز».
    assert mod.invalidation_scope(_queued_row({"geometry_revision": 3}, queued)) == (3, queued)
    # ``True`` ليست مراجعة، ولحظةٌ بلا منطقة زمنيّة لا تُخمَّن منطقتُها.
    naive = {"geometry_revision": True, "geometry_changed_at": "2026-09-29T22:46:37"}
    assert mod.invalidation_scope(_queued_row(naive, queued)) == (None, queued)
    # صفٌّ بلا بيانات (السلوك السابق) يبقى قابلاً للمعالجة.
    assert mod.invalidation_scope({"metadata": None, "created_at": None}) == (None, None)


def test_the_stale_statement_receives_the_scope_of_the_named_change(monkeypatch) -> None:
    from datetime import datetime

    mod = _load_worker()
    monkeypatch.setattr(
        mod.tile_cache_maint, "invalidate_field_tile_cache", lambda t, f: 0, raising=True
    )
    row = _queued_row({"geometry_revision": 1, "geometry_changed_at": _CHANGED_AT})
    conn = _FakeConn([row])
    assert asyncio.run(mod.run_once(_FakePool(conn))) == 1
    stale = [(sql, args) for sql, args in conn.calls if "asset_status='stale'" in sql]
    assert len(stale) == 1, "عبارةُ الوسم لم تُنفَّذ مرّةً واحدة"
    sql, args = stale[0]
    assert args == (row["tenant_id"], "fld_new", 1, datetime.fromisoformat(_CHANGED_AT))
    # الوسمُ مقيّدٌ بالمراجعة وباللحظة — لا ``WHERE`` بالحقل وحدَه كما كان.
    assert "geometry_revision < $3::int" in sql and "created_at < $4::timestamptz" in sql


def test_worker_uses_skip_locked_and_flag_and_compose() -> None:
    src = WORKER.read_text(encoding="utf-8")
    assert "FOR UPDATE SKIP LOCKED" in src, "المطالبة يجب أن تكون FOR UPDATE SKIP LOCKED"
    assert "RASTER_CACHE_INVALIDATION_ENABLED" in src, "يجب راية تفعيل"
    assert "JOBS_DATABASE_URL" in src, "يجب استخدام دور الوظائف (BYPASSRLS)"
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "sahool-raster-cache-invalidation-worker:" in compose, (
        "خدمة العامل غير موصولة في compose"
    )
    assert "cache_invalidation_worker" in compose, "أمر تشغيل العامل غائب"
