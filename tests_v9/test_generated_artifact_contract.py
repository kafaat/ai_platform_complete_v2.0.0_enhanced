"""GENERATED-CHECK-IGNORES-ITS-OWN-COMPANION-ARTIFACTS-01 — حارس الحُرّاس.

العيب المقيس عند bbfe121f: ستّة حرّاس تُشغَّل بـ`--check` في workflows، و**١٣ من ١٦
مصنوعة يملكونها تُفسَد والفحص أخضر**. القياس كان بإفساد كلّ ملفّ على حدة ثمّ قراءة رمز
الخروج؛ والتكذيب بإعادة مصادرهم إلى HEAD أعاد الـ١٣ بالضبط، وبعد الوصل صار **صفراً من ١٦**.

**لماذا لا يُفسِد هذا الاختبار الملفّات كما فعل القياس؟** لأنّ إفساد ملفّات مُلتزَمة في
كلّ تشغيل وحدات — محليّاً وفي CI — يترك الشجرة موسَّخة إن قُتِل التشغيل بين الإفساد
والاستعادة (`finally` لا يُنقِذ من SIGKILL). فالخاصّيّة تُثبَّت هنا بثلاثة شروط
مجتمعة، كلٌّ منها قراءة صرفة، ومجموعها يُساوي ما قاسه الإفساد:

  ① `drift` نفسها ترصد **بايتاً واحداً** (مُبرهَن على `tmp_path`، لا على الشجرة).
  ② كلّ حارس يُمرّر إلى `drift`/`enforce` نتيجة استدعاء **`artifacts` الخاصّة به**،
     مُتحقَّقاً منه بشجرة AST لا بـgrep — فلا يكفي أن يستورد العقد ثمّ يقارن غيره.
  ③ مجموعة `artifacts` لكلّ حارس **مطابقة للعدد المُعلَن هنا** وخالية من الانحراف على
     الشجرة النظيفة — فتضييق المجموعة سرّاً (ترك `.csv` أو `.md`) يُسقِط الاختبار.

①+②+③ تُلزِم أنّ كلّ ملفّ يملكه الحارس يمرّ بمقارنة بايتيّة في مسار `--check`.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CI = os.path.join(_ROOT, "scripts", "ci")
if _CI not in sys.path:
    sys.path.insert(0, _CI)

# عدد المصنوعات التي يملكها كلّ حارس — مُعلَن كبيانات لا مُشتقّ من الشيفرة، وإلّا
# «أثبت» الاختبارُ ما يقيسه على نفسه: حارس يحذف رفيقاً من مجموعته يبقى أخضر لأنّ
# المتوقّع يتقلّص معه. الأرقام من القياس، ومجموعها ١٦.
OWNED = {
    "ai_container_contract_guard": 2,
    "capability_registry_v1": 5,
    "duplicate_definition_guard": 1,
    "platform_main_subinventory_guard": 3,
    "production_certification_checklist_guard": 3,
    "runtime_container_deep_contract_guard": 2,
}

_CONTRACT_SINKS = {"drift", "enforce"}


def _build(name):
    """مجموعة مصنوعات الحارس كما يبنيها هو — بمُدخَلاته لا بمُدخَلات مُختلَقة."""
    mod = importlib.import_module(name)
    if name in ("ai_container_contract_guard", "runtime_container_deep_contract_guard"):
        return mod.artifacts(mod.build_inventory())
    if name == "duplicate_definition_guard":
        return mod.artifacts(mod.build_payload())
    if name == "platform_main_subinventory_guard":
        return mod.artifacts(mod.inventory())
    if name == "production_certification_checklist_guard":
        return mod.artifacts()
    idx, _domains, caps = mod.load()
    return mod.artifacts(idx, caps)


def _sink_calls(name):
    """استدعاءات `drift`/`enforce` في مصدر الحارس، ومع كلٍّ: أهو على `artifacts(...)`؟"""
    tree = ast.parse(open(os.path.join(_CI, f"{name}.py"), encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        target = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
        if target not in _CONTRACT_SINKS:
            continue
        first = node.args[0] if node.args else None
        on_own = (
            isinstance(first, ast.Call)
            and isinstance(first.func, ast.Name)
            and first.func.id == "artifacts"
        )
        found.append((target, on_own))
    return found


def test_a_single_byte_of_corruption_is_seen_by_the_comparison_itself(tmp_path):
    """① الأساس: لو لم ترصد `drift` بايتاً، لصار كلّ ما فوقها زينة.

    مُبرهَن على `tmp_path` لا على الشجرة — الاختبار الذي يُفسِد ملفّاً مُلتزَماً ليقيس
    الحراسة يترك الشجرة موسَّخة إن قُتِل بين الإفساد والاستعادة.
    """
    from generated_artifact_contract import Artifact, drift, write_all

    path = tmp_path / "generated.json"
    art = [Artifact(path, '{"a": 1}\n')]

    write_all(art)
    assert drift(art) == [], "ملفّ كُتِب للتوّ لا يجوز أن يُقرأ منحرفاً"

    path.write_bytes(b'{"a": 1}\n ')  # مسافة واحدة زائدة
    assert drift(art), "بايت واحد يجب أن يُرى"

    path.unlink()
    assert drift(art), "الغياب انحراف أيضاً — لا «لا شيء يُقارَن»"


def test_a_missing_trailing_newline_is_not_forgiven_by_text_normalisation(tmp_path):
    """المقارنة بالبايت لا بالنصّ المُترجَم.

    ``read_text`` يُوحّد نهايات الأسطر، فيُخفي إفساداً حقيقيّاً في ملفّ CSV تنتهي
    أسطره بـCRLF — وهو الفخّ الذي أوقع `capability_linker` سابقاً.
    """
    from generated_artifact_contract import Artifact, drift

    path = tmp_path / "generated.csv"
    art = [Artifact(path, "a,b\r\n1,2\r\n")]

    path.write_bytes(b"a,b\r\n1,2\r\n")
    assert drift(art) == []

    path.write_bytes(b"a,b\n1,2\n")  # نفس النصّ بعد الترجمة، بايتات مختلفة
    assert drift(art), "ترجمة نهايات الأسطر لا يجوز أن تغفر إفساداً بايتيّاً"


def test_checking_never_repairs_what_it_is_checking(tmp_path):
    """CHECK-STEPS-MUTATE-THE-TREE-01: الفحص قراءة.

    مُضاف بعد تكذيب فاشل: جعلتُ `enforce` تكتب بلا شرط، وبقيت هذه الملفّة خضراء —
    فالخاصّيّة كانت مُدّعاة في التوثيق وغير محروسة. حارس يُصلح ما يفحصه لا يفحص شيئاً:
    يمرّ دائماً، ويترك الشجرة موسَّخة بفرق لا يقابله تغيير مصدر.

    فالشرطان معاً: يرفع الانحراف، و**يترك الملفّ المُفسَد كما هو**.
    """
    from generated_artifact_contract import Artifact, enforce

    path = tmp_path / "generated.json"
    art = [Artifact(path, '{"a": 1}\n')]

    enforce(art, write=True, label="probe")
    assert path.read_bytes() == b'{"a": 1}\n', "علم الكتابة يجب أن يكتب"

    path.write_bytes(b"corrupted")
    with pytest.raises(SystemExit) as raised:
        enforce(art, write=False, label="probe")

    assert path.read_bytes() == b"corrupted", "الفحص أصلح ما يفحصه — فلم يفحص شيئاً"
    assert "generated.json" in str(raised.value), "الانحراف يجب أن يُسمّي ملفّه"


@pytest.mark.parametrize("guard", sorted(OWNED))
def test_the_check_path_compares_the_guards_own_artifact_set(guard):
    """② الوصل مُتحقَّق بالبنية لا بالاستيراد.

    حارس يستورد العقد ثمّ يقارن مجموعة أخرى (أو مجموعة جزئيّة مبنيّة يدويّاً) يبقى
    «موصولاً» لأيّ فحص نصّيّ. الشرط الصادق: الوسيط الأوّل لـ`drift`/`enforce` هو
    استدعاء `artifacts(...)` نفسه.
    """
    calls = _sink_calls(guard)
    assert calls, f"{guard}: لا يستدعي drift/enforce إطلاقاً — لا يقارن مصنوعاته"
    assert any(on_own for _, on_own in calls), (
        f"{guard}: يستدعي {[c for c, _ in calls]} على مجموعة ليست artifacts(...) — "
        "قد يقارن أقلّ ممّا يملك"
    )


@pytest.mark.parametrize("guard", sorted(OWNED))
def test_every_artifact_the_guard_owns_is_declared_and_clean(guard):
    """③ المجموعة كاملة ومطابقة للشجرة.

    العدد مُعلَن كبيانات: حارس يُسقِط رفيقه `.csv` من مجموعته يُسقِط هذا الاختبار بدل
    أن يمرّ بمجموعة أصغر. والانحراف على شجرة نظيفة يعني مصنوعة مُلتزَمة بائتة.
    """
    from generated_artifact_contract import drift

    arts = _build(guard)
    assert len(arts) == OWNED[guard], (
        f"{guard}: يملك {len(arts)} مصنوعة والمُعلَن {OWNED[guard]}. "
        "إن كان التغيير مقصوداً فحدّث OWNED مع سبب مكتوب؛ وإن لم يكن فمصنوعة سقطت من الحراسة."
    )
    assert drift(arts) == [], (
        f"{guard}: مصنوعات مُلتزَمة لا تُطابق ما يُنتجه مولّدها — أعد التوليد بعلم الكتابة"
    )


def test_the_owned_counts_add_up_to_the_measured_total():
    """الرقم المُسجَّل في سجلّ الفجوات هو نفسه المفروض هنا — لا نسختان تتباعدان."""
    assert sum(OWNED.values()) == 16
    assert len(OWNED) == 6
