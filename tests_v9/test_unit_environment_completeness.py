"""الحارس ضدّ عودة الخمود الصامت.

إيقاظ ~479 اختبار وحدة تمّ بإضافة ثلاث تبعيّات إلى ``requirements-test.txt``. بلا حارس،
حذف أيٍّ منها لاحقاً يُعيدها إلى ``skip`` **بصمت**: البوّابة تبقى خضراء وتُبلِغ عدداً أصغر،
ولا أحد يقرأ عدّاد المتخطّى. هذا بالضبط ما حدث أوّل مرّة — الاستبعاد كان موثّقاً ومبرَّراً
يوم كُتب، ثمّ تآكل مبرّره دون أن يُنبِّه أحد.

فالحارس لا يفحص الاختبارات الموقَظة واحداً واحداً (هشّ)، بل **الشرط الذي يجعلها تعمل**.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit

# (وحدة الاستيراد، ما تُوقِظه) — التبرير في requirements-test.txt.
_REQUIRED = {
    "fastapi": (
        "اختبارات تبني api.main عبر TestClient، ومنها ملفّات تفحص المسارات "
        "المُسجَّلة عبر app.openapi()['paths'] (conftest.registered_paths/"
        "registered_methods — APP-ROUTES-INTROSPECTION-COUPLING-01)"
    ),
    "scipy": "core.spatial (مثبَّتة أصلاً في api/requirements.txt:20)",
    "PIL": "تصيير الصور في اختبارات raster/bivariate",
}


@pytest.mark.parametrize("module", sorted(_REQUIRED))
def test_unit_environment_keeps_the_dormancy_wakers_installed(module: str):
    """حذف أيٍّ من هذه من requirements-test.txt يُخمِد مئات الاختبارات بصمت."""
    try:
        importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - يفشل عمداً عند الانحدار
        pytest.fail(
            f"{module} غائبة عن بيئة -m unit ⇒ يعود الخمود الصامت لِـ{_REQUIRED[module]}. "
            f"أعِدها إلى tests_v9/requirements-test.txt بدل قبول عدّاد متخطٍّ أكبر. ({exc})"
        )


def test_service_module_loader_proves_identity_by_path():
    """الحمولة الحقيقيّة لـservice_module: منع نجاح كاذب على وحدة خدمة أخرى."""
    from tests_v9.service_module import load_service_main

    with pytest.raises(AssertionError, match="تصادم أسماء"):
        # جذر المستودع ليس جذر خدمة: أيّ `main` يُستورَد منه هو الوحدة الخطأ.
        load_service_main("services/auth", required_attrs=("__nonexistent_attr__",))


def test_the_path_check_still_catches_a_collision_when_the_purge_is_neutralised():
    """خطّ الدفاع الثاني: لو فشل الإسقاط، تُمسَك الهويّة **بالمسار** لا بالسمات.

    فحصُ السمات وحده يمرّ على وحدةٍ شقيقة تصادف حملُها الأسماءَ نفسها؛ والمسار لا يكذب.
    مقيسٌ بتعطيل الإسقاط عمداً — وإلّا لبقي هذا السطر بلا تكذيب (يمرّ لأنّ ما قبله يعمل).
    """
    import importlib
    import sys

    from tests_v9 import service_module

    sys.path.insert(0, "services/soil-service")
    service_module.purge_generic_modules()
    importlib.import_module("main")  # يُخزّن وحدة soil باسم 'main'
    original_purge = service_module.purge_generic_modules
    service_module.purge_generic_modules = lambda: None  # تعطيلُ خطّ الدفاع الأوّل
    try:
        # ``ingest_reading`` سمةٌ **يملكها** main الخاصّ بـsoil — فلا يستطيع فحصُ
        # السمات أن يمسك هذه الحالة، ولا يبقى بين النجاح الكاذب وبيننا إلّا المسار.
        # (لو طُلبت سمةٌ لا يملكها، ابتلع فحصُ السمات الحالةَ ونجت الطفرة صامتة —
        # وهو ما وقع فعلاً في أوّل صياغة، فصُحّح بالقياس لا بالمراجعة.)
        with pytest.raises(AssertionError, match="خارج"):
            service_module.load_service_main("services/auth", required_attrs=("ingest_reading",))
    finally:
        service_module.purge_generic_modules = original_purge
        service_module.purge_generic_modules()


# الملفّات التي تستورد ``main`` عارياً وتُنظّف بنفسها **داخل تجهيزاتها** بدل المساعِد.
# استثناءٌ مُعلَن لا صمت: قوائم إسقاطها أوسع من ``_GENERIC_ROOTS`` (تشمل ``db_persist``
# مثلاً)، فترحيلها الأعمى إلى المساعِد يُضيّق تنظيفها ويكسرها. تبقى مسموحةً **بشرط**
# أن تُثبِت كلٌّ منها أنّها تُسقط المُخبّأ فعلاً — والشرط مفروضٌ أدناه لا موعود.
_INLINE_PURGE_ALLOWLIST = frozenset(
    {
        "test_auth_admin_stepup_mfa.py",
        "test_auth_mfa_enforcement.py",
        "test_soil_field_tenant_authz.py",
        "test_video_processor_features_20260702.py",
        "test_video_stream_tenant_authz.py",
    }
)


def test_no_test_in_the_shared_process_imports_a_bare_main_unguarded():
    """``sys.modules`` مفتاحه الاسم لا المسار، و٢٤ خدمة تحمل ``main.py``.

    كلّ ملفّات ``tests_v9`` تعمل في **عمليّة واحدة**، فاستيرادُ ``main`` عارياً بلا
    إسقاطٍ للمُخبّأ يجعل صحّة الملفّ رهنَ ترتيب الجمع وأيّ تبعيّةٍ اختياريّة صادف
    وجودُها. والخطر ليس الفشل بل **النجاح الكاذب**: وحدةٌ شقيقة تحمل الأسماء نفسها
    تمرّ صامتة. مقيسٌ في 2026-08-25 على ``test_tenant_provisioning.py``.
    """
    import pathlib
    import re

    here = pathlib.Path(__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(here.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if not re.search(r'import_module\(\s*["\']main["\']\s*\)', text):
            continue
        # **استدعاءٌ** لا ذِكر: `if "load_service_main" in text` كان يُعفي الملفّ
        # بمجرّد ورود الاسم في تعليق — وهو ما أعفى أوّل صياغةٍ من نفسها، ومسكه
        # التكذيب لا المراجعة.
        if re.search(r"load_service_main\s*\(", text):
            continue
        if path.name in _INLINE_PURGE_ALLOWLIST:
            assert re.search(r'sys\.modules\.pop\(\s*(["\']main["\']|_m)', text), (
                f"{path.name} في قائمة الاستثناء بدعوى الإسقاط الداخليّ — ولا إسقاط فيه. "
                "إمّا يُسقط فعلاً وإمّا يخرج من القائمة إلى load_service_main."
            )
            continue
        offenders.append(path.name)

    assert not offenders, (
        "استيرادُ `main` عارياً بلا حارس في العمليّة المشتركة: "
        + ", ".join(offenders)
        + " — استعمل tests_v9.service_module.load_service_main (يُسقط المُخبّأ ويُثبِت "
        "الهويّة بالمسار)، أو أضِفه إلى _INLINE_PURGE_ALLOWLIST إن كان يُسقط بنفسه."
    )


def test_loading_the_same_service_twice_returns_the_same_module_object():
    """إعادةُ الاستيراد تخلق كائنَ وحدةٍ ثانياً لنفس الملفّ — وهو عطلٌ صامت.

    من استورد الأولى يبقى عليها، بينما ``sys.modules["main"]`` صار الثانية؛ وكلُّ
    من يحلّ ``import main`` **وقتَ الاستدعاء** يقرأ الثانية. فيقع الترقيع على كائن
    والقراءةُ على آخر.

    مقيسٌ على #927: ``mfa_runtime._main()`` يستورد ``main`` عند كلّ نداء، فأسقط
    ملفٌّ لاحقٌ أعاد استيراد auth اختبارَ ``test_correct_code_is_true`` بلا أن
    يتغيّر سطرٌ فيه — والعطلُ لم يظهر إلّا في تشغيل الجناح كاملاً.
    """
    from tests_v9.service_module import load_service_main

    first = load_service_main("services/auth", required_attrs=("require_role",))
    second = load_service_main("services/auth", required_attrs=("require_role",))
    assert first is second, (
        "تحميلُ الخدمة نفسها مرّتين أنتج كائنَين — وهو ما يكسر ترقيعَ الاختبارات "
        "التي تحلّ `main` وقت الاستدعاء."
    )
