"""استهلاك outbox مُتعاضد (Stage A P1): processed_events dedup — منع الأثر المزدوج.

تسليم الـoutbox at-least-once (FOR UPDATE SKIP LOCKED + نشر ثمّ وسم 'sent' في معاملة):
صفّ مُرسَل قبيل تعطّل قبل وسمه 'sent' يُعاد نشره. هذه الاختبارات تُثبّت أنّ المُستهلِك
(OutboxWorker._send_one) يُطالِب الحدث عبر processed_events داخل نفس المعاملة، فيُطبَّق
الأثر الجانبيّ (النشر) **مرّةً واحدة** رغم إعادة التسليم — حتى مع تعطّل في المنتصف.

نواة بلا خدمات (conn زائف يحاكي asyncpg): قابلة للتشغيل offline في وظيفة الوحدات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.event_bus import (  # noqa: E402
    OUTBOX_CONSUMER_NAME,
    OutboxWorker,
    claim_event,
    claim_is_first,
)

# ─── conn زائف: يحاكي processed_events + event_outbox بلا قاعدة ───


class _FakeTx:
    """معاملة متداخلة زائفة (SAVEPOINT): تتراجع عن مطالبات processed_events عند خطأ.

    تُسجّل event_ids المُدرَجة داخل البلوك؛ لو خرج البلوك باستثناء (rollback) تُزال
    تلك المطالبات من conn._processed — يحاكي تراجع SAVEPOINT (المطالبة تُلغى مع الفشل).
    """

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        self._conn._tx_claims = []
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            # rollback: أزِل المطالبات التي أُدرِجت داخل هذا البلوك (تراجع SAVEPOINT)
            for eid in self._conn._tx_claims:
                self._conn._processed.discard(eid)
        self._conn._tx_claims = []
        return False  # لا يبتلع الاستثناء (يُعاد رفعه ليلتقطه retry tracking)


class FakeConn:
    """conn زائف ذرّيّ: processed_events set + سجلّ UPDATE/مطالبات للتأكيد."""

    def __init__(self):
        self._processed: set[str] = set()  # processed_events.event_id
        self._tx_claims: list[str] = []
        self.updates: list[tuple] = []  # (status_kind, outbox_id)
        self.claims: list[str] = []  # كلّ محاولة claim (للتدقيق)

    def transaction(self):
        return _FakeTx(self)

    async def execute(self, sql: str, *args) -> str:
        s = " ".join(sql.split())
        if "INSERT INTO processed_events" in s:
            event_id = str(args[0])
            self.claims.append(event_id)
            if event_id in self._processed:
                return "INSERT 0 0"  # تعارض على الـPK ⇒ DO NOTHING
            self._processed.add(event_id)
            self._tx_claims.append(event_id)
            return "INSERT 0 1"
        if "status = 'sent'" in s:
            self.updates.append(("sent", args[0]))
            return "UPDATE 1"
        if "retry_count = $1" in s:
            self.updates.append(("retry", args[-1]))
            return "UPDATE 1"
        return "OK"


def _row(event_id: str, *, outbox_id: int = 1, retry_count: int = 0) -> dict:
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "nats_subject": "sahool.events.test",
        "retry_count": retry_count,
        "event_type": "field.created",
        "entity_type": "field",
        "entity_id": "f-1",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "payload": {"k": "v"},
        "occurred_at": None,
    }


# ─── 1. claim_is_first: تفسير وسم INSERT (نقيّ، بلا قاعدة) ───


def test_claim_is_first_inserted_row_is_first():
    assert claim_is_first("INSERT 0 1") is True


def test_claim_is_first_conflict_is_not_first():
    assert claim_is_first("INSERT 0 0") is False


def test_claim_is_first_unknown_status_conservative_true():
    # وسم مشوَّه/خالٍ ⇒ يُعامَل محافِظاً كأوّل استهلاك (at-least-once أأمن من الابتلاع).
    assert claim_is_first(None) is True
    assert claim_is_first("") is True
    assert claim_is_first("garbage") is True


# ─── 2. claim_event على conn زائف: أوّل مطالبة vs مُعادة ───


@pytest.mark.asyncio
async def test_claim_event_new_then_duplicate():
    conn = FakeConn()
    eid = "11111111-1111-1111-1111-111111111111"
    assert await claim_event(conn, eid) is True  # جديد ⇒ أوّل مطالبة
    assert await claim_event(conn, eid) is False  # مُعاد ⇒ عولِج سابقاً
    assert conn.claims == [eid, eid]
    assert eid in conn._processed


@pytest.mark.asyncio
async def test_claim_event_uses_consumer_name():
    conn = FakeConn()
    # المُستهلِك الافتراضيّ = relay الـoutbox (يُمرَّر إلى consumer العمود).
    assert await claim_event(conn, "22222222-2222-2222-2222-222222222222") is True
    assert OUTBOX_CONSUMER_NAME == "outbox_relay"


# ─── 3. _send_one: حدث جديد يُنشَر؛ مُعاد يُتخطّى (لا أثر مزدوج) ───


def _worker_with_capture():
    published: list[tuple] = []

    async def _publish(subject: str, payload: bytes) -> None:
        published.append((subject, payload))

    worker = OutboxWorker(pool=None, nats_publish_fn=_publish)
    return worker, published


@pytest.mark.asyncio
async def test_send_one_new_event_publishes_and_marks_sent():
    worker, published = _worker_with_capture()
    conn = FakeConn()
    eid = "33333333-3333-3333-3333-333333333333"

    await worker._send_one(conn, _row(eid, outbox_id=7))

    assert len(published) == 1  # نُشِر مرّةً
    assert ("sent", 7) in conn.updates  # وُسِم 'sent'
    assert eid in conn._processed  # طُولِب


@pytest.mark.asyncio
async def test_send_one_duplicate_event_skips_publish_no_double_side_effect():
    """إعادة تسليم نفس event_id ⇒ يُطبَّق الأثر (النشر) مرّةً واحدة فقط."""
    worker, published = _worker_with_capture()
    conn = FakeConn()
    eid = "44444444-4444-4444-4444-444444444444"

    # التسليم الأوّل: يُنشَر.
    await worker._send_one(conn, _row(eid, outbox_id=1))
    # إعادة تسليم (نفس الحدث، صفّ outbox آخر): يُتخطّى النشر، يُجرَّد بوسمه 'sent'.
    await worker._send_one(conn, _row(eid, outbox_id=2))

    assert len(published) == 1, "أثر جانبيّ مزدوج: نُشِر الحدث المُعاد مرّةً ثانية"
    # كلا الصفّين وُسِما 'sent' (الأوّل بالنشر، الثاني بالتخطّي) — لا إعادة محاولة عبثيّة.
    assert ("sent", 1) in conn.updates
    assert ("sent", 2) in conn.updates


# ─── 4. ذرّيّة: فشل النشر ⇒ تُلغى المطالبة (لا «معالَج» بلا نشر) ───


@pytest.mark.asyncio
async def test_send_one_publish_failure_rolls_back_claim_atomic():
    """تعطّل بعد المطالبة قبل اكتمال النشر ⇒ تُرجَع المطالبة (SAVEPOINT) ⇒ يُعاد لاحقاً.

    لولا الذرّيّة لبقي الحدث «معالَجاً» في processed_events رغم فشل نشره ⇒ يُبتلَع للأبد.
    """
    published: list = []

    async def _failing_publish(subject: str, payload: bytes) -> None:
        published.append((subject, payload))
        raise RuntimeError("NATS down")

    worker = OutboxWorker(pool=None, nats_publish_fn=_failing_publish)
    conn = FakeConn()
    eid = "55555555-5555-5555-5555-555555555555"

    await worker._send_one(conn, _row(eid, outbox_id=9, retry_count=0))

    # المطالبة أُلغيت بتراجع SAVEPOINT ⇒ الحدث غير «معالَج» (سيُعاد في دورة لاحقة).
    assert eid not in conn._processed, "المطالبة لم تُلغَ رغم فشل النشر (لا ذرّيّة)"
    # تتبّع المحاولة سُجِّل (retry) خارج SAVEPOINT ⇒ مُثبَّت (لا يُتراجَع عنه).
    assert ("retry", 9) in conn.updates
    # ولم يُوسَم 'sent' (فشل فعليّ).
    assert ("sent", 9) not in conn.updates


@pytest.mark.asyncio
async def test_send_one_retry_after_failure_can_reclaim_and_publish():
    """بعد فشل نشر (تراجعت مطالبته)، إعادة المحاولة تُطالِب من جديد وتُنشَر — لا ابتلاع."""
    published: list = []
    fail_first = {"n": 0}

    async def _flaky_publish(subject: str, payload: bytes) -> None:
        fail_first["n"] += 1
        published.append(subject)
        if fail_first["n"] == 1:
            raise RuntimeError("transient NATS error")

    worker = OutboxWorker(pool=None, nats_publish_fn=_flaky_publish)
    conn = FakeConn()
    eid = "66666666-6666-6666-6666-666666666666"

    await worker._send_one(conn, _row(eid, outbox_id=3, retry_count=0))  # يفشل
    assert eid not in conn._processed  # المطالبة تراجعت
    await worker._send_one(conn, _row(eid, outbox_id=3, retry_count=1))  # ينجح

    assert eid in conn._processed  # طُولِب نهائيّاً
    assert ("sent", 3) in conn.updates  # وُسِم 'sent' بعد النجاح
    assert fail_first["n"] == 2  # حُوول مرّتين (فشل ثمّ نجح) — لا ابتلاع
