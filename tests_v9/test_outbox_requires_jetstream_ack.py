"""`OUTBOX-RELAY-MARKS-SENT-WITHOUT-JETSTREAM-ACK-01` — شواهدُ عقد التسليم.

**العطلُ مقيسٌ لا مفترَض** (stack معزول، 2026-09-20): حدثٌ نُشِر إلى subject لا يغطّيه
أيُّ stream صار صفُّه `sent` بـ`last_error=NULL` ومحاولةً `published` — **ولم تُخزَّن
الرسالة**. أي أنّ `sent` كانت تعني «سُلِّمت إلى المقبس» لا «صارت دائمة».

**والسببُ موضعُ سطرٍ واحد:** الناشرُ المحقون في `_start_outbox_worker` كان
`_NATS_CONN.publish` — **Core NATS**: إطلاقٌ بلا إقرار ينجح ما دام الاتّصالُ قائماً،
وُجِد دفقٌ أم لا.

**وهذه الشواهدُ لا تُعيد فحصَ `OutboxWorker`** — بنيتُه سليمةٌ أصلاً (ينشر ثمّ يَسِم
داخل معاملة، والاستثناءُ يُعيد الصفَّ `pending/failed`). تحرس **الخاصّيّةَ** التي كان
العطلُ يخرقها: أنّ الوسمَ `sent` يلزمه **إقرارُ تخزين**، وأنّ غيابَه يُبقي الحدثَ
قابلاً لإعادة التسليم بخطأ مكتوب — لا أن يُبتلَع صامتاً.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services" / "sahool-platform" / "api" / "main.py"
EVENT_BUS = ROOT / "services" / "sahool-platform" / "api" / "event_bus.py"
BROKER = ROOT / "shared" / "broker_url.py"


def _event_bus():
    """يُستورَد **عضواً في حزمته** لا بمسارٍ مفرد.

    `event_bus.py` يحمل `from .feature_registry import is_enabled`، فتحميلُه بمسارٍ
    مفرد يرفع `ImportError` — وهو عطلُ **مِرقاة** لا عطلُ شيفرة. وابتلاعُه بـ`skip`
    كان سيُنتِج شاهداً يُقرأ ضماناً وهو لا يعمل، فيُسجَّل تغطيةً لا يملكها.
    """
    platform = (ROOT / "services" / "sahool-platform").as_posix()
    if platform not in sys.path:
        sys.path.insert(0, platform)
    import importlib

    return importlib.import_module("api.event_bus")


# ── الخاصّيّة الأولى: الناشرُ المحقون يمرّ بـJetStream ويشترط الإقرار ──────────────


def _bootstrap() -> str:
    """جسمُ `_start_outbox_worker` وحدَه — لا نصُّ الملفّ كلُّه.

    مسحُ الملفّ كاملاً كان يلتقط أيَّ ذكرٍ عابرٍ في تعليق، وهو
    `SCANNER-COUNTS-A-PATH-LITERAL-AS-A-USAGE-01` المُسجَّل في هذا المستودع.
    """
    source = MAIN.read_text(encoding="utf-8")
    return source[
        source.index("async def _start_outbox_worker") : source.index(
            "async def _stop_outbox_worker"
        )
    ]


def _publisher_factory() -> str:
    """جسمُ `make_jetstream_publisher` في `shared/broker_url.py` — موضعُه القانونيّ.

    **اختارته بوّابتان لا الراحة:** `main.py` بلا هامشِ أسطر، و`api/event_bus.py`
    **مسارٌ مجمَّد خلف GATE-01** يحتاج تفويضَ مالكٍ لمرّةٍ واحدة. وهذا الملفُّ ينصّ
    على أنّ شؤون الوسيط «تُكتَب مرّةً واحدة هنا».
    """
    source = BROKER.read_text(encoding="utf-8")
    return source[source.index("def make_jetstream_publisher") :]


def test_the_injected_publisher_is_not_core_nats_fire_and_forget():
    """**counterexample الخطوة ⑤ بعينه، مقروءاً من المصدر.**

    `nats_conn.publish` ينجح بلا دفق. فوجودُه ناشراً للصندوق الصادر **هو** العطل،
    لا عَرَضٌ له. ويُفحَص **الموضعان**: مُهيّئ التطبيق الذي يحقن، ومصنعُ الناشر الذي
    يملك العقد — فلا يعود أحدُهما إلى Core NATS بينما الآخرُ يبدو سليماً.
    """
    bootstrap, factory = _bootstrap(), _publisher_factory()

    assert "_NATS_CONN.publish(" not in bootstrap, (
        "ناشرُ الصندوق الصادر عاد إلى Core NATS — إطلاقٌ بلا إقرار، "
        "فيصير `sent` يعني «سُلِّم إلى المقبس» لا «صار دائماً»."
    )
    assert "make_jetstream_publisher(" in bootstrap, "المُهيّئ لا يحقن الناشرَ المُقِرّ"
    # والعقدُ لا يعود إلى المسار المجمَّد: تعديلُه يحتاج تفويضَ GATE-01، فسكناه هناك
    # يجعل كلَّ لمسةٍ لاحقةٍ له تحتاج قرارَ مالك.
    assert "make_jetstream_publisher" not in EVENT_BUS.read_text(encoding="utf-8"), (
        "عقدُ النشر عاد إلى `event_bus.py` المجمَّد خلف GATE-01"
    )
    assert "nats_conn.publish(" not in factory, "المصنعُ نفسُه يُطلِق بلا إقرار"
    assert ".jetstream()" in factory, "لا سياقَ JetStream في مصنع الناشر"
    assert "await jetstream.publish(" in factory, "النشرُ لا يمرّ بـJetStream"


def test_the_publisher_refuses_an_acknowledgement_that_proves_nothing():
    """إقرارٌ بلا تسلسلٍ ليس إقراراً — وبدونه يعود `sent` يعني «لم يُرفَع استثناء».

    وعميلٌ يُرجِع `None` (أو إقراراً فارغاً) يجعل `await` ينجح صامتاً، فيمرّ الوسم.
    """
    factory = _publisher_factory()
    assert "JETSTREAM_PUBACK_MISSING" in factory, "لا يُفحَص الإقرارُ بعد النشر"
    assert "ack is None" in factory


# ── الخاصّيّة الثانية: غيابُ الإقرار يُبقي الحدثَ معلَّقاً بخطأ مكتوب ──────────────


class _Conn:
    """اتّصالٌ صغيرٌ يسجّل ما نُفِّذ — لا محاكاةُ قاعدةٍ بل رصدُ الجُمَل الصادرة."""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.args: list[tuple] = []

    async def execute(self, sql: str, *args):
        self.statements.append(" ".join(sql.split()))
        self.args.append(args)

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Txn()


@pytest.mark.asyncio
async def test_a_publisher_without_an_ack_never_lets_a_row_reach_sent(monkeypatch):
    """**الخاصّيّةُ التي خرقها العطل، مقيسةً على الشيفرة لا موصوفة.**

    ناشرٌ يرفع (كما يفعل `NoStreamResponseError` حين لا يغطّي المسارَ دفق) يجب أن
    يُخرِج الصفَّ من `sent` كلّيّاً: `pending/failed` بـ`last_error` ومحاولةً فاشلة.
    """
    bus = _event_bus()
    monkeypatch.setattr(bus, "claim_event", _always_claims, raising=False)

    async def _refusing_publish(subject: str, payload: bytes) -> None:
        raise RuntimeError("nats: no response from stream")

    worker = bus.OutboxWorker(pool=None, nats_publish_fn=_refusing_publish)
    conn = _Conn()
    await worker._send_one(conn, _row())

    joined = " | ".join(conn.statements)
    assert "SET status = 'sent'" not in joined, "وُسِم `sent` بلا إقرارِ تخزين — وهو العطلُ بعينه"
    assert "last_error = $2" in joined, "سقط الخطأُ فلا يُقرأ سببُ عدم التسليم"
    assert any("delivery" in s.lower() or "attempt" in s.lower() for s in conn.statements)


@pytest.mark.asyncio
async def test_a_publisher_with_an_ack_does_mark_sent(monkeypatch):
    """**الشاهدُ الإيجابيّ: العلاجُ المشروع يمرّ.**

    بلا هذا يصير الشرطُ «بوّابةً لا تُغلَق بعملٍ صحيح» — أي لا يمكن لحدثٍ أن يُسلَّم
    أبداً، وهو عطلٌ آخرُ بثوب التشديد.
    """
    bus = _event_bus()
    monkeypatch.setattr(bus, "claim_event", _always_claims, raising=False)

    async def _acking_publish(subject: str, payload: bytes) -> None:
        return None  # نجاحٌ بلا استثناء = إقرارٌ تمّ فحصُه في الناشر نفسِه

    worker = bus.OutboxWorker(pool=None, nats_publish_fn=_acking_publish)
    conn = _Conn()
    await worker._send_one(conn, _row())

    joined = " | ".join(conn.statements)
    assert "SET status = 'sent'" in joined, "حدثٌ مُقَرٌّ لم يُوسَم — البوّابةُ لا تُغلَق بعملٍ صحيح"


# ── مِرقاةٌ صغيرة ────────────────────────────────────────────────────────────────


async def _always_claims(conn, event_id):
    return True


def _row() -> dict:
    from datetime import UTC, datetime
    from uuid import uuid4

    return {
        "outbox_id": 1,
        "event_id": uuid4(),
        "event_type": "soil.observation.recorded",
        "entity_type": "observation",
        "entity_id": uuid4(),
        "tenant_id": uuid4(),
        "payload": {"value": 1},
        "occurred_at": datetime.now(UTC),
        "retry_count": 0,
        "nats_subject": "sahool.soil.observation.recorded",
    }
