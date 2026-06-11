"""Unit test: عزل InMemoryWorkflowStore لكلّ مستأجر (مسار التطوير بلا DB).

كان _get_workflow_store يُرجِع مفرداً InMemory واحداً مشتركاً يفهرس بـ
workflow_id فقط ⇒ مستأجران بنفس workflow_id يتصادمان (يقرأ أحدهما حالة الآخر).
الإصلاح: مخزن منفصل لكلّ tenant. هذا الاختبار يحرس ألّا يعود التصادم.
(الإنتاج يستعمل Postgres+RLS — هذا المسار تطويريّ فقط.)
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.mark.unit
def test_inmem_workflow_store_isolated_per_tenant(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-for-ci-only-0123456789")
    monkeypatch.delenv("DATABASE_URL", raising=False)  # يفرض مسار InMemory
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m
    from core.workflow_engine import WorkflowState

    m._INMEM_WORKFLOW_STORES.clear()

    sa = m._get_workflow_store("tenant-A")
    sb = m._get_workflow_store("tenant-B")
    assert sa is not sb  # مخزن منفصل لكلّ مستأجر
    assert m._get_workflow_store("tenant-A") is sa  # نفس المخزن للمستأجر نفسه

    # حالة بنفس workflow_id في A لا تظهر للمستأجر B (لا تصادم/تسريب).
    sa.save(WorkflowState(workflow_id="wf-shared", tenant_id="tenant-A"))
    assert sa.load("wf-shared") is not None
    assert sb.load("wf-shared") is None
