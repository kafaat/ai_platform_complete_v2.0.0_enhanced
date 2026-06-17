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


# ── 4. ترتيب حتميّ ──
def test_deterministic_ordering():
    src = _read("services/sahool-platform/api/event_bus.py")
    assert "ORDER BY occurred_at ASC, seq ASC" in src, (
        "تاريخ الكيان ليس مرتّباً حتميّاً (occurred_at, seq)"
    )
    replay = _read("services/sahool-platform/api/event_replay.py")
    assert "seq" in replay and "occurred_at" in replay, "إعادة التشغيل لا تستعمل الترتيب الحتميّ"
