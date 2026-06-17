"""حارس دور المهامّ الخلفيّة sahool_jobs (HIGH-002 — العزل + التجاوز المقصود).

الجداول العابرة للمستأجرين (event_outbox الآن، الطقس لاحقاً) تُقرأ بلا سياق مستأجِر
من مهامّ خلفيّة (المرسِل/المجدوِل). الحلّ الصحيح بدل كشفها لكلّ التطبيق: RLS عليها
(فيُعزَل التطبيق sahool_app) + دور مخصّص sahool_jobs (BYPASSRLS) لمسار المهامّ وحده.

هذا الحارس (ثابت) يثبت أركان النمط: الدور يُنشأ بـBYPASSRLS، event_outbox عليه
RLS+FORCE، المرسِل يستعمل مسبح المهامّ، والإنتاج يحقن JOBS_DATABASE_URL.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))


def _read(p):
    with open(os.path.join(BASE, p), encoding="utf-8") as f:
        return f.read()


def test_jobs_role_created_with_bypassrls():
    """apply_in_compose ينشئ sahool_jobs بـBYPASSRLS (وNOSUPERUSER — أضيق صلاحيّة)."""
    sh = _read("migrations/apply_in_compose.sh")
    assert "JOBS_ROLE" in sh and "sahool_jobs" in sh
    # السطر الذي يثبّت السمات يجب أن يحوي BYPASSRLS وNOSUPERUSER.
    assert "BYPASSRLS" in sh, "sahool_jobs بلا BYPASSRLS ⇒ يفشل المرسِل تحت RLS"
    assert "NOSUPERUSER" in sh, "sahool_jobs يجب ألّا يكون superuser (أضيق صلاحيّة)"


def test_app_role_still_nobypassrls():
    """دور التطبيق sahool_app يبقى NOBYPASSRLS (العزل محفوظ — لم يُضعَّف)."""
    sh = _read("migrations/apply_in_compose.sh")
    assert "NOBYPASSRLS" in sh, "sahool_app فقد NOBYPASSRLS — انهار عزل المستأجرين!"


def test_event_outbox_has_force_rls():
    """v72 يُفعّل RLS+FORCE+سياسة معزولة عبر الأب events على event_outbox."""
    sql = _read("migrations/v72_event_outbox_rls.sql")
    assert "ALTER TABLE event_outbox ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE event_outbox FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation ON event_outbox" in sql
    assert "FROM events e" in sql and "e.event_id = event_outbox.event_id" in sql


def test_v72_in_manifest():
    assert "v72_event_outbox_rls.sql" in _read("migrations/MANIFEST.txt")


def test_outbox_worker_uses_jobs_pool():
    """المرسِل (OutboxWorker) يستعمل مسبح المهامّ (_JOBS_POOL) لا مسبح التطبيق وحده."""
    src = _read("services/sahool-platform/api/main.py")
    assert "_JOBS_POOL" in src, "لا مسبح مهامّ منفصل"
    assert "OutboxWorker(_JOBS_POOL or _DB_POOL" in src, (
        "المرسِل لا يفضّل مسبح المهامّ ⇒ يقرأ event_outbox بدور معزول فيفشل تحت RLS"
    )


def test_production_injects_jobs_database_url():
    """الإنتاج (v9) يحقن JOBS_DATABASE_URL لخدمة المنصّة (وإلّا المرسِل على دور معزول)."""
    assert "JOBS_DATABASE_URL" in _read("docker-compose.v9.yml")
