"""الحارس السابع (SCOUT-INGEST-01 / B1.2) — «نفس مفتاح، جسم مختلف ⇒ quarantine، لا سقوط صامت».

يُثبت أنّ حلّ الـdedup لا يعيد درس ``ON CONFLICT DO NOTHING`` الصامت: التعارض المتباين
حدث يُرى (quarantine بمفتاح مشتقّ)، والمطابق idempotent صادق، والجديد يُدرَج. منطق صرف.
"""

from __future__ import annotations

import pytest

from shared.contracts.ingest.dedup_resolution import (
    DIVERGENT_PAYLOAD_REASON,
    resolve_dedup,
)

pytestmark = pytest.mark.unit

_KEY = "f" * 64
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def test_no_existing_row_inserts_new() -> None:
    d = resolve_dedup(base_key=_KEY, incoming_content_hash=_HASH_A, existing_content_hash=None)
    assert d.action == "insert_new"
    assert d.storage_key == _KEY
    assert d.quarantined is False and d.quarantine_reasons == ()


def test_same_key_same_body_is_honest_idempotent_replay() -> None:
    d = resolve_dedup(base_key=_KEY, incoming_content_hash=_HASH_A, existing_content_hash=_HASH_A)
    assert d.action == "idempotent_replay"
    assert d.storage_key == _KEY  # لا تخزين مكرّر — نفس الصفّ
    assert d.quarantined is False


def test_same_key_different_body_quarantines_not_silently_dropped() -> None:
    """جوهر الحارس السابع: التعارض المتباين يُرى، لا يُبتلع."""
    d = resolve_dedup(base_key=_KEY, incoming_content_hash=_HASH_B, existing_content_hash=_HASH_A)
    assert d.action == "quarantine_divergent"
    assert d.quarantined is True
    assert d.quarantine_reasons == (DIVERGENT_PAYLOAD_REASON,)
    # يُخزَّن بمفتاح مشتقّ ⇒ لا يصطدم بالموجود ولا يُسقِطه (الخامّ القديم محفوظ):
    assert d.storage_key != _KEY
    assert d.storage_key.startswith(_KEY + "#dup-")


def test_divergent_key_is_stable_per_body_and_distinct_per_body() -> None:
    """جسم متباين واحد ⇒ مفتاح ثابت (idempotent له)؛ جسمان متباينان ⇒ مفتاحان مختلفان."""
    d1 = resolve_dedup(base_key=_KEY, incoming_content_hash=_HASH_B, existing_content_hash=_HASH_A)
    d1_again = resolve_dedup(
        base_key=_KEY, incoming_content_hash=_HASH_B, existing_content_hash=_HASH_A
    )
    d2 = resolve_dedup(base_key=_KEY, incoming_content_hash="c" * 64, existing_content_hash=_HASH_A)
    assert d1.storage_key == d1_again.storage_key  # ثابت لنفس الجسم المتباين
    assert d1.storage_key != d2.storage_key  # مختلف لجسم متباين آخر (لا اصطدام)
