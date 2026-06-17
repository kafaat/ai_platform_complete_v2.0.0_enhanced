"""بوّابة CI لتعداد عزل المستأجرين الشامل (scripts/tenant_query_audit).

ينقل العزل من «فحصتُ عيّنة» إلى «كلّ استعلام محسوب ومُبوَّب». كلّ استعلام على جدول
مُستأجَر مُصنَّف (RLS_CONN/EXPLICIT/DELEGATED/APP_FILTER/RAW)؛ كلّ RAW مُبرَّر فرديّاً في
allowlist. أيّ RAW جديد على جدول مُستأجَر خارج الـallowlist يُفشِل CI (يجب تصنيفه أو
تحويله إلى tenant_connection). يتضمّن سلامة ذاتيّة للماسح.
"""

from __future__ import annotations

import importlib.util
import os
import textwrap

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load():
    spec = importlib.util.spec_from_file_location(
        "tq_audit", os.path.join(ROOT, "scripts", "tenant_query_audit.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_no_unclassified_raw_tenant_queries():
    """كلّ استعلام RAW على جدول مُستأجَر مُبرَّر في الـallowlist — أيّ جديد يُفشِل."""
    m = _load()
    viol = m.raw_violations(m.audit())
    assert not viol, (
        "استعلامات RAW على جداول مُستأجَرة خارج الـallowlist (صنّفها أو حوّلها لـ"
        "tenant_connection، أو أضِفها لـ_ALLOWLIST_JUSTIFIED بتبرير):\n  "
        + "\n  ".join(f"{r['loc']} [{r['tables']}]" for r in viol)
    )


def test_audit_finds_tenant_queries():
    """سلامة: الماسح يكتشف استعلامات مُستأجَرة فعلاً (وإلّا فالتحليل مكسور)."""
    m = _load()
    rows = m.audit()
    assert len(rows) > 100, "تعداد الاستعلامات المُستأجَرة منخفض مريب — التحليل مكسور"
    classes = {r["class"] for r in rows}
    assert "RLS_CONN" in classes  # المسار الأساسيّ موجود


def test_allowlist_entries_are_justified():
    """كلّ مدخل allowlist له تبرير غير فارغ (لا ختم مطّاطيّ صامت)."""
    m = _load()
    for key, just in m._ALLOWLIST_JUSTIFIED.items():
        assert just and len(just) > 8, f"مدخل allowlist بلا تبرير: {key}"


def test_scanner_flags_new_raw(tmp_path, monkeypatch):
    """سلامة الماسح: استعلام raw جديد على جدول مُستأجَر (بلا سياق) يُرصَد."""
    m = _load()
    svc = tmp_path / "services" / "newsvc"
    svc.mkdir(parents=True)
    (svc / "leak.py").write_text(
        textwrap.dedent("""
        async def read(pool, fid):
            async with pool.acquire() as conn:
                return await conn.fetch("SELECT * FROM fields WHERE field_id = $1", fid)
        """),
        encoding="utf-8",
    )
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "SCAN", ("services",))
    monkeypatch.setattr(m, "tenant_tables", lambda: {"fields"})  # بلا migrations في tmp
    # جدول fields مُستأجَر؛ الدالّة تكتسب pool.acquire بلا سياق ولا ترشيح ⇒ RAW
    rows = m.audit()
    assert any(r["class"] == "RAW" and "fields" in r["tables"] for r in rows)
