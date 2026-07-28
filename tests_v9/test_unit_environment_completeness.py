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
    "fastapi": "اختبارات تبني api.main عبر TestClient، ومنها 12 ملفّاً تفحص app.routes",
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
