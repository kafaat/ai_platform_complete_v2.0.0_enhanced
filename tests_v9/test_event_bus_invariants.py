"""حُرّاس ثوابت ناقل الأحداث: الـidempotency متعدّد الطبقات + الترتيب + سلامة الـoutbox.

فحص عميق للمحور B (Event Bus / Replay / Idempotency). التحقّق أظهر أنّ النظام **سليم
ومُطبَّق بطبقات صحيحة**، لا فجوة منطقيّة. هذه الحُرّاس تُثبّت تلك الضمانات كبوّابة CI كي لا
ينحدر أحدها صامتاً في إعادة هيكلة مستقبليّة (نفس فلسفة حارس RLS):

  1. idempotency الأوامر: commands.command_id PRIMARY KEY + ON CONFLICT DO NOTHING
     (أمر مُعاد بنفس المعرّف ⇒ يُحجب قبل أيّ إصدار حدث).
  2. dedup الأحداث: فهرس فريد على dedup_key + ON CONFLICT DO NOTHING في emit_event.
  3. سلامة الـoutbox: FOR UPDATE SKIP LOCKED (لا إرسال مزدوج بين عمّال) + تراجع أسّيّ.
     النشر ثمّ وسم 'sent' داخل معاملة واحدة ⇒ at-least-once بلا فقدان.
  4. ترتيب حتميّ: (occurred_at, seq) كاسرَ تعادل (seq من v63).

حُرّاس مصدر/هجرة — تُنفَّذ في CI بلا قاعدة.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── 1. idempotency الأوامر (الطبقة العليا) ──
def test_commands_table_pk_idempotency():
    sql = _read("migrations/v10_command_store_lifecycle.sql")
    assert "command_id      UUID PRIMARY KEY" in sql or "command_id UUID PRIMARY KEY" in sql, (
        "commands.command_id يجب أن يكون PRIMARY KEY (idempotency الأوامر)"
    )


def test_command_store_on_conflict_do_nothing():
    src = _read("services/sahool-platform/api/command_store.py")
    assert "ON CONFLICT (command_id) DO NOTHING" in src, (
        "store() لا يحجب الأمر المُعاد (idempotency مفقودة على مستوى الأمر)"
    )
    assert "was_duplicate" in src, "store() لا يُبلّغ عن الأمر المُكرَّر"


# ── 2. dedup الأحداث (الطبقة الثانية) ──
def test_events_dedup_unique_index_and_conflict():
    sql = _read("migrations/v11_events_bus.sql")
    assert "CREATE UNIQUE INDEX" in sql and "ux_events_dedup" in sql, "فهرس dedup الفريد مفقود"
    assert "ON events(dedup_key)" in sql.replace(" ", "") or "ON events(dedup_key)" in sql, (
        "فهرس dedup ليس على dedup_key"
    )
    assert "ON CONFLICT (dedup_key)" in sql and "DO NOTHING" in sql, (
        "emit_event لا يحجب الحدث المُكرَّر على dedup_key"
    )


def test_dedup_key_composition():
    sql = _read("migrations/v11_events_bus.sql")
    # dedup_key = tenant : event_type : entity_id : payload_hash : date
    for part in ("p_tenant_id", "p_event_type", "p_entity_id", "v_payload_hash"):
        assert part in sql, f"dedup_key لا يتضمّن {part}"
    assert "digest(" in sql and "sha256" in sql, "payload_hash ليس SHA-256 حتميّاً"


# ── 3. سلامة الـoutbox (at-least-once، لا إرسال مزدوج) ──
def test_outbox_skip_locked_and_backoff():
    src = _read("services/sahool-platform/api/event_bus.py")
    assert "FOR UPDATE OF o SKIP LOCKED" in src, (
        "الـoutbox لا يستعمل SKIP LOCKED ⇒ خطر إرسال مزدوج بين العمّال"
    )
    assert "make_interval" in src and "power(2" in src, "لا تراجع أسّيّ للمحاولات الفاشلة"
    assert "retry_count < $1" in src, "لا حدّ أقصى للمحاولات (dead-letter)"


def test_outbox_publish_then_mark_sent():
    src = _read("services/sahool-platform/api/event_bus.py")
    # النشر يسبق وسم 'sent' (at-least-once: فشل بعد النشر ⇒ إعادة إرسال لا فقدان)
    pub = src.index("await self.publish(")
    sent = src.index("status = 'sent'", pub)
    assert pub < sent, "وسم 'sent' يجب أن يلي النشر (at-least-once، لا فقدان)"


# ── 3b. استهلاك مُتعاضد (processed_events، at-most-once) ──
def test_processed_events_dedup_table_present():
    sql = _read("migrations/v93_processed_events.sql")
    assert "CREATE TABLE IF NOT EXISTS processed_events" in sql, "جدول processed_events مفقود"
    assert "event_id     UUID         PRIMARY KEY" in sql or "event_id UUID PRIMARY KEY" in sql, (
        "processed_events.event_id ليس PRIMARY KEY (مفتاح التعاضُد)"
    )
    # عالميّ عمداً: لا عمود tenant_id (مُستهلِك عابر للمستأجرين على sahool_jobs/BYPASSRLS).
    # نفحص جسم الـCREATE TABLE فقط (لا التعليقات/الـCOMMENT التي تشرح غياب tenant_id قصداً).
    import re

    body = re.search(r"CREATE TABLE[^(]*\((.*?)\)\s*;", sql, re.S).group(1)
    assert not re.search(r"\btenant_id\b", body), (
        "processed_events جدول بنية تحتيّة عالميّ — لا يجب أن يحوي عمود tenant_id"
    )


def test_processed_events_in_manifest_order():
    manifest = _read("migrations/MANIFEST.txt")
    assert "v93_processed_events.sql" in manifest, "v93 غير مُدرَج في MANIFEST (لن يُطبَّق)"


def test_consumer_asks_before_the_side_effect_and_claims_after_it():
    """التعاضُد محفوظٌ بوسيلتين، والنشرُ خارج كلّ معاملة.

    **كان هذا الاختبار يُثبِّت العطلَ نفسَه.** نصُّه السابق اشترط
    ``claim_event`` **قبل** ``publish`` و**كليهما داخل** ``conn.transaction()`` —
    أي معاملةٌ مفتوحةٌ أثناء I/O شبكيّ، وهو بعينه ما يصفه
    `WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01` عطلاً: قفلُ الصفّ واتّصالُ المسبح
    محتجزان حتّى يردّ الوسيط، فتباطؤُه يصير تعطّلَ العامل. فالشرطُ القديم كان
    **بوّابةً لا تُغلَق بعملٍ صحيح**، وأُعيدت صياغتُه على العقد الجديد لا حُذِف.

    **والخاصّيّتان اللتان حماهما الشرطُ القديم محفوظتان، كلٌّ بوسيلتها:**

      • لا أثرَ مزدوج ⇒ فحصٌ **قرائيّ** (`event_already_claimed`) قبل النشر.
      • لا «مُعالَجٌ بلا نشر» ⇒ كتابةُ المطالبة (`claim_event`) **بعد** النشر.

    وهما مقيستان سلوكيّاً لا نصّيّاً في ``test_outbox_idempotent_consumption.py``؛
    وما يُقاس هنا هو الترتيبُ الذي لا يراه اختبارٌ سلوكيّ بـconn زائف: **ألّا يقع
    النشرُ داخل معاملة**.
    """
    src = _read("services/sahool-platform/api/event_bus.py")
    # المطالبة عبر ON CONFLICT DO NOTHING (idempotency key) — لم تتغيّر.
    assert "INSERT INTO processed_events" in src, "لا مطالبة عبر processed_events"
    assert "ON CONFLICT (event_id) DO NOTHING" in src, "المطالبة ليست idempotent"

    # السؤالُ قبل الأثر، والادّعاءُ بعده.
    ask = src.index("await event_already_claimed(conn, row[")
    pub = src.index("await self.publish(row[", ask)
    claim = src.index("await claim_event(conn, row[", pub)
    assert ask < pub < claim, (
        "الترتيب المطلوب: فحصٌ قرائيّ ⇒ نشر ⇒ كتابةُ مطالبة. "
        "المطالبةُ قبل النشر تبتلع حدثاً يفشل نشرُه؛ وبلا فحصٍ قبله يُنشَر المُعاد مرّتين."
    )

    # **النشرُ خارج كلّ معاملة**: آخِرُ فتحِ معاملةٍ قبل سطر النشر يجب أن يكون مُغلَقاً
    # — نقيسه بأنّ سطر النشر أقلُّ إزاحةً من جسم تلك المعاملة (خرج من كتلتها).
    tx = src.rindex("async with conn.transaction():", 0, pub)
    tx_indent = len(src[:tx].rsplit("\n", 1)[-1])
    pub_indent = len(src[:pub].rsplit("\n", 1)[-1])
    assert pub_indent <= tx_indent, (
        "النشرُ داخل كتلة معاملة — قفلُ الصفّ واتّصالُ المسبح محتجزان أثناء I/O "
        "(WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01)"
    )


# ── 4. ترتيب حتميّ ──
def test_deterministic_ordering():
    src = _read("services/sahool-platform/api/event_bus.py")
    assert "ORDER BY occurred_at ASC, seq ASC" in src, (
        "تاريخ الكيان ليس مرتّباً حتميّاً (occurred_at, seq)"
    )
    replay = _read("services/sahool-platform/api/event_replay.py")
    assert "seq" in replay and "occurred_at" in replay, "إعادة التشغيل لا تستعمل الترتيب الحتميّ"
