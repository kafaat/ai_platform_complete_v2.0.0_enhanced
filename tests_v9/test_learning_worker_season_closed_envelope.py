"""عامل التعلّم يُسقِط كلّ ``season.closed`` — معرّف الموسم في ``entity_id`` لا في الحمولة.

``handle_envelope`` قرأ ``payload["season_id"]`` بينما منتِجو الحدث
(``api/routers/fields.py`` عبر ``_emit_domain_event(conn, user, "SEASON_CLOSED", "season",
season_id, {...})``) حملوا المعرّف هويّةَ كيانٍ في المغلّف وحده. فكان ``KeyError`` يُجهِض
المعاملة ويعيد التسليم إلى الأبد: لم يصل إغلاقُ موسمٍ واحد إلى التعلّم.

المغلّف هنا مبنيٌّ بالشكل الذي يُخرجه ``OutboxWorker`` (``api/event_bus.py``) حرفيّاً:
``event_id/event_type/entity_type/entity_id/tenant_id/payload/correlation_id/...``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = ROOT / "services/sahool-platform/workers/canonical_execution_learning_worker.py"
FIELDS_PATH = ROOT / "services/sahool-platform/api/routers/fields.py"
TENANT = "00000000-0000-0000-0000-0000000000b2"


def _worker():
    spec = importlib.util.spec_from_file_location("_learning_worker_season_closed", WORKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Tx:
    def __init__(self, log):
        self.log = log

    async def start(self):
        self.log.append("start")

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class _Conn:
    def __init__(self):
        self.log: list[str] = []

    def transaction(self):
        return _Tx(self.log)

    async def execute(self, sql, *args):
        self.log.append(sql)


class _Pool:
    def __init__(self):
        self.conn = _Conn()
        self.released = 0

    async def acquire(self):
        return self.conn

    async def release(self, conn):
        self.released += 1


def _envelope(payload: dict, *, entity_type: str = "season", entity_id: str = "ssn-42"):
    return {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "season.closed",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "tenant_id": TENANT,
        "payload": payload,
        "correlation_id": None,
        "causation_id": None,
        "occurred_at": "2026-11-08T00:00:00+00:00",
    }


@pytest.fixture
def worker(monkeypatch):
    mod = _worker()
    calls: list[dict] = []

    async def fake_process(conn, **kw):
        calls.append(kw)
        return {"status": "blocked"}

    monkeypatch.setattr(mod, "process_season_closed_event", fake_process)
    mod._calls = calls
    return mod


@pytest.mark.asyncio
async def test_legacy_explicit_close_payload_falls_back_to_envelope_entity_id(worker):
    """حمولة ``update_season`` قبل الإصلاح: ``{field_id, reason}`` بلا season_id."""
    pool = _Pool()
    await worker.handle_envelope(
        pool, _envelope({"field_id": "fld-7", "reason": "explicit_update"})
    )
    assert worker._calls == [
        {
            "event_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": TENANT,
            "field_id": "fld-7",
            "season_id": "ssn-42",
            "minimum_outcomes": 3,
        }
    ]
    assert "commit" in pool.conn.log and pool.released == 1


@pytest.mark.asyncio
async def test_legacy_superseded_close_payload_falls_back_to_envelope_entity_id(worker):
    """حمولة ``create_season`` (إغلاق آليّ) قبل الإصلاح."""
    payload = {"field_id": "fld-7", "reason": "superseded_by_new_season", "superseded_by": "s-new"}
    await worker.handle_envelope(_Pool(), _envelope(payload, entity_id="ssn-old"))
    assert worker._calls[0]["season_id"] == "ssn-old"


@pytest.mark.asyncio
async def test_payload_season_id_wins_when_present(worker):
    payload = {"field_id": "fld-7", "season_id": "ssn-42", "reason": "explicit_update"}
    await worker.handle_envelope(_Pool(), _envelope(payload))
    assert worker._calls[0]["season_id"] == "ssn-42"


@pytest.mark.asyncio
async def test_non_season_entity_without_season_id_is_rejected_not_guessed(worker):
    pool = _Pool()
    with pytest.raises(ValueError, match="SEASON_ID_REQUIRED"):
        await worker.handle_envelope(
            pool, _envelope({"field_id": "fld-7"}, entity_type="field", entity_id="fld-7")
        )
    assert worker._calls == []
    assert "rollback" in pool.conn.log


def test_fields_router_season_closed_producers_carry_season_id():
    """المنتِجون يحملون season_id في الحمولة أيضاً (لا اعتماد على المغلّف وحده)."""
    src = FIELDS_PATH.read_text(encoding="utf-8")
    chunks = src.split('"SEASON_CLOSED",')[1:]
    assert len(chunks) >= 2, "تغيّر عدد منتِجي SEASON_CLOSED في fields.py"
    for chunk in chunks:
        head = chunk[:400]
        assert '"season_id":' in head, head
