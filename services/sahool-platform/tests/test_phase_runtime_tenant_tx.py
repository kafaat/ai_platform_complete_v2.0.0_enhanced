"""حارس: كتابات phase_runtime تضبط سياق RLS داخل معاملة (transaction).

السبب الجذريّ المُصلَّح: ``set_config(..., is_local=true)`` محلّيّ-للمعاملة؛ وasyncpg
ينفّذ خارج المعاملات في وضع autocommit. فبدون ``conn.transaction()`` محيطة، يُعاد ضبط
GUC المستأجِر قبل تنفيذ الكتابة — وتحت الدور المقيّد ``sahool_app`` (NOBYPASSRLS) تُرفض
كلّ كتابة FORCE-RLS. CI لا يكشفه لأنّ Integration Tests تتّصل بدور superuser يتجاوز RLS.

هذا الحارس ساكن (يمنع عودة النمط الخطر) لأنّ المسار الحيّ مُقنَّع بدور superuser في CI.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

API = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "api"))
STORE = os.path.join(API, "phase_runtime_store.py")
WORKERS = os.path.join(API, "phase_runtime_workers.py")


def _read(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_store_uses_transaction_wrapped_tenant_context():
    src = _read(STORE)
    # المُجمِّع الصحيح موجود: acquire + transaction + set_config.
    assert "async def _tenant_conn(" in src
    assert "conn.transaction()" in src
    assert "set_config('app.current_tenant'" in src and "set_config('app.tenant_id'" in src
    # النمط الخطر (acquire ثمّ _set_rls_tenant مباشرةً بلا معاملة) لم يَعُد موجوداً.
    broken = re.search(r"async with pool\.acquire\(\) as conn:\s*\n\s*await _set_rls_tenant\(", src)
    assert broken is None, "tenant write acquires a connection without an enclosing transaction"


def test_workers_wrap_skip_locked_batches_in_transactions():
    src = _read(WORKERS)
    # لا يوجد acquire عارٍ بلا transaction (FOR UPDATE SKIP LOCKED بلا معاملة = قفل بلا معنى).
    bare = re.findall(r"async with pool\.acquire\(\) as conn:\s*\n", src)
    assert bare == [], (
        "worker acquires a connection without conn.transaction() (SKIP LOCKED is a no-op)"
    )
    assert "async with pool.acquire() as conn, conn.transaction():" in src
    assert "FOR UPDATE SKIP LOCKED" in src
