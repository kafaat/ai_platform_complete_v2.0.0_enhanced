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

import re
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
