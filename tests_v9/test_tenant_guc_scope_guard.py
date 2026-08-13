"""حارس نطاق GUC المستأجِر — شجريّ لا ملفٌّ واحد. ``GUC-SCOPE-GUARD-SEES-ONE-FILE-01``.

الحارس القائم في ``services/raster-service/`` يحمل التشخيص الصحيح لعيبٍ إنتاجيّ حقيقيّ
(‏``set_config(..., true)`` في autocommit يضيع قبل الاستعلام التالي ⇒ RLS يُرجِع صفراً ⇒
هندسة فارغة) **لكنّ تأكيده على ملفٍّ واحد**. وهذه الاختبارات تقيس الشجرة.

**والقياس بنيويّ لا نصّيّ:** الاحتواء داخل معاملة سؤالٌ عن البنية. وأوّل صيغة من الحارس
مسحت الأسطر فالتقطت **شرحه هو** مخالفةً — فصار الكشف مُرسًى على **وسائط الاستدعاء**
عبر الـAST. الاختبار الأخير يحرس ذلك تحديداً.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "tenant_guc_scope_guard.py"
BASELINE = ROOT / "docs" / "architecture" / "tenant_guc_scope_baseline.json"


def _load_guard():
    spec = importlib.util.spec_from_file_location("tenant_guc_scope_guard", GUARD)
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل {GUARD}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tenant_guc_scope_guard"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_guard_exists_and_the_baseline_is_declared():
    """أساسٌ غائب يجعل الحارس يقبل كلّ شيء — الغياب فشلٌ لا تخطٍّ."""
    assert GUARD.is_file(), "الحارس غير موجود"
    assert BASELINE.is_file(), "الأساس المُعلَن غير موجود — بدونه لا راتشِت"
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["offenders"], "أساسٌ فارغ مع دَينٍ قائم يعني أنّ الكاشف لا يرى شيئاً"


def test_the_tree_matches_the_declared_baseline():
    """البوّابة خضراء على الشجرة كما هي — وإلّا فهي غير قابلة للدمج."""
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"الحارس يحجب على الشجرة القائمة:\n{proc.stdout}{proc.stderr}"


def test_the_detector_reproduces_the_documented_measurement():
    """تصادُقٌ مستقلّ: الجرد وثّق ١٢ في `market_server.py` — والكاشف يجب أن يراها.

    رقمٌ يُطابِق قياساً وثّقه غيري أقوى من رقمٍ أثق به وحدي.
    """
    mod = _load_guard()
    offenders, _ = mod.scan()
    market = [o for o in offenders if o["file"].endswith("mcp_servers/market_server.py")]
    assert len(market) == 12, (
        f"الجرد وثّق ١٢ موضعاً في market_server.py والكاشف يرى {len(market)} — "
        "أحدهما خاطئ، ولا يُطوى الفارق"
    )


def test_a_new_offender_outside_a_transaction_is_blocked(tmp_path, monkeypatch):
    """**الطفرة الأولى — عدم تطابق النطاق.** موضع `true` خارج معاملة ⇒ حجب."""
    mod = _load_guard()
    victim = tmp_path / "services" / "leak_service"
    victim.mkdir(parents=True)
    (victim / "store.py").write_text(
        "async def read(conn, tenant):\n"
        "    await conn.execute(\"SELECT set_config('app.current_tenant', $1, true)\", tenant)\n"
        "    return await conn.fetch('SELECT * FROM fields')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "_SCAN_DIRS", ("services",))
    offenders, _ = mod.scan()
    assert [o["file"] for o in offenders] == ["services/leak_service/store.py"], (
        "ضبطٌ بنطاق المعاملة خارج أيّ معاملة لم يُرصَد — وهو العيب الإنتاجيّ بعينه"
    )


def test_the_same_code_inside_a_transaction_is_clean(tmp_path, monkeypatch):
    """الوجه المقابل: نفس السطر **داخل** معاملة سليم — وإلّا كان الحارس يقيس الوجود."""
    mod = _load_guard()
    victim = tmp_path / "services" / "ok_service"
    victim.mkdir(parents=True)
    (victim / "store.py").write_text(
        "async def read(conn, tenant):\n"
        "    async with conn.transaction():\n"
        "        await conn.execute(\"SELECT set_config('app.current_tenant', $1, true)\", tenant)\n"
        "        return await conn.fetch('SELECT * FROM fields')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "_SCAN_DIRS", ("services",))
    offenders, _ = mod.scan()
    assert offenders == [], "ضبطٌ داخل معاملة رُصِد مخالفةً — إيجابيّة كاذبة تُبطِل الحارس"


def test_guc_names_are_inventoried_not_unified(tmp_path, monkeypatch):
    """**الطفرة الثانية — اسم GUC مختلف.** يُجرَد ولا يُوحَّد ميكانيكيّاً.

    توحيدُ الأسماء آليّاً يكسر سياسات RLS التي تقرأ الاسم الآخر. فالمقيس أنّ الحارس
    **يرى** التعدّد ويُبلِغه، لا أنّه يفرض اسماً واحداً.
    """
    mod = _load_guard()
    victim = tmp_path / "services" / "svc"
    victim.mkdir(parents=True)
    (victim / "a.py").write_text(
        "async def f(conn, t):\n"
        "    async with conn.transaction():\n"
        "        await conn.execute(\"SELECT set_config('app.tenant_id', $1, true)\", t)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "_SCAN_DIRS", ("services",))
    offenders, names = mod.scan()
    assert offenders == [], "داخل معاملة ⇒ لا مخالفة مهما كان الاسم"
    assert names == {"app.tenant_id"}, "الاسم البديل لم يُجرَد — التعدّد يجب أن يبقى مرئيّاً"


def test_prose_describing_the_defect_is_not_counted_as_committing_it():
    """الترسية على الاستدعاء: ملفٌّ **يصف** العيب ليس ملفّاً **يرتكبه**.

    قِيس هذا على الحارس نفسه: صيغته الأولى مسحت الأسطر فأدرجت وثيقتَها مخالفةً.
    """
    mod = _load_guard()
    offenders, _ = mod.scan()
    assert not [o for o in offenders if "tenant_guc_scope_guard" in o["file"]], (
        "الحارس يلتقط شرحه هو — الكشف يجب أن يُرسَى على وسائط الاستدعاء لا على نصّ الملفّ"
    )


def test_the_baseline_only_shrinks():
    """أساسٌ يحمل موضعاً أُصلِح يُجمّد ديناً مسدَّداً — الراتشِت يُنظَّف لا يُترَك."""
    mod = _load_guard()
    offenders, _ = mod.scan()
    found = {f"{o['file']}:{o['line']}" for o in offenders}
    known = set(json.loads(BASELINE.read_text(encoding="utf-8"))["offenders"])
    stale = sorted(known - found)
    assert not stale, "مواضع أُصلِحت وما تزال في الأساس — تُحذَف بـ--generate: " + ", ".join(stale)
