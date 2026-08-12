"""`UNDECLARED-CONTEXT-DEPENDENCY-01` — طلبٌ عبر المُحلِّل بلا إعلانٍ يُحجَب.

**البابُ الذي يسدّه:** حارسُ الالتفاف يرى مَن يقرأ الحقل مباشرةً؛ ومن يقرؤه عبر
المُحلِّل خارج مداه تماماً. فيستطيع أن يطلب مفتاحاً بـ`ctx.require("...")` بلا
إعلان، فتعود التبعيّة إلى رأس كاتبها — وهو ما بُنيت الطبقة لإخراجه منه.

**وأوّل تشغيلٍ للحارس قاس صفر طلب**، لأنّ المُنسِّق كان يحلّ العقد ثمّ يُهمِل
القيمة. وحارسٌ يمرّ على عالمٍ فارغ يقول «لا مخالفة» عن سؤالٍ لم يُطرَح — فأُصلِح
**السبب** (صار المُنسِّق يستهلك القيمة ويُصدِر نَسَبَها) لا الحارس.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "undeclared_context_dependency_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("undeclared_context_dependency_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_REGISTERED = {"a.k", "a.other"}
_DECLARED = {"a.k"}


def _consumer(tmp_path: Path, body: str) -> tuple[list[Path], Path]:
    pkg = tmp_path / "services"
    pkg.mkdir(exist_ok=True)
    target = pkg / "consumer.py"
    target.write_text(body, encoding="utf-8")
    return [target], tmp_path


def test_a_declared_and_registered_request_passes(tmp_path):
    files, root = _consumer(tmp_path, 'def f(ctx):\n    return ctx.require("a.k")\n')
    problems, requests = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems == []
    assert requests == 1


def test_a_registered_but_undeclared_request_is_blocked(tmp_path):
    """الصنف المقصود: مفتاحٌ له مصدرُ حقيقة، ولا عقدَ يقول إنّ هذه المهمّة تحتاجه."""
    files, root = _consumer(tmp_path, 'def f(ctx):\n    return ctx.require("a.other")\n')
    problems, _ = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems and "بلا إعلانٍ في أيّ عقد" in problems[0]


def test_an_unregistered_request_is_blocked_with_its_own_reason(tmp_path):
    """خطأٌ أوضح: يسأل عن شيءٍ لا مصدر حقيقةٍ له — ورسالةٌ تخلطهما تُضلّل."""
    files, root = _consumer(tmp_path, 'def f(ctx):\n    return ctx.require("a.ghost")\n')
    problems, _ = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems and "لا مصدرَ حقيقةٍ مُسجَّلاً له" in problems[0]


def test_provenance_is_watched_like_require(tmp_path):
    """`provenance()` طلبٌ أيضاً: من يسأل عن النَّسَب يعتمد على المفتاح."""
    files, root = _consumer(tmp_path, 'def f(ctx):\n    return ctx.provenance("a.other")\n')
    problems, _ = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems


def test_another_method_with_a_string_argument_is_not_a_request(tmp_path):
    """الحصرُ في `require`/`provenance` هو ما يمنع الضجيج.

    `d.get("x")` و`s.startswith("y")` تملأ أيّ شجرة؛ وعدُّها طلباتٍ يُنتِج مئات
    المخالفات الكاذبة، وهي تُسقِط الحارس بلا تعطيله لأنّ قارئ الأحمر يتعلّم
    تجاهله.

    **وهذا التأكيد أُضيف بعد أن كشفت الطفرة أنّ مرساتي كانت خاطئة:** توسيعُ
    الحصر لم يكن يُحمِر اختبار التعليق (فالتعليقات لا تصل إلى `ast` أصلاً)، بل
    كان يُحمِر اختبارات الشجرة الحيّة وحدها — أي «حمرّ بغير الاختبار المُتوقَّع».
    """
    files, root = _consumer(tmp_path, 'def f(cfg):\n    return cfg.get("a.other")\n')
    problems, requests = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems == [] and requests == 0


def test_a_key_named_in_a_comment_is_not_a_request(tmp_path):
    """يُقرأ الاستدعاء لا النصّ — وإلّا صار الشرح يُحمِر الحارس."""
    files, root = _consumer(
        tmp_path, 'def f(ctx):\n    # ctx.require("a.other") مذكورٌ شرحاً\n    return 1\n'
    )
    problems, requests = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems == [] and requests == 0


def test_a_same_named_method_on_another_object_is_still_watched(tmp_path):
    """الحارس يرى `x.require("k")` أيّاً كان `x`.

    وهذا **مقصود ومحافظ**: تمييزُ «المُحلِّل» من غيره يحتاج تتبّع أنواع، وفشلُه
    يكون في اتّجاه العمى. والثمن إيجابيّةٌ محتملة على `require` أخرى — وهي
    تُعالَج بتسجيل المفتاح أو بإعادة تسمية الدالّة، لا بإسكات الحارس.
    """
    files, root = _consumer(tmp_path, 'def f(cfg):\n    return cfg.require("a.other")\n')
    problems, _ = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert problems


def test_test_files_are_not_scanned(tmp_path):
    """اختباراتٌ تطلب مفاتيح تركيبيّة يجب ألّا تُحمِر حارس الإنتاج."""
    pkg = tmp_path / "services"
    pkg.mkdir()
    (pkg / "test_thing.py").write_text(
        'def f(ctx):\n    return ctx.require("a.ghost")\n', encoding="utf-8"
    )
    files = guard.scan_files(tmp_path, ("services",), tmp_path / "shared" / "knowledge")
    assert files == []


def test_the_contract_directory_itself_is_excluded(tmp_path):
    """`shared/knowledge/` هو مُعرِّف الطبقة لا مستهلِكُها."""
    contracts = tmp_path / "shared" / "knowledge"
    contracts.mkdir(parents=True)
    (contracts / "c.py").write_text(
        'def f(ctx):\n    return ctx.require("a.ghost")\n', encoding="utf-8"
    )
    files = guard.scan_files(tmp_path, ("shared",), contracts)
    assert files == []


def test_no_declared_keys_fails_closed(tmp_path):
    """بلا عقدٍ مقروء يمرّ الحارس بلا أن يقيس شيئاً — وهو أخضرُ يكذب."""
    registry = tmp_path / "reg.json"
    registry.write_text(
        '{"schema": "sahool.knowledge_source_registry", "keys": [{"key": "a.k"}]}',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        guard.main(
            [
                "--registry",
                str(registry),
                "--contracts",
                str(tmp_path / "absent"),
                "--root",
                str(tmp_path),
            ]
        )


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--root", str(tmp_path)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_the_live_tree_actually_contains_a_resolver_request():
    """المسار الثاني — وهو أهمّ تأكيدٍ هنا.

    حارسٌ يمرّ بصفر طلبٍ لا يقيس شيئاً، وخضرتُه تُقرأ «لا مخالفة» وهي «لم
    يُطرَح سؤال». وقد كان ذلك حاله عند أوّل تشغيل.
    """
    declared = guard.declared_keys(guard.CONTRACT_DIR)
    files = guard.scan_files(guard.ROOT, guard.SCAN_DIRS, guard.CONTRACT_DIR)
    registered = {e["key"] for e in guard.load_keys(guard.REGISTRY)}
    problems, requests = guard.violations(registered, declared, files, guard.ROOT)
    assert problems == []
    assert requests >= 1, "لا طلبَ حقيقيّاً في الشجرة — الحارس لا يقيس شيئاً"


def test_a_keyword_argument_request_is_seen(tmp_path):
    """`ctx.require(key="…")` مسارُ تجاوزٍ حقيقيّ لو قُرِئت الوسائط الموضعيّة وحدها.

    و`require(self, key: str)` ليست positional-only، فالصيغة مشروعة تماماً — ولا
    يحتاج الالتفافُ نيّةً سيّئة: يكفي أن يكتبها أحدٌ هكذا. أمسكتها المراجعة.
    """
    files, root = _consumer(tmp_path, 'def f(ctx):\n    return ctx.require(key="a.other")\n')
    problems, requests = guard.violations(_REGISTERED, _DECLARED, files, root)
    assert requests == 1
    assert problems and "بلا إعلانٍ في أيّ عقد" in problems[0]


def test_a_positionally_declared_requirement_is_seen(tmp_path):
    """`KnowledgeRequirement("k", "sot")` — صنفُ بياناتٍ يقبل الموضعيّ.

    وقراءةُ المُسمّى وحده كانت تجعل الإعلان الموضعيّ غير مرئيّ، فيبدو الطلبُ
    المعتمِد عليه «غير مُعلَن» وهو مُعلَنٌ فعلاً.
    """
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "c.py").write_text(
        "from .contracts import KnowledgeRequirement\n"
        'R = KnowledgeRequirement("a.other", "sot_a")\n',
        encoding="utf-8",
    )
    assert "a.other" in guard.declared_keys(contracts)
