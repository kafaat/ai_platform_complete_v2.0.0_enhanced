"""حارس ساكن لـv203 — قيد البذار ضمن نطاق المشاهدة (DB-level، يُغلق فجوة تدقيق المطابقة).

المواصفة SEASON-RECORD-01 §قيود-النزاهة صرّحت «DB-level، لا تطبيقيّة فقط»؛ v201 تركت القيد 2
تطبيقيّاً (الواجهة). v203 يفرضه بـtrigger يعبر جدولين (نمط season_harvest_after_sowing). البرهان
السلوكيّ الحيّ في services/scout-ingest-service/tests/test_season_live.py (بذار خارج النطاق ⇒ 400).

وحدة صرفة — ``pytest -m unit`` (نصّ، لا قاعدة).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_MIG = (
    Path(__file__).resolve().parents[1] / "migrations" / "v203_season_sowing_in_observed_range.sql"
)


def _sql() -> str:
    return _MIG.read_text(encoding="utf-8")


def test_v203_defines_sowing_range_trigger_on_season_crop():
    sql = _sql()
    # دالّة + trigger BEFORE INSERT OR UPDATE على season_crop (يعبر جدولين ⇒ trigger لا CHECK)
    assert "FUNCTION season_crop_sowing_in_observed_range()" in sql
    assert "BEFORE INSERT OR UPDATE ON season_crop" in sql
    assert "trg_season_crop_sowing_in_range" in sql
    # يقرأ نطاق الأب من season_records ويقارن بـsowing_date
    assert "observed_at_from" in sql and "observed_at_to" in sql
    assert "NEW.sowing_date < v_from OR NEW.sowing_date > v_to" in sql


def test_v203_rejection_message_states_the_actual_range():
    """رسالة الرفض تذكر النطاق الفعليّ (حارس لا عائق — المُدخِل من الدفاتر يخطئ التواريخ كثيراً)."""
    sql = _sql()
    assert "RAISE EXCEPTION" in sql
    # الرسالة تحمل ثلاث قيم: sowing_date + الحدّان (three % placeholders + القيم)
    assert "must be within the observed range" in sql
    assert "NEW.sowing_date, v_from, v_to" in sql


def test_v203_is_forward_only_and_idempotent():
    """v201 مُطبَّقة إنتاجاً لا تُحرَّر ⇒ هجرة أماميّة idempotent (CREATE OR REPLACE + DROP/CREATE)."""
    sql = _sql()
    assert "CREATE OR REPLACE FUNCTION" in sql
    assert "DROP TRIGGER IF EXISTS trg_season_crop_sowing_in_range" in sql
