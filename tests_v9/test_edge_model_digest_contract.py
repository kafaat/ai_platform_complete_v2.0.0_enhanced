"""`EDGE-MODEL-DIGEST-CONTRACT-UNENFORCED-01` — عقدُ بصمة نماذج الحافّة يُربَط بطرفَيه.

**ما هذه الشواهد، وما ليست.** البصمةُ نفسُها مُنفَّذةٌ فعلاً وقتَ التشغيل: `model_artifact_gate`
يُجزّئ الملفّ ويقارنه بالمعتمد قبل كلّ استدلال، بأسبابٍ مسمّاة (`EDGE-MODEL-ARTIFACT-INTEGRITY-01`
مُغلَقة). فهذا الملفّ **لا يضيف بصمة** — يربط **العقدَ المُعلَن حولها** كي لا ينحرف صامتاً.

**المقيس الذي أوجده:** العقدُ مُعلَنٌ في موضعَين يدّعي كلٌّ منهما الوحدانيّة — بيانُ
`edge_models.required.json`، وخريطةُ `main.py:_MODEL_ENV` التي يقول تعليقُها «المصدرُ الواحد
للحكم». والحارسُ الحاجب `edge_model_contract_guard.py` يقرأ `env` و`default_path` فقط:

- `sha256_env` حقلٌ **مُعلَنٌ بلا إنفاذ** — صفرُ مراجع في `scripts/` و`tests_v9/`. فإعادةُ تسميته
  تجعل المُهيّئَ يقرأ متغيّراً غيرَ موجود، فتسقط القدرةُ مغلقةً **بصمت**. الإغلاقُ صواب،
  والصمتُ هو العطل.
- لا فحصَ **عكسيّ**: نموذجٌ يدخل `_MODEL_ENV` بلا صفٍّ في البيان يمرّ أخضر.
- والفحصُ بالاحتواء النصّيّ، فيُرضيه ذكرُ الاسم في تعليق — صنفُ «قارئٌ أضيقُ من دعواه».

فالقراءةُ هنا بشجرة النحو لا بالنصّ، والاتّجاهان مقيسان.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _compose_files() -> list[Path]:
    """`compose_files` من السطح المشترك، مُحمَّلاً بمساره **بلا تعديل `sys.path`**.

    `sys.path.insert` على مستوى الوحدة يبقى نافذاً بقيّةَ جلسة pytest، فيُقحِم ~٢٠٠ وحدةً
    من `scripts/ci` في فضاء الاستيراد لكلّ اختبارٍ يليه — وهو عينُ العطل الذي أُصلح في
    `tests_v9/service_module.py` اليوم (#1017): تلويثُ مسارٍ عامٍّ من أجل استيرادٍ محلّيّ.
    والعُرفُ القائم في `tests_v9` هو `spec_from_file_location`، فيُتَّبع.
    """
    spec = importlib.util.spec_from_file_location(
        "_compose_surface_for_edge_digest", ROOT / "scripts" / "ci" / "compose_surface.py"
    )
    assert spec and spec.loader, "تعذّر تحميل سطح compose المشترك"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.compose_files())


EDGE = ROOT / "services/edge-inference"
MANIFEST = EDGE / "models_manifest/edge_models.required.json"
EDGE_MAIN = EDGE / "main.py"
GATE = EDGE / "model_artifact_gate.py"


def _manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["required_models"]


def _ships_env(compose_text: str, env_name: str) -> bool:
    """يقبل صيغتَي compose كلتَيهما: خريطةً (``ENV: value``) وقائمةً (``- ENV=value``).

    البحثُ عن `"ENV:"` وحده يفوّت صيغةَ القائمة فيُنتج **حمرةً كاذبة** عند تمثيلٍ مختلف
    لنفس الحقيقة — وهو الوجهُ المقابل لِما يُقاس هنا (مراجعةُ #1022).
    """
    return (
        re.search(rf"^\s*-?\s*{re.escape(env_name)}\s*[:=]", compose_text, re.MULTILINE) is not None
    )


def _model_env_map() -> dict[str, tuple[str, str]]:
    """`_MODEL_ENV` مقروءةً من شجرة النحو — لا بالاحتواء النصّيّ ولا باستيراد الخدمة.

    الاستيرادُ يتطلّب تبعيّاتِ الخدمة، ولا وظيفةَ CI تُشغّل `services/edge-inference/tests`؛
    فالقراءةُ الساكنة هي ما يجعل هذا الشاهدَ يعمل حيث بوّابةُ الدمج فعلاً.
    """
    tree = ast.parse(EDGE_MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", "") == "_MODEL_ENV" for t in node.targets):
            continue
        assert isinstance(node.value, ast.Dict), "`_MODEL_ENV` لم يعد قاموساً حرفيّاً"
        out: dict[str, tuple[str, str]] = {}
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            assert isinstance(key, ast.Constant), "مفتاحٌ غيرُ حرفيّ في `_MODEL_ENV`"
            assert isinstance(value, ast.Tuple) and len(value.elts) == 2, (
                f"قيمةُ {key.value} ليست زوجاً (مسار · بصمة)"
            )
            path_env, sha_env = value.elts
            assert isinstance(path_env, ast.Constant) and isinstance(sha_env, ast.Constant)
            out[str(key.value)] = (str(path_env.value), str(sha_env.value))
        return out
    raise AssertionError("اختفت `_MODEL_ENV` من `main.py` — العقدُ فقد أحدَ طرفَيه")


def test_the_two_declarations_of_the_contract_agree_in_both_directions() -> None:
    """مصدران يدّعيان الوحدانيّة ⇒ يجب أن يتطابقا، وإلّا فأحدهما يكذب بصمت."""
    manifest = {Path(m["default_path"]).name: m for m in _manifest()}
    runtime = _model_env_map()

    missing_from_runtime = sorted(set(manifest) - set(runtime))
    assert not missing_from_runtime, (
        f"نماذجُ في البيان بلا ربطٍ في `_MODEL_ENV`: {missing_from_runtime} — "
        "تُعلَن مطلوبةً ولا يقرؤها التشغيل"
    )
    # الاتّجاهُ العكسيّ هو ما كان يفلت: الحارسُ القائم يمرّ على البيان ولا يعود منه.
    missing_from_manifest = sorted(set(runtime) - set(manifest))
    assert not missing_from_manifest, (
        f"نماذجُ في `_MODEL_ENV` بلا صفٍّ في البيان: {missing_from_manifest} — "
        "يُحمَّل نموذجٌ لا يعرفه العقدُ المُعلَن"
    )

    for filename, model in manifest.items():
        path_env, sha_env = runtime[filename]
        assert model["env"] == path_env, (
            f"{filename}: متغيّرُ المسار يختلف — البيان `{model['env']}` والتشغيل `{path_env}`"
        )
        assert model["sha256_env"] == sha_env, (
            f"{filename}: متغيّرُ البصمة يختلف — البيان `{model['sha256_env']}` "
            f"والتشغيل `{sha_env}`؛ المُهيّئُ سيقرأ متغيّراً لا يُصدِّره أحد فتسقط القدرةُ صامتة"
        )


def _gate_function(name: str) -> ast.AST:
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"اختفت `{name}` من المُهيّئ — العقدُ فقد حلقةً")


def test_the_declared_digest_name_is_threaded_end_to_end_into_the_environment_read() -> None:
    """السلسلةُ تُقاس حلقةً حلقة: `sha256_env` ⇐ `model_capability` ⇐ `expected_sha256` ⇐ `getenv`.

    **الصياغةُ الأولى كانت أضعفَ من دعواها** (مراجعةُ #1022): قبلت **أيَّ** `os.getenv` في الملفّ.
    فلو صار `expected_sha256` يقرأ اسماً ثابتاً — أو اسماً لا علاقة له بالمُمرَّر — لمرّت خضراء
    والعقدُ مقطوع. الربطُ الآن صريحٌ في الطرفين معاً، فلا تكفي مصادفةُ وجود نداء.
    """
    reader = _gate_function("expected_sha256")
    param = reader.args.args[0].arg
    threaded = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "getenv"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == param
        for node in ast.walk(reader)
    )
    assert threaded, (
        f"`expected_sha256` لم يعد يمرّر وسيطَه `{param}` إلى `os.getenv` — "
        "البصمةُ المعتمدة تُقرأ من مصدرٍ آخر، والاسمُ المُعلَن صار زينة"
    )

    caller = _gate_function("model_capability")
    passes_declared_name = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "expected_sha256"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "sha_env_name"
        for node in ast.walk(caller)
    )
    assert passes_declared_name, (
        "`model_capability` لم يعد يمرّر `sha_env_name` إلى `expected_sha256` — "
        "اسمُ البصمة المُعلَن في البيان لا يبلغ القراءةَ من البيئة"
    )


def test_every_surface_that_ships_a_model_path_also_ships_its_digest() -> None:
    """**كلُّ** سطحِ نشرٍ يشحن مساراً يجب أن يشحن بصمتَه — لا سطحٌ واحد يُقاس ويُدَّعى الباقي.

    **المقيس (كشفتْه مراجعةُ #1021 على سطحٍ مجاور، فقِيس هنا):** ثلاثةُ ملفّات compose تُعرّف
    `edge-inference`، والبصمةُ كانت تصل **واحداً** منها. و`docker-compose.light.yml` يشحن
    المسارَين ويُفعّل `AUTO_DOWNLOAD_MODELS` فوقهما، بينما `download_models.py:49` يرفض
    التنزيل بلا بصمةٍ صالحة — فلا يُنزَّل شيء، ويردّ كلُّ استدلالٍ 503 دائماً، ولا شيءَ في CI
    يقول ذلك لأنّ الحارس القائم يقرأ `docker-compose.v9.yml` وحدَه.

    **والصياغةُ الأولى لهذا الشاهد وقعت في العيب نفسِه**: اسمُها «تصل الحاوية» وقراءتُها ملفٌّ
    واحد. رابعُ ظهورٍ لصنف «قارئٌ أضيقُ من دعواه» في يومٍ واحد، وأوّلُ مرّةٍ يُكتشَف في شيفرتي
    قبل شحنها.

    **القاعدةُ مبدئيّة لا ترقيعيّة:** المسارُ يقول أين، والبصمةُ تقول هل يصلح؛ وفصلُهما هو عينُ
    عطل «الاسمُ يُفعِّل» الذي أُغلق في `EDGE-MODEL-ARTIFACT-INTEGRITY-01`. فمن يشحن الأوّلَ
    يشحن الثاني. وسطحٌ لا يشحن المسارَ أصلاً خارجَ القاعدة — لا يدّعي تشغيلَ النموذج.
    """
    surfaces = _compose_files()
    assert surfaces, "سطحُ compose المشترك فارغ — تغيّرت بنيةُ النشر، حدِّث هذا الشاهد"

    offenders: list[str] = []
    covered: list[str] = []
    for model in _manifest():
        path_env, sha_env = model["env"], model["sha256_env"]
        for surface in surfaces:
            text = surface.read_text(encoding="utf-8")
            if not _ships_env(text, path_env):
                continue  # لا يدّعي تشغيلَ هذا النموذج
            covered.append(f"{surface.name}:{path_env}")
            if not _ships_env(text, sha_env):
                offenders.append(f"{surface.name}: يشحن {path_env} بلا {sha_env}")

    assert covered, "لا سطحَ يشحن مسارَ نموذجٍ — تغيّرت البنية، حدِّث الشاهدَ لا الادّعاء"
    assert not offenders, (
        "أسطحُ نشرٍ تشحن المسارَ بلا البصمة — النموذجُ يُحمَّل بالاسم ولا يُحكَم عليه:\n  "
        + "\n  ".join(offenders)
    )


def test_no_declared_digest_value_is_committed_to_the_tree() -> None:
    """البيانُ يحمل **اسمَ** المتغيّر لا قيمته — قيمةٌ مُثبَتة تُجمّد وزناً لا يملكه المستودع."""
    raw = MANIFEST.read_text(encoding="utf-8")
    for model in _manifest():
        assert "expected_sha256" not in model and "sha256" not in {
            k for k in model if k != "sha256_env"
        }, f"{model['capability']}: ظهرت قيمةُ بصمةٍ في البيان — والوزنُ غيرُ مُزوَّدٍ بعقده"
    assert "packaged_in_repository" in raw
