"""`TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01` — وشهودُ نطاقه الخمسة.

عزلُ المستأجِر يقوم على `current_setting('app.<اسم>')` في سياسات RLS، والاسمُ ليس
واحداً: ثلاثُ عائلاتٍ تقرأ ثلاثةَ أسماء. **وشكلُ الفشل صامت** — اسمٌ خاطئ ⇒ `NULL`
⇒ `USING` تُصفّي كلَّ شيء ⇒ صفرُ صفوفٍ بلا خطأ ولا سجلّ.

ويفرض هذا الملفّ `GUARD-SCOPE-COMPLETENESS` (دفتر القرارات 2026-08-20): لا يُقبَل
حارسٌ جديد إلّا بخمسة شهود — مصدرُ السطح، وما رآه، وما استبعده ولماذا، **وتساوي
المجموعات** لا العدّادات، وشاهدُ طفرة.

**وشاهدٌ سادسٌ يخصّ هذا الحارس بعينه: موجبٌ لكلّ كاشف.** كلُّ تأكيدٍ هنا على شجرةٍ
سليمة هو تأكيدُ **غياب** (`new == []` · `unset == []`)، وهو يبقى صادقاً **لو عُطِّل
الكشفُ رأساً**. فيُقاس كلُّ كاشفٍ بالإيجاب على تقريرٍ مُصطنَع — وإلّا كان الملفّ
كلُّه أخضرَ بلا معلومة، وهو الصنفُ الذي أمسكه مراجعٌ آليّ عليّ في #953.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_g_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_g_{name}"] = module
    spec.loader.exec_module(module)
    return module


guard = _load("tenant_guc_name_convergence_guard")


# ── الشهود ①②: مصدرُ السطح وما رآه ─────────────────────────────────────────
def test_the_surface_is_derived_from_the_tree_not_a_written_table():
    """قائمةٌ مكتوبة تبيت: هجرةٌ جديدة باسمٍ رابع لا تدخل النطاق، والحارسُ يبقى
    أخضرَ عن سؤالٍ لم يعد يطرحه. والنطاقُ هنا **تعبيرٌ على الاسم** (`app.*tenant*`)،
    فالاسمُ الرابع يدخل بمجرّد كتابته ولا ينتظر أحداً ليُدرِجه."""
    read = guard.tenant_names_read()

    assert read, "صفرُ اسمٍ مكتشَف — والمستودعُ يحمل مئاتِ السياسات"
    for name, files in read.items():
        assert guard._TENANT_SCOPED.match(name), f"اسمٌ خارج النطاق تسرّب: {name}"
        assert files, f"اسمٌ بلا هجرةٍ تقرؤه: {name}"


def test_the_dynamic_policy_families_are_actually_seen():
    """**الاشتقاقُ قِيس أنّه يرى ما كان مُستخرِجٌ ساكنٌ يفوته.**

    ثلاثُ عائلاتٍ هنا تُنشئ سياساتِها داخل `format()` في كتلة `DO` — أوسعُها
    `_sahool_apply_tenant_rls` التي تحكم `fields` نفسَها. فمُستخرِجٌ يقرأ
    `CREATE POLICY` الساكنة وحدَها كان **يفوته أكبرُ عائلةٍ في الشجرة**.
    """
    read = guard.tenant_names_read()
    joined = {name: " ".join(files) for name, files in read.items()}

    assert "v9_rls_tenant_isolation.sql" in joined.get("app.current_tenant", "")
    assert "v161_soil_p1_products.sql" in joined.get("app.current_tenant_id", "")
    assert "v106_phase9_10_runtime_strengthening.sql" in joined.get("app.tenant_id", "")


# ── الشاهد ③: ما استُبعِد ولماذا ────────────────────────────────────────────
def test_non_tenant_scoped_names_are_excluded_by_derivation_not_by_exemption():
    """`app.current_role` و`app.current_user_id` **خارج النطاق بالاشتقاق لا بإعفاء**.

    انحرافُهما عطلُ تفويضٍ لا عطلُ عزلٍ بين المستأجرين — صنفٌ آخر بأثرٍ آخر،
    وإدخالُه هنا كان يُوسِّع الادّعاءَ فوق الدليل المقيس.
    """
    for outside in ("app.current_role", "app.current_user_id", "app.managed_roles"):
        assert not guard._TENANT_SCOPED.match(outside), f"اسمٌ غيرُ مستأجِرٍ دخل النطاق: {outside}"
    assert guard._TENANT_SCOPED.match("app.current_tenant")
    assert guard._TENANT_SCOPED.match("app.tenant_id")


def test_the_two_zero_setter_names_are_not_policies_at_all():
    """`app.managed_roles` و`app.bypassrls_allowed` بصفر ضابط — **وليسا عطلاً**.

    قِيسا فوُجِدا في **تأكيدٍ داخل سكربت إعداد** يضبطهما السكربتُ نفسُه، لا في أيّ
    سياسة. فاستبعادُهما اشتقاقٌ صحيح، وتسجيلُ ذلك يمنع من يقرأ العدّادَ لاحقاً من
    «إصلاح» ما ليس معطوباً.
    """
    setup = (ROOT / "migrations" / "apply_in_compose.sh").read_text(encoding="utf-8")
    assert "current_setting('app.managed_roles')" in setup
    assert not any(
        guard._TENANT_SCOPED.match(n) for n in ("app.managed_roles", "app.bypassrls_allowed")
    )


# ── الشاهد ④: تساوي المجموعات لا العدّادات ─────────────────────────────────
def test_the_name_set_matches_a_frozen_identity_set_not_a_count():
    """عدّادٌ ثابت يمرّ حين يُضاف اسمٌ **ويُحذَف** آخر — وهو شكلُ الانحراف بعينه.

    ولذلك تُقارَن **المجموعة**: اسمٌ جديد يُحمِّر، واسمٌ زال يُحمِّر أيضاً كي
    يُخفَض السقفُ صراحةً بدل أن يبقى مقعداً شاغراً يعود إليه مخالف.
    """
    report = guard.audit()
    assert set(report["names"]) == set(guard.EXPECTED_NAMES)
    assert report["new"] == [] and report["retired"] == []


def test_every_name_a_policy_reads_is_set_by_some_path():
    """اسمٌ بلا ضابطٍ يعني جدولاً لا يُقرَأ منه شيءٌ أبداً — صفرٌ دائمٌ بلا شكوى."""
    assert guard.audit()["unset"] == []


def test_the_measured_asymmetry_is_recorded_so_it_cannot_quietly_worsen():
    """**الرقمُ المُقلِق ليس وجودَ الأسماء بل النسبة.**

    ولا تُثبَّت الأعدادُ بالضبط — تتحرّك مع كلّ هجرة، فتثبيتُها يجعل هذا الاختبارَ
    ضجيجاً. المُثبَّتُ **الخاصّيّة**: لكلّ اسمٍ ضابطٌ واحد على الأقلّ، والاسمُ
    الشائع أكثرُ ضبطاً بمراتب — فانقلابُ ذلك يعني توحيداً جرى أو انحرافاً أعمق.
    """
    report = guard.audit()
    setters = report["setters"]
    assert all(count >= 1 for count in setters.values())
    assert setters["app.current_tenant"] > 10 * max(
        setters["app.tenant_id"], setters["app.current_tenant_id"]
    ), "تبدّلت بنيةُ الانحراف — أعِد قياسَه قبل تحديث هذا الشاهد"


# ── الشاهد ⑤ + الموجب: كلُّ كاشفٍ يُقاس بالإيجاب ───────────────────────────
def test_a_fourth_name_is_actually_reported(monkeypatch):
    """**شاهدٌ موجب — وبدونه كان `new == []` يمرّ على كاشفٍ مُعطَّل.**

    تأكيدُ غيابٍ يقيس سكونَ الشجرة لا عملَ الآليّة. فيُقاس هنا على تقريرٍ
    مُصطنَع: اسمٌ رابع **يُبلَّغ**، وشجرةٌ سليمة تمرّ.
    """
    planted = {
        "names": [*sorted(guard.EXPECTED_NAMES), "app.tenant_uuid"],
        "read": {},
        "setters": {},
        "unset": [],
        "new": ["app.tenant_uuid"],
        "retired": [],
        "ceiling": guard.NAME_CEILING,
    }
    reasons = guard.failures(planted)
    assert any("app.tenant_uuid" in reason for reason in reasons)
    assert any("السقف" in reason for reason in reasons), "الرابعُ تجاوز السقفَ ولم يُبلَّغ"


def test_a_name_no_path_sets_is_actually_reported():
    """كاشفُ «اسمٌ بلا ضابط» يُقاس بالإيجاب: صفرُ ضابطٍ **يُبلَّغ**."""
    planted = {
        "names": sorted(guard.EXPECTED_NAMES),
        "read": {},
        "setters": {},
        "unset": ["app.tenant_id"],
        "new": [],
        "retired": [],
        "ceiling": guard.NAME_CEILING,
    }
    assert any("app.tenant_id" in reason for reason in guard.failures(planted))


def test_a_zero_discovery_run_fails_instead_of_passing_green():
    """صفرُ اكتشافٍ يمرّ أخضرَ لو لم يُغلَق — وهو أخطرُ من انحرافٍ مُبلَّغ."""
    empty = {
        "names": [],
        "read": {},
        "setters": {},
        "unset": [],
        "new": [],
        "retired": [],
        "ceiling": guard.NAME_CEILING,
    }
    assert guard.failures(empty)


def test_a_healthy_report_produces_no_reasons():
    """والسليمُ يمرّ — كاشفٌ يقول «موجود» دائماً لا يكشف شيئاً."""
    healthy = {
        "names": sorted(guard.EXPECTED_NAMES),
        "read": {},
        "setters": {},
        "unset": [],
        "new": [],
        "retired": [],
        "ceiling": guard.NAME_CEILING,
    }
    assert guard.failures(healthy) == []


def test_the_guard_exits_nonzero_when_it_reports(monkeypatch):
    """حارسٌ يطبع الشكوى ويُنهي بصفرٍ لا يحجب شيئاً."""
    monkeypatch.setattr(
        guard,
        "audit",
        lambda: {
            "names": ["app.tenant_uuid"],
            "read": {"app.tenant_uuid": 1},
            "setters": {"app.tenant_uuid": 0},
            "unset": ["app.tenant_uuid"],
            "new": ["app.tenant_uuid"],
            "retired": sorted(guard.EXPECTED_NAMES),
            "ceiling": guard.NAME_CEILING,
        },
    )
    monkeypatch.setattr(sys, "argv", ["tenant_guc_name_convergence_guard.py"])
    assert guard.main() == 1


def test_the_guard_survives_the_machine_locale():
    """`GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01`: مخرَجٌ عربيٌّ
    يحسب صحيحاً ثمّ يموت وهو يطبع نجاحَه، فيُقرَأ `exit=1` حجباً وهو مرور."""
    source = (ROOT / "scripts" / "ci" / "tenant_guc_name_convergence_guard.py").read_text(
        encoding="utf-8"
    )
    reconfigure = re.search(r"reconfigure\(encoding=\"utf-8\"\)", source)
    assert reconfigure, "بلا إعادة ترميزٍ عند التحميل"
    assert source.index("def main(") > reconfigure.start(), (
        "إعادةُ الترميز داخل `main()` تترك المسارَ المُستورَد مكشوفاً"
    )
