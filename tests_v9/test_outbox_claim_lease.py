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
