"""`load_service_main` يُميّز انحدارَ التوصيل عن التبعيّة الناقصة — لا يُخضِّر ما انكسر.

مراجعةُ Copilot على #1014: المُحمِّل كان يحوّل **أيَّ** `ImportError` أثناء استيراد
`main.py` إلى `pytest.skip`. فلو انكسر `router_registry` أو `routers.validation` —
التوصيلُ الذي يقيسه عقدُ HTTP على الخدمة نفسها — تُخطّيت الاختبارات وبقي CI أخضر:
صنفُ «التخطّي الصامت يُقرَأ نجاحاً» في المساعد الذي تعتمد عليه اختباراتُ خدماتٍ عدّة.

العقد: حزمةٌ خارجيّة غائبة ⇒ تخطٍّ مُعلَّل (بيئةُ تطوير بلا سائق لا تُعاقَب)؛ وحدةٌ داخليّة
غائبة أو استيرادٌ داخليّ مكسور ⇒ فشلٌ صريح. والتصنيفُ بالمسار: ما له ملفٌّ تحت جذر
الخدمة أو جذر المستودع داخليّ، والمجهولُ داخليّ (فشلٌ مغلق).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests_v9 import service_module

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_service(tmp_path: Path, monkeypatch):
    """خدمةٌ مؤقّتة بـ`main.py` يُكتَب لكلّ حالة؛ تُنظَّف `sys.path` و`sys.modules` بعدها."""
    service = tmp_path / "svc"
    service.mkdir()
    (service / "routers").mkdir()
    (service / "routers" / "__init__.py").write_text("", encoding="utf-8")
    original_path = list(sys.path)

    def write(main_src: str) -> Path:
        (service / "main.py").write_text(main_src, encoding="utf-8")
        return service

    service_module.purge_generic_modules()
    yield write
    service_module.purge_generic_modules()
    sys.path[:] = original_path


def _must_fail_hard(service: Path, match: str) -> None:
    """يحوّل التخطّي إلى فشلٍ صريح: لو تخطّى المُحمِّل لخرج استثناءُ التخطّي من الاختبار
    فسُجِّل «متخطّى» لا «فاشل» — وهو الصنفُ نفسُه الذي يُكذَّب هنا (قِيس على #1014)."""
    try:
        service_module.load_service_main(str(service), required_attrs=("app",))
    except AssertionError as exc:
        assert match in str(exc), str(exc)
        return
    except pytest.skip.Exception as exc:
        pytest.fail(f"انحدارٌ داخليّ صار تخطّياً: {exc}")
    pytest.fail("المُحمِّل أعاد وحدةً رغم انكسار استيرادها")


def test_a_missing_internal_module_is_a_hard_failure(fake_service):
    service = fake_service("from routers.validation import router  # لا وجود لها\napp = object()\n")
    _must_fail_hard(service, "انحدارُ توصيلٍ")


def test_a_missing_external_package_still_skips(fake_service):
    service = fake_service("import definitely_not_an_installed_package_sahool\napp = object()\n")
    with pytest.raises(pytest.skip.Exception, match="تبعيّة خارجيّة ناقصة"):
        service_module.load_service_main(str(service), required_attrs=("app",))


def test_a_broken_internal_import_is_a_hard_failure_not_a_skip(fake_service):
    """`ImportError` بلا `ModuleNotFoundError`: الوحدةُ موجودة واسمٌ غائب منها."""
    service = fake_service("from routers import no_such_router\napp = object()\n")
    _must_fail_hard(service, "انكسر استيرادُ")


def test_a_healthy_service_loads_and_is_identified_by_path(fake_service):
    service = fake_service("app = object()\n")
    mod = service_module.load_service_main(str(service), required_attrs=("app",))
    assert Path(mod.__file__).resolve() == (service / "main.py").resolve()


def test_an_unknown_module_name_is_classified_internal_fail_closed(tmp_path: Path):
    assert service_module._is_internal_module(None, tmp_path) is True
    assert service_module._is_internal_module("main", tmp_path) is True
    assert service_module._is_internal_module("shared.whatever", tmp_path) is True, (
        "`shared/` تحت جذر المستودع ⇒ داخليّة"
    )
    assert service_module._is_internal_module("definitely_not_a_repo_package_x", tmp_path) is False
