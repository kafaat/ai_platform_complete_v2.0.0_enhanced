"""`WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01` — الصندوقُ الصادر: الشبكةُ خارج المعاملة.

**العطلُ الذي وُجِدت هذه الشواهدُ لأجله، بنصّ الشيفرة السابقة:** `_process_batch` كان
يلفّ الدُّفعةَ كلَّها في معاملةٍ صريحة «كي تبقى أقفال FOR UPDATE SKIP LOCKED محتجَزة
حتى تحديث الحالة» — أي **أقفالُ صفوفٍ واتّصالُ مسبحٍ محتجَزان أثناء النشر على الشبكة**.
تباطؤُ الوسيط يتحوّل عندئذٍ إلى تعطّلِ العامل ومسبحِه معاً.

والنمطُ البديل مُطبَّقٌ ومُثبَتٌ حيّاً في هذا المستودع (`v228` على
`runtime_event_outbox`): TX-1 إجارةٌ تُثبَّت بـcommit · الشبكةُ خارجها · TX-2 إنهاءٌ
بـCAS على `claim_token`. **و`event_outbox` لم يكن ضمن جداول `v228`** — فأُضيف له
`v233`، وهذه الشواهدُ تحرس الخاصّيّةَ لا الصياغة.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
BUS = ROOT / "services/sahool-platform/api/event_bus.py"
MIGRATION = ROOT / "migrations/v233_event_outbox_claim_lease.sql"
MANIFEST = ROOT / "migrations/MANIFEST.txt"


def _code_lines(body: str) -> list[str]:
    """أسطرُ الشيفرة وحدَها — بلا تعليقاتٍ ولا سلسلةِ توثيق.

    **عطلٌ وقع في هذا الملفّ نفسِه:** أوّلُ صياغةٍ طابقت `conn.transaction()` الواردةَ
    في **docstring** يصف التصميمَ القديم، فقرأت وصفاً بنيةً — وهو
    `SCANNER-COUNTS-A-PATH-LITERAL-AS-A-USAGE-01` بعينه.
    """
    out, in_doc = [], False
    for ln in body.splitlines():
        stripped = ln.strip()
        if stripped.count('"""') == 1:
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#") or not stripped:
            continue
        out.append(ln)
    return out


def _block_ended(lines: list[str], open_idx: int) -> int:
    """فهرسُ أوّل سطرٍ يعود إلى إزاحة الكتلة أو أقلّ — أي حيث أُغلِقت."""
    indent = len(lines[open_idx]) - len(lines[open_idx].lstrip())
    for i in range(open_idx + 1, len(lines)):
        if len(lines[i]) - len(lines[i].lstrip()) <= indent:
            return i
    return len(lines)


def _body(name: str) -> str:
    """جسمُ دالّةٍ بعينها — لا نصُّ الملفّ كلُّه.

    مسحُ الملفّ كاملاً يلتقط أيَّ ذكرٍ عابرٍ في تعليق، وهو
    `SCANNER-COUNTS-A-PATH-LITERAL-AS-A-USAGE-01` المُسجَّل هنا.
    """
    source = BUS.read_text(encoding="utf-8")
    start = source.index(f"    async def {name}(")
    nxt = source.index("\n    async def ", start + 10)
    return source[start:nxt]


def test_the_publish_call_is_not_inside_a_transaction_block():
    """**الخاصّيّةُ التي خرقها العطل، مقروءةً من البنية لا موصوفة.**

    يُقاس عمقُ الإزاحة: نداءُ النشر يجب ألّا يقع تحت `async with conn.transaction()`.
    """
    lines = _code_lines(_body("_send_one"))
    publish_idx = next(i for i, ln in enumerate(lines) if "await self.publish(" in ln)
    for i, ln in enumerate(lines[:publish_idx]):
        if "conn.transaction()" in ln:
            assert _block_ended(lines, i) <= publish_idx, (
                "النشرُ يقع داخل معاملةٍ مفتوحة — أقفالُ الصفوف محتجَزةٌ أثناء I/O"
            )


def test_the_batch_closes_its_transaction_before_sending():
    """حلقةُ الإرسال خارج كتلة المعاملة في `_process_batch` — لا مجرّد داخل دالّةٍ أخرى."""
    lines = _code_lines(_body("_process_batch"))
    send_idx = next(i for i, ln in enumerate(lines) if "await self._send_one(" in ln)
    txn_idx = [i for i, ln in enumerate(lines[:send_idx]) if "conn.transaction()" in ln]
    assert txn_idx, "المقدّمة: توجد معاملةٌ في الدُّفعة"
    assert _block_ended(lines, txn_idx[-1]) <= send_idx, "الإرسالُ ما زال داخل معاملة الدُّفعة"


def test_the_claim_is_pinned_by_a_committed_token_not_by_a_row_lock():
    """المطالبةُ تُثبَّت **بالبيانات**: رمزٌ يُكتَب في TX-1 قبل إغلاقها."""
    body = _body("_process_batch")
    assert "claim_token = $1" in body, "لا رمزَ يُكتَب — المطالبةُ ما زالت بالقفل وحدَه"
    assert "lease_until = NOW() + make_interval" in body, "لا إجارةَ زمنيّة"
    assert "uuid.uuid4()" in body


def test_an_expired_lease_is_recapturable_but_a_stale_finisher_cannot_write():
    """**السببُ الذي يجعل الحالةَ وحدَها غيرَ كافية.**

    الالتقاطُ يشترط انقضاءَ الإجارة، والإنهاءُ يشترط **الرمزَ نفسَه** — فعاملٌ فقد
    إجارتَه أثناء النشر لا يسم صفّاً صار لغيره.
    """
    batch = _body("_process_batch")
    assert "o.lease_until IS NULL OR o.lease_until <= NOW()" in batch, (
        "الالتقاطُ لا يحترم إجارةً قائمة"
    )
    # **مسارُ الإنهاء يمتدّ إلى دالّتين** منذ أن وُحِّد وسمُ `'sent'` في
    # `_mark_sent_if_lease_held` (التكرارُ كان يُعمي مرساةَ الطفرة). فالنطاقُ
    # المقيس هو المسارُ كلُّه لا دالّةٌ بعينها — وإلّا قاس الاختبارُ **موضعَ**
    # الشيفرة بدل **خاصّيّتها**، فيحمرّ على إعادة تنظيمٍ لا تغيّر شيئاً.
    # **ولا يُذكَر نصُّ الشرط في أيّ نثرٍ داخل هذين الجسمين.** قِيس أنّ ذكرَه يُبطِل
    # التكذيب: طفرةٌ تُزيل الشرطَ من الـSQL بقيت **حيّة** لأنّ نصَّه كان مكتوباً في
    # docstring الدالّة المساعِدة، فأبقى العدَّ عند ٢. وشاهدٌ يقرأ نثرَه عن نفسِه
    # يُثبِت وجودَ النثر لا وجودَ القاعدة. (وتجريدُ الـdocstrings هنا لا يصلح: نصُّ
    # الـSQL نفسُه سلسلةٌ ثلاثيّةُ الاقتباس، فيسقط مع ما يُجرَّد.)
    finish = _body("_send_one") + _body("_mark_sent_if_lease_held")
    assert finish.count("claim_token IS NOT DISTINCT FROM") >= 2, (
        "الإنهاءُ أو تسجيلُ الفشل بلا CAS على الرمز — يكتب فوق عاملٍ آخر"
    )


def test_losing_the_lease_is_reported_not_swallowed():
    """صمتٌ عند فقد الإجارة يُخفي سبباً حقيقيّاً لتكرار النشر."""
    finish = _body("_send_one") + _body("_mark_sent_if_lease_held")
    assert "lease lost before finish" in finish
    assert "logger.warning" in finish


def test_the_migration_is_additive_and_backward_compatible():
    """**شرطُ ترتيبٍ لازم:** خدمةُ المهاجرات تتبع `main`، فقد تصل المهاجرةُ قبل الشيفرة.

    أعمدةٌ قابلةٌ للإفراغ بلا `NOT NULL` ولا `DEFAULT` ⇒ النسخةُ القديمة تعمل كما كانت.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS claim_token UUID" in sql
    assert "ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ" in sql
    assert not re.search(r"ADD COLUMN[^;]*NOT NULL", sql), "عمودٌ إلزاميّ يكسر النسخةَ القديمة"
    assert "DROP " not in sql.upper(), "المهاجرةُ تحذف شيئاً — ليست إضافيّة"


def test_the_migration_is_registered_before_the_final_hardening():
    """مهاجرةٌ غيرُ مُسجَّلةٍ لا تعمل؛ وتسجيلُها بعد التشديد النهائيّ يقلب الترتيب."""
    manifest = MANIFEST.read_text(encoding="utf-8").splitlines()
    entries = [ln.strip() for ln in manifest if ln.strip().endswith(".sql")]
    assert "v233_event_outbox_claim_lease.sql" in entries, "المهاجرةُ غيرُ مُسجَّلة"
    assert entries.index("v233_event_outbox_claim_lease.sql") < entries.index(
        "v206_rls_final_hardening.sql"
    ), "سُجِّلت بعد التشديد النهائيّ"


# ── شاهدٌ لا يتأثّر بالنثر: يُقرَأ ما يُمرَّر إلى واجهة الاتّصال، لا نصُّ الملفّ ──────


class _SqlSpy:
    """اتّصالٌ زائف يسجّل ما **يُمرَّر إلى `execute`**: الجملةَ ووسائطَها.

    **تسميةٌ دقيقةٌ عن قصد:** هذا ليس «الـSQL المُنفَّذ في القاعدة» — لا قاعدةَ هنا.
    المقيسُ ما يُصدِره مسارُ الإنتاج إلى واجهة الاتّصال. والفرقُ ليس لفظيّاً: جملةٌ
    صحيحةُ النصّ قد يرفضها PostgreSQL أو تُنفَّذ بدلالةٍ غير المقصودة، وهذا الشاهدُ
    لا يقول شيئاً عن ذلك.

    **ولمَ هو إلى جانب الشاهد البنيويّ:** البنيويُّ يعدّ وروداتِ شرطِ الـCAS في نصّ
    الدالّتين، فبقاؤه صحيحاً مشروطٌ بألّا يذكر أحدٌ الشرطَ في تعليقٍ أو توثيق — وذلك
    **قيدٌ على الكاتب لا خاصّيّةٌ في الشيفرة**، وقد أبطل التكذيبَ فعلاً مرّةً (طفرةٌ
    أزالت الشرطَ من الـSQL فبقي العدُّ صحيحاً بنصّ الـdocstring). هذا يقرأ ما أُرسِل،
    فتعليقٌ جديدٌ لا يُغيّر نتيجتَه بحال.

    **وحدُّه مُعلَن:** يُثبِت أنّ الشرطَ **أُرسِل بالوسيط الصحيح**، لا أنّ PostgreSQL
    رفض كتابةَ عاملٍ قديم تحت تزامن. والبرهانُ الحيُّ قائمٌ في موضعه لا هنا:
    `OUTBOX-LEASE-HAS-NO-LIVE-TWO-WORKER-PROOF-01` صار `verified` بعاملَين متزامنَين
    على PostgreSQL وNATS حقيقيَّين، وشاهدُ العامل القديم عند CAS=0 في #1076. فهذا
    الشاهدُ **مُكمِّلٌ رخيص** يعمل في كلّ جولة وحدات، لا بديلٌ عن ذلك البرهان.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, *args) -> str:
        self.calls.append((" ".join(sql.split()), args))
        return "UPDATE 1"

    async def fetchval(self, sql: str, *args):
        return False  # لم يُطالَب بعد ⇒ المسارُ المقيس هو النشر ثمّ الوسم

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Txn()


_SPY_OUTBOX_ID = 41
_SPY_TOKEN = "tok-of-this-attempt"


def _row_for_spy() -> dict:
    return {
        "outbox_id": _SPY_OUTBOX_ID,
        "event_id": "66666666-6666-6666-6666-666666666666",
        "nats_subject": "sahool.events.test",
        "retry_count": 0,
        "event_type": "field.created",
        "entity_type": "field",
        "entity_id": "f-1",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "payload": {"k": "v"},
        "occurred_at": None,
    }


def _worker(*, failing: bool):
    import sys

    platform = str(ROOT / "services" / "sahool-platform")
    if platform not in sys.path:
        sys.path.insert(0, platform)
    from api.event_bus import OutboxWorker

    async def _publish(subject: str, payload: bytes) -> None:
        if failing:
            raise RuntimeError("NATS down")

    return OutboxWorker(pool=None, nats_publish_fn=_publish)


def _assert_guarded_by_the_attempt_token(sql: str, args: tuple) -> None:
    """الشرطُ موجودٌ **ومربوطٌ بالقيم الصحيحة** — لا مجرّد اسمٍ في النصّ.

    اسمُ العمود قد يرد في `SET claim_token = NULL` وفي تعليق؛ فالمقيسُ هنا أنّ
    `WHERE` يحمل الشرطَ، وأنّ الوسيطَين المربوطَين بـ`outbox_id` وبالرمز هما صفُّ
    هذه المحاولة ورمزُها بعينهما.
    """
    where = sql.split(" WHERE ", 1)
    assert len(where) == 2, f"كتابةٌ بلا WHERE: {sql}"
    assert "claim_token IS NOT DISTINCT FROM" in where[1], (
        f"شرطُ الرمز غائبٌ عن WHERE — تكتب فوق عاملٍ آخر: {sql}"
    )
    assert _arg_bound_to(sql, "outbox_id", args) == _SPY_OUTBOX_ID, (
        f"الكتابةُ لا تستهدف صفَّ هذه المحاولة: {sql} :: {args}"
    )
    assert _arg_bound_to(sql, "claim_token IS NOT DISTINCT FROM", args) == _SPY_TOKEN, (
        f"الشرطُ مربوطٌ برمزٍ غير رمزِ هذه المحاولة: {sql} :: {args}"
    )


def _arg_bound_to(sql: str, needle: str, args: tuple):
    match = re.search(re.escape(needle) + r"\s*=?\s*\$(\d+)", sql)
    assert match, f"لا ربطَ لـ{needle} في: {sql}"
    return args[int(match.group(1)) - 1]


def _outbox_writes(spy: _SqlSpy) -> list[tuple[str, tuple]]:
    return [c for c in spy.calls if c[0].startswith("UPDATE event_outbox")]


@pytest.mark.asyncio
async def test_the_success_path_sends_its_finishing_write_bound_to_the_attempt_token():
    """مسارُ النجاح: **وقعت** كتابةُ الإنهاء، وحملت الشرطَ مربوطاً بصفّها ورمزِها.

    التوكيدُ على وقوعِ الكتابة المقصودة أوّلاً مقصود: «كلُّ الكتابات مُقيَّدة» جملةٌ
    صادقةٌ على قائمةٍ فارغة — فتمرّ التجربةُ وهي لم تبلغ المسارَ أصلاً.
    """
    spy = _SqlSpy()
    await _worker(failing=False)._send_one(spy, _row_for_spy(), _SPY_TOKEN)
    writes = _outbox_writes(spy)
    finishing = [c for c in writes if "SET status = 'sent'" in c[0]]
    assert finishing, f"لم تقع كتابةُ الإنهاء أصلاً — الكتاباتُ: {[c[0] for c in writes]}"
    for sql, args in writes:
        _assert_guarded_by_the_attempt_token(sql, args)


@pytest.mark.asyncio
async def test_the_failure_path_sends_its_state_write_bound_to_the_attempt_token():
    """مسارُ الفشل يُعامَل كمسار النجاح: كتابةُ الحالة وقعت، ومقيَّدةٌ بالرمز نفسِه."""
    spy = _SqlSpy()
    await _worker(failing=True)._send_one(spy, _row_for_spy(), _SPY_TOKEN)
    writes = _outbox_writes(spy)
    failing_write = [c for c in writes if "retry_count = $1" in c[0]]
    assert failing_write, f"مسارُ الفشل لم يكتب حالةً — الكتاباتُ: {[c[0] for c in writes]}"
    assert not [c for c in writes if "SET status = 'sent'" in c[0]], "نشرٌ فاشلٌ وُسِم 'sent'"
    for sql, args in writes:
        _assert_guarded_by_the_attempt_token(sql, args)


# ── الاتّصالُ والإجارةُ أثناء الدُّفعة ─────────────────────────────────────────────
#
# `OUTBOX-BATCH-HOLDS-A-POOLED-CONNECTION-ACROSS-THE-NETWORK-01`: الحلقةُ خرجت من
# `conn.transaction()` ولم تخرج من `pool.acquire()` — فاتّصالُ المسبح محتجَزٌ طوال
# نشر الدُّفعة تسلسليّاً.
# `OUTBOX-LEASE-IS-GRANTED-TO-A-WHOLE-BATCH-BUT-SPENT-SERIALLY-01`: الإجارةُ تُمنَح
# للدُّفعة كلِّها في TX-1 وتُنفَق تسلسليّاً — فتنقضي إجارةُ آخرِ صفوفها قبل نشره.
#
# الشواهدُ سلوكيّةٌ على **قاعدةٍ زائفةٍ بساعةٍ مُتحكَّمٍ بها**: `NOW()` قيمةٌ يُقدِّمها
# الناشرُ نفسُه، فـ«نشرٌ يستغرق ٢٠ث» يُقاس بلا انتظارٍ حقيقيّ. **وحدُّها مُعلَن:** هذه
# ليست PostgreSQL — تُثبِت ما يُصدِره العاملُ ومتى يستعير اتّصالاً، لا دلالةَ الـSQL
# تحت تزامنٍ حقيقيّ (ذلك برهانُ `OUTBOX-LEASE-HAS-NO-LIVE-TWO-WORKER-PROOF-01` الحيّ).


def _bound(sql: str, needle: str, args: tuple):
    match = re.search(re.escape(needle) + r"\s*=?\s*\$(\d+)", sql)
    assert match, f"لا ربطَ لـ{needle} في: {sql}"
    return args[int(match.group(1)) - 1]


class _OutboxDb:
    """`event_outbox` + `processed_events` في الذاكرة، و`NOW()` = ``self.now`` (ثوانٍ)."""

    def __init__(self, n_rows: int) -> None:
        self.now = 0.0
        self.processed: set[str] = set()
        self.rows: dict[int, dict] = {}
        for i in range(1, n_rows + 1):
            self.rows[i] = {
                "outbox_id": i,
                "event_id": f"00000000-0000-0000-0000-{i:012d}",
                "nats_subject": "sahool.events.test",
                "retry_count": 0,
                "event_type": "field.created",
                "entity_type": "field",
                "entity_id": f"f-{i}",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "payload": {"k": i},
                "occurred_at": None,
                "status": "pending",
                "claim_token": None,
                "lease_until": None,
            }

    def _cas(self, sql: str, args: tuple) -> dict | None:
        row = self.rows.get(_bound(sql, "outbox_id", args))
        token = _bound(sql, "claim_token IS NOT DISTINCT FROM", args)
        return row if row is not None and row["claim_token"] == token else None


class _OutboxConn:
    def __init__(self, db: _OutboxDb) -> None:
        self.db = db

    async def fetch(self, sql: str, *args):
        db = self.db
        assert "FOR UPDATE OF o SKIP LOCKED" in sql, sql
        free = [
            r
            for r in db.rows.values()
            if r["status"] in ("pending", "failed")
            and r["retry_count"] < args[0]
            and (r["lease_until"] is None or r["lease_until"] <= db.now)
        ]
        return [dict(r) for r in sorted(free, key=lambda r: r["outbox_id"])[: args[1]]]

    async def fetchval(self, sql: str, *args):
        if "FROM processed_events" in sql:
            return str(args[0]) in self.db.processed
        return 1

    async def execute(self, sql: str, *args) -> str:
        db, s = self.db, " ".join(sql.split())
        if s.startswith("INSERT INTO processed_events"):
            new = str(args[0]) not in db.processed
            db.processed.add(str(args[0]))
            return f"INSERT 0 {int(new)}"
        if s.startswith("INSERT INTO outbox_delivery_attempts"):
            return "INSERT 0 1"
        assert s.startswith("UPDATE event_outbox"), s
        if "outbox_id = ANY(" in s:  # TX-1: منحُ الإجارة للدُّفعة
            for oid in args[3]:
                db.rows[oid].update(claim_token=args[0], lease_until=db.now + args[2])
            return f"UPDATE {len(args[3])}"
        row = db._cas(s, args)
        if row is None:
            return "UPDATE 0"
        if "SET status = 'sent'" in s:
            row.update(status="sent", claim_token=None, lease_until=None)
        elif "retry_count = $1" in s:
            row.update(status=args[2], retry_count=args[0], claim_token=None, lease_until=None)
        elif s.startswith("UPDATE event_outbox SET lease_until"):
            row["lease_until"] = db.now + args[0]
        else:  # pragma: no cover — كتابةٌ لا يعرفها الزائف تُرفَض لا تُبتلَع
            raise AssertionError(f"كتابةٌ غيرُ متوقَّعة: {s}")
        return "UPDATE 1"

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Txn()


class _Pool:
    """مسبحٌ بسعةٍ محدودة: `acquire` **ينتظر** حين تُستعار كلُّ اتّصالاته — كـasyncpg."""

    def __init__(self, db: _OutboxDb, capacity: int) -> None:
        self.db = db
        self._slots = asyncio.Semaphore(capacity)

    def acquire(self):
        @asynccontextmanager
        async def _lease():
            async with self._slots:
                yield _OutboxConn(self.db)

        return _lease()


def _outbox_worker(pool, publish):
    import sys

    platform = str(ROOT / "services" / "sahool-platform")
    if platform not in sys.path:
        sys.path.insert(0, platform)
    from api.event_bus import OutboxWorker

    return OutboxWorker(pool=pool, nats_publish_fn=publish)


@pytest.mark.asyncio
async def test_a_publish_in_flight_does_not_hold_the_only_pooled_connection():
    """شاهدُ الإغلاق كما سمّاه سجلُّ الفجوة: مسبحٌ سعتُه **اتّصالٌ واحد**، وناشرٌ موقوف،
    ثمّ عملٌ مستقلٌّ يستعير الاتّصالَ أثناء انتظار النشر.

    قبل الإصلاح: `_process_batch` يحتجز الاتّصالَ الوحيد عبر النشر ⇒ الاستعارةُ تنتظر
    حتّى يردّ الوسيط ⇒ مهلةُ ٠٫٥ث تنقضي. بعده: الاتّصالُ عاد إلى المسبح قبل النشر.
    """
    db = _OutboxDb(n_rows=1)
    pool = _Pool(db, capacity=1)
    publishing, release = asyncio.Event(), asyncio.Event()

    async def _held_publish(subject: str, payload: bytes) -> None:
        publishing.set()
        await release.wait()

    worker = _outbox_worker(pool, _held_publish)
    batch = asyncio.create_task(worker._process_batch())
    try:
        await asyncio.wait_for(publishing.wait(), timeout=2)

        async def _independent_work():
            async with pool.acquire() as conn:
                return await conn.fetchval("SELECT 1")

        try:
            assert await asyncio.wait_for(_independent_work(), timeout=0.5) == 1
        except TimeoutError:
            pytest.fail(
                "عملٌ مستقلٌّ لم يستعِر الاتّصالَ الوحيد خلال ٠٫٥ث بينما النشرُ موقوف — "
                "الدُّفعةُ تحتجز اتّصالَ المسبح عبر الشبكة "
                "(OUTBOX-BATCH-HOLDS-A-POOLED-CONNECTION-ACROSS-THE-NETWORK-01)"
            )
    finally:
        release.set()
        processed = await asyncio.wait_for(batch, timeout=2)
    assert processed == 1
    assert db.rows[1]["status"] == "sent", "النشرُ لم يُنهَ بعد إطلاقه"


@pytest.mark.asyncio
async def test_the_last_row_of_a_slow_batch_still_holds_its_lease_when_its_publish_starts():
    """N=5 صفوف، كلُّ نشرٍ ٢٠ث (ساعةٌ مُتحكَّمٌ بها)، `LEASE_SECONDS=60`.

    بلا تجديد: إجارةُ الدُّفعة تنقضي عند ٦٠ث ⇒ الصفّان الرابعُ (يبدأ عند ٦٠) والخامسُ
    (عند ٨٠) يبدآن نشرَهما **وإجارتُهما منقضية** — أي قابلَين لإعادة الالتقاط من عاملٍ
    آخر، بلا أن يبطؤ أيُّ نشرٍ مفرد. والمقيسُ هنا الإجارةُ **لحظةَ بدء النشر** لكلّ صفّ.
    """
    db = _OutboxDb(n_rows=5)
    started: list[tuple[int, float, float]] = []

    async def _slow_publish(subject: str, payload: bytes) -> None:
        oid = json.loads(payload)["payload"]["k"]
        started.append((oid, db.now, db.rows[oid]["lease_until"]))
        db.now += 20.0

    worker = _outbox_worker(_Pool(db, capacity=1), _slow_publish)
    assert worker.LEASE_SECONDS == 60, "المقدّمة: مدّةُ الإجارة المقيسة في الحساب"
    assert await worker._process_batch() == 5

    lapsed = [(oid, t, lease) for oid, t, lease in started if lease is None or lease <= t]
    assert [oid for oid, _, _ in started] == [1, 2, 3, 4, 5], started
    assert not lapsed, (
        f"صفوفٌ بدأ نشرُها وإجارتُها منقضية (outbox_id, now, lease_until): {lapsed} — "
        "الإجارةُ مُنِحت للدُّفعة وأُنفِقت تسلسليّاً "
        "(OUTBOX-LEASE-IS-GRANTED-TO-A-WHOLE-BATCH-BUT-SPENT-SERIALLY-01)"
    )
    assert all(r["status"] == "sent" for r in db.rows.values())


@pytest.mark.asyncio
async def test_a_row_recaptured_after_its_lease_lapsed_is_not_published_by_the_stale_worker(
    caplog,
):
    """العاملُ (أ) يلتقط صفَّين؛ نشرُ الأوّل يستغرق ٧٠ث فتنقضي إجارةُ الثاني، فيلتقطه
    عاملٌ حيٌّ (ب) **وما زال نشرُه جارياً**. حين يبلغ (أ) الصفَّ الثاني يجب ألّا ينشره —
    صار لغيره.

    **ولمَ (ب) موقوفٌ أثناء نشره:** لو أنهى (ب) نشرَه قبل أن يبلغ (أ) الصفّ لأوقفه فحصُ
    `processed_events` القرائيُّ القائم — فيمرّ الشاهدُ على الشيفرة القديمة وهو لا يقيس
    الإجارة (قِيس: هذا ما وقع في صياغته الأولى). النافذةُ الحقيقيّة هي «التقطه غيري ولم
    يُنهِه بعد»، وفيها لا يحمي إلّا الرمز.

    قبل الإصلاح كان (أ) ينشره ثمّ يكتشف فقدَ الإجارة **عند الإنهاء** فقط («lease lost
    before finish»): نشرٌ مكرَّرٌ لصفٍّ لم يعد يملكه. at-least-once يبقى الضمانة
    المُعلَنة، لكنّ العاملَ البائت لا ينشر ما يعرف أنّه فقده.
    """
    db = _OutboxDb(n_rows=2)
    pool = _Pool(db, capacity=2)
    published_by_a: list[int] = []
    published_by_b: list[int] = []
    b_publishing, b_release = asyncio.Event(), asyncio.Event()

    async def _publish_b(subject: str, payload: bytes) -> None:
        published_by_b.append(json.loads(payload)["payload"]["k"])
        b_publishing.set()
        await b_release.wait()

    worker_b = _outbox_worker(pool, _publish_b)
    tasks: list[asyncio.Task] = []

    async def _publish_a(subject: str, payload: bytes) -> None:
        oid = json.loads(payload)["payload"]["k"]
        published_by_a.append(oid)
        if oid == 1:
            db.now += 70.0  # نشرٌ بطيءٌ ينقضي أثناءه ما بقي من إجارة الدُّفعة
            tasks.append(asyncio.create_task(worker_b._process_batch()))  # (ب) حيّ
            await asyncio.wait_for(b_publishing.wait(), timeout=2)  # التقط ولم يُنهِ

    worker_a = _outbox_worker(pool, _publish_a)
    caplog.set_level("WARNING")
    try:
        await asyncio.wait_for(worker_a._process_batch(), timeout=2)
    finally:
        b_release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)

    assert published_by_a == [1], (
        f"العاملُ البائت نشر صفّاً التقطه غيرُه بعد انقضاء إجارته: {published_by_a}"
    )
    # بعد الدعوى لا قبلها: على الشيفرة القديمة يُسقِط نشرُ (أ) المكرَّرُ نشرَ (ب) عبر
    # `processed_events`، فلو سبق هذا التوكيدُ لحمرّ على المقدّمة لا على العطل.
    assert published_by_b == [1, 2], f"(ب) مالكُ الصفَّين نشرهما — {published_by_b}"
    assert "lease lost before publish" in caplog.text, caplog.text
    assert all(r["status"] == "sent" for r in db.rows.values())
