"""طزاجةٌ حتميّة بدل هويّة التزام — ``MEASURED-ON-SQUASH-FRESHNESS-01`` طور ١.

``measured_on`` **إشارةُ إسناد** لا سلطةَ طزاجة (GOV-01)، وذلك أُغلِق. لكنّ إبقاءه
وحده ترك سؤالاً بلا جواب: **متى يكون الـprovenance المنشور بائتاً والنتيجةُ مطابقة؟**
إعادةُ الاشتقاق تُجيب عن النتيجة ولا تُجيب عن الأساس — فيبقى ختمٌ قديم إلى الأبد
بحجّة أنّ الناتج لم يتغيّر.

فالعقد هنا **اقترانيّ لا بديل**::

    طازجٌ ⇔ تطابقَ measurement_basis_digest  **و**  تطابقت النتيجة المُعاد اشتقاقها

وإعادةُ الاشتقاق تبقى سلطةَ النتيجة كما كانت — لم يُنقَل إليها شيء.

**ولمَ ثلاثةُ مكوّنات لا واحد.** بصمةُ المدخلات وحدها تعمى عن أخطر الانحرافين:
تغيُّرِ منطقِ المولّد بمدخلاتٍ ثابتة — يتبدّل معنى الرقم بلا أثرٍ في مدخلاته. فالأساس
= H(نسخةُ العقد · بصمةُ المدخلات · بصمةُ الخوارزميّة).

**وحسّاسيّةُ كلّ بصمة مضبوطةٌ على حسّاسيّة ما تصفه:**

* المدخلات: بايتات — لأنّ نتيجة هذا القياس تحمل **أرقام أسطر**، فإزاحةُ سطرٍ تغيّر
  الناتج فعلاً. البايتات هنا ليست إفراطاً بل مطابقة.
* الخوارزميّة: AST مُجرَّدةً من التوثيق — تعديلُ شرحٍ لا يغيّر سلوكاً، وبصمةٌ خام
  كانت ستجعل كلّ إعادة صياغةٍ انحرافاً، وهو الـchurn الذي وُجِد العقد ليمنعه.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/tenant_guc_scope_guard.py"
BASELINE = ROOT / "docs/architecture/tenant_guc_scope_baseline.json"


def _guard():
    spec = importlib.util.spec_from_file_location("tenant_guc_basis", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source() -> str:
    return GUARD.read_text(encoding="utf-8")


# ── العقد مُعلَنٌ في المصنوعة ─────────────────────────────────────────────────


def test_the_published_baseline_carries_a_basis() -> None:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    for field in (
        "measurement_contract_version",
        "measurement_input_digest",
        "measurement_algorithm_digest",
        "measurement_basis_digest",
        "measurement_inputs",
    ):
        assert data.get(field), f"حقلُ الأساس غائب: {field}"


def test_the_published_basis_matches_a_fresh_re_derivation() -> None:
    """الشجرةُ الحاضرة تُنتِج الأساسَ المنشور نفسه — وإلّا فالمصنوعة بائتة."""
    module = _guard()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["measurement_basis_digest"] == module.basis_digest()


def test_the_basis_binds_all_three_components() -> None:
    """أساسٌ يُهمِل أحد مكوّناته يُعلِن تغطيةً لا يملكها."""
    module = _guard()
    ref = module.basis_digest("i", "a", 1)
    assert module.basis_digest("CHANGED", "a", 1) != ref
    assert module.basis_digest("i", "CHANGED", 1) != ref
    assert module.basis_digest("i", "a", 2) != ref


# ── ① HEAD وحده تغيّر ⇒ لا بيات ───────────────────────────────────────────────


def test_a_moved_head_alone_does_not_stale_the_basis(monkeypatch) -> None:
    """هذا هو جوهرُ الشريحة: الالتزام يتحرّك والأساسُ لا يتحرّك معه.

    فمع الدمج بـsquash لا يصير كلّ PR churn، ولا تُطارَد مساواةٌ غيرُ قابلة
    للتحقيق داخل الـPR أصلاً.
    """
    module = _guard()
    before = module.basis_digest()
    monkeypatch.setattr(module, "_head_sha", lambda: "0" * 40)
    assert module.basis_digest() == before


def test_the_commit_stamp_is_not_an_input_to_the_basis() -> None:
    """`measured_on` لا يدخل الحساب — وإلّا عاد الالتزامُ سلطةَ طزاجةٍ من الباب الخلفيّ."""
    module = _guard()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert module.basis_digest() != data["measured_on"]
    assert data["measured_on"] not in (
        data["measurement_input_digest"],
        data["measurement_algorithm_digest"],
        data["measurement_basis_digest"],
    )


# ── ② تغييرٌ توثيقيّ محض ⇒ لا بيات ────────────────────────────────────────────


def test_a_docs_only_change_does_not_stale_the_algorithm_digest() -> None:
    module = _guard()
    src = _source()
    base = module._algorithm_digest(src)
    commented = src.replace("_SCAN_DIRS = (", "# شرحٌ جديد لا يغيّر سلوكاً\n_SCAN_DIRS = (", 1)
    assert commented != src
    assert module._algorithm_digest(commented) == base


def test_a_rewritten_docstring_does_not_stale_the_algorithm_digest() -> None:
    """التوثيقُ يُنزَع قبل البصم: نصٌّ يصف ولا يُنفَّذ."""
    module = _guard()
    src = _source()
    old = '"""يُرجِع (المخالفات، أسماء الـGUC المرصودة). مخالفة = ``true`` خارج معاملة."""'
    assert src.count(old) == 1
    rewritten = src.replace(old, '"""نصٌّ آخر تماماً يصف الشيء نفسه."""', 1)
    assert module._algorithm_digest(rewritten) == module._algorithm_digest(src)


# ── ③ منطقُ المولّد تغيّر ⇒ بيات ولو ثبتت المدخلات ────────────────────────────


def test_changed_generator_logic_stales_the_basis_with_inputs_untouched() -> None:
    """الحالةُ التي تعمى عنها بصمةُ المدخلات وحدها — وهي سببُ وجود المكوّن الثاني.

    يتبدّل معنى الرقم ولا يتحرّك أيُّ مُدخَل، فبصمةُ مدخلاتٍ منفردة تشهد بالطزاجة
    وهي لم تقس ما تبدّل.
    """
    module = _guard()
    src = _source()
    old = 'if is_local != "true":'
    assert src.count(old) == 1
    mutated = src.replace(old, 'if is_local != "false":', 1)
    assert module._algorithm_digest(mutated) != module._algorithm_digest(src)
    inputs = module._input_digest()
    assert module.basis_digest(inputs, module._algorithm_digest(mutated)) != module.basis_digest(
        inputs, module._algorithm_digest(src)
    )


# ── ④ مُدخَلٌ أصيل تغيّر ⇒ بيات ───────────────────────────────────────────────


def test_a_changed_authoritative_input_stales_the_input_digest() -> None:
    module = _guard()
    manifest = module._input_manifest()
    assert manifest, "جردُ المدخلات فارغ — الاختبار يقيس شجرةً تغيّرت تحته"
    tampered = [dict(e) for e in manifest]
    tampered[0]["sha256"] = "0" * 64
    assert module._input_digest(tampered) != module._input_digest(manifest)


def test_only_inputs_that_reach_the_measurement_are_in_the_manifest() -> None:
    """١٥٣٥ ملفّاً يُمسَح و٣٩ يصل القياس. بصمُ الكلّ يُعيد بناء الدوّامة نفسها:

    تعديلُ ملفٍّ لا يمسّ القياس يُبيت الأساس، فيصير الـregeneration ضريبةً دائمة —
    وهي بالضبط العلّة التي هرب منها هذا العقد، بصورة hash مختلفة.
    """
    module = _guard()
    manifest = module._input_manifest()
    scanned = module._iter_source_files()
    assert len(manifest) < len(scanned) / 10, (
        f"الجرد {len(manifest)} من {len(scanned)} — اتّسع حتّى صار الشجرةَ نفسها"
    )
    for entry in manifest:
        raw = (ROOT / entry["path"]).read_bytes()
        assert b"set_config" in raw, f"مُدخَلٌ لا يصل القياس: {entry['path']}"


def test_the_generator_is_not_counted_as_its_own_input() -> None:
    """مصدرُ الحارس خوارزميّةٌ لا مُدخَل.

    وعدُّه مرّتين بقاعدتَي حسّاسيّة مختلفتين (بايتات للمدخلات · AST للخوارزميّة)
    يُبطِل تطبيعَ التوثيق: تعديلُ تعليقٍ فيه كان سيصير انحرافَ **مدخلات**.
    """
    module = _guard()
    paths = {e["path"] for e in module._input_manifest()}
    assert "scripts/ci/tenant_guc_scope_guard.py" not in paths


# ── ⑤ تطبيعُ الترتيب والمسارات ────────────────────────────────────────────────


def test_the_manifest_is_canonically_ordered_and_relative() -> None:
    module = _guard()
    manifest = module._input_manifest()
    assert [e["path"] for e in manifest] == sorted(e["path"] for e in manifest)
    for entry in manifest:
        assert not entry["path"].startswith("/"), entry["path"]
        assert str(ROOT) not in entry["path"], "مسارٌ مطلق يجعل البصمة تختلف بين آلتين"


def test_reordering_the_manifest_does_not_change_the_digest() -> None:
    """ترتيبُ الاكتشاف تفصيلُ نظام ملفّات، لا خاصّيّةٌ من خواصّ القياس."""
    module = _guard()
    manifest = module._input_manifest()
    assert module._input_digest(list(reversed(manifest))) == module._input_digest(manifest)


def test_no_timestamp_or_mtime_enters_the_basis() -> None:
    """زمنٌ في البصمة يُنتِج انحرافاً لا يصف شيئاً — ويختلف بين آلتين على نفس الشيفرة."""
    module = _guard()
    assert module._input_digest() == module._input_digest()
    assert module.basis_digest() == module.basis_digest()
    source = _source()
    body = source[source.index("def _input_manifest(") :]
    for banned in ("st_mtime", "time.time", "datetime", "st_ctime"):
        assert banned not in body, f"{banned} داخل حساب الجرد"


def test_the_stored_manifest_agrees_with_a_fresh_one() -> None:
    module = _guard()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["measurement_inputs"] == module._input_manifest()
    assert data["measurement_input_digest"] == module._input_digest()


# ── ⑥ تصنيفُ `--check`: بياتُ إسنادٍ مقابل انحرافٍ دلاليّ ──────────────────────


def _run(module, monkeypatch, tmp_path, baseline: dict, capsys):
    import sys as _sys

    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(module, "BASELINE", path)
    monkeypatch.setattr(_sys, "argv", ["tenant_guc_scope_guard.py", "--check"])
    code = module.main()
    return code, capsys.readouterr().out


def _current(module) -> dict:
    offenders, guc = module.scan()
    return {
        "measured_on": "0" * 40,
        "measurement_contract_version": module.CONTRACT_VERSION,
        "measurement_input_digest": module._input_digest(),
        "measurement_algorithm_digest": module._algorithm_digest(),
        "measurement_basis_digest": module.basis_digest(),
        "offenders": sorted(module._key(o) for o in offenders),
        "guc_names": sorted(guc),
    }


def test_matching_basis_and_matching_result_passes(monkeypatch, tmp_path, capsys) -> None:
    module = _guard()
    code, out = _run(module, monkeypatch, tmp_path, _current(module), capsys)
    assert code == 0, out
    assert "tenant_guc_scope_ok" in out


def test_a_changed_basis_with_an_identical_result_is_provenance_only(
    monkeypatch, tmp_path, capsys
) -> None:
    """يُحجَب لأنّ المنشور يحتاج تحديثاً — **ولا يُصنَّف انحداراً وظيفيّاً**.

    ولا يمرّ صامتاً: مروره كان سيُبقي provenance قديماً إلى الأبد بحجّة أنّ
    النتيجة نفسها، وهو ما وُجِد العقد ليمنعه.
    """
    module = _guard()
    baseline = _current(module)
    baseline["measurement_basis_digest"] = "f" * 64
    code, out = _run(module, monkeypatch, tmp_path, baseline, capsys)
    assert code == 1
    assert "PROVENANCE_STALE" in out
    assert "مواضع جديدة" not in out, "صُنِّف انحرافاً دلاليّاً وهو تجديدُ إسناد"


def test_a_changed_result_is_semantic_drift_and_outranks_provenance(
    monkeypatch, tmp_path, capsys
) -> None:
    """انحرافُ النتيجة يبقى الحكم الأوّل — والأساسُ لا يحجب مكانه ولا يُخفيه."""
    module = _guard()
    baseline = _current(module)
    baseline["offenders"] = ["ملفٌّ لا وجود له::سطر"]
    baseline["measurement_basis_digest"] = "f" * 64
    code, out = _run(module, monkeypatch, tmp_path, baseline, capsys)
    assert code == 1
    assert "مواضع جديدة" in out
    assert "PROVENANCE_STALE" not in out


def test_a_tampered_stored_digest_is_detected(monkeypatch, tmp_path, capsys) -> None:
    """بصمةٌ مُحرَّرة يدويّاً لا تشتري خضرة — وإلّا صارت المصنوعة تُصادِق نفسها."""
    module = _guard()
    baseline = _current(module)
    baseline["measurement_basis_digest"] = module.basis_digest("مزوّر", "مزوّر")
    code, out = _run(module, monkeypatch, tmp_path, baseline, capsys)
    assert code == 1
    assert "PROVENANCE_STALE" in out


def test_a_missing_digest_is_an_explicit_migration_state_not_implicit_freshness(
    monkeypatch, tmp_path, capsys
) -> None:
    """غيابُ البصمة **لا** يُقرأ تطابقاً — وهو نفس عطل «يفشل مفتوحاً» في صنفٍ آخر."""
    module = _guard()
    baseline = _current(module)
    del baseline["measurement_basis_digest"]
    code, out = _run(module, monkeypatch, tmp_path, baseline, capsys)
    assert code == 1
    assert "حالةُ هجرةٍ صريحة" in out


def test_the_contract_version_is_part_of_the_stored_artifact() -> None:
    """ترقيةُ العقد يجب أن تُبيت الأساس القديم، وإلّا قُرِئ رقمٌ بعقدٍ آخر."""
    module = _guard()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert data["measurement_contract_version"] == module.CONTRACT_VERSION


# ── ⑦ حدُّ الطور الأوّل مُعلَن ────────────────────────────────────────────────


def test_the_contract_is_not_yet_generalised_beyond_this_one_artifact() -> None:
    """طورٌ أوّل بالقصد: لا تُفرَض بدائيّةٌ عامّة قبل إثبات تطابق العقود.

    و`claim_base_guard` **لا يتقاسم هذه الدلالة**: هو يتحقّق أنّ المصنوعات تحمل
    أختامَ أساسٍ ويصنّفها، ولا يُنتِج قياساً يُعاد اشتقاقه. فتوحيدُهما في بدائيّةٍ
    واحدة كان سيوحّد ما ليس واحداً.
    """
    claim_base = (ROOT / "scripts/ci/claim_base_guard.py").read_text(encoding="utf-8")
    assert "measurement_basis_digest" not in claim_base, (
        "امتدّ عقدُ الأساس إلى `claim_base_guard` قبل إثبات تطابق الدلالتين. "
        "وهما ليستا واحدة: هذا يُنتِج قياساً يُعاد اشتقاقه، وذاك يتحقّق أنّ "
        "المصنوعات تحمل أختاماً ويصنّفها. تعميمٌ سابقٌ لأوانه على ٧٠ مولّداً "
        "يفرض عقداً واحداً على عقودٍ لم تُقَس بعد."
    )
    assert "def scan(" not in claim_base, (
        "`claim_base_guard` اكتسب ماسحاً — فصار يُنتِج قياساً بعد أن كان يصنّف "
        "أختامه. وعندها يلزمه عقدُ الأساس نفسه، ولا يصحّ أن يبقى خارجه بحجّة الطور."
    )


# ── ⑧ شاهدان مباشران على حدَّي التطبيع ──────────────────────────────────────


def test_a_semantic_literal_change_stales_the_algorithm_digest() -> None:
    """حدُّ التطبيع من الأعلى: ثابتٌ يدخل القياس **ليس** توثيقاً.

    تطبيعٌ مفرط يبتلع الثوابت يجعل البصمة تُجيز تغييراً يقلب ما يُقاس أصلاً —
    فتفقد صلاحيّتها سلطةً. و`_SCAN_DIRS` تُحدّد **أيّ شجرةٍ تُمسَح**، فتغييرها
    تغييرُ القياس نفسه لا وصفِه.
    """
    module = _guard()
    src = _source()
    old = '_SCAN_DIRS = ("services", "shared", "agents", "scripts", "bots")'
    assert src.count(old) == 1
    mutated = src.replace(old, '_SCAN_DIRS = ("services", "shared", "agents", "scripts")', 1)
    assert module._algorithm_digest(mutated) != module._algorithm_digest(src)
    # والمدخلاتُ لم تتحرّك: الخوارزميّةُ وحدها هي التي أبَاتت الأساس.
    inputs = module._input_digest()
    assert module.basis_digest(inputs, module._algorithm_digest(mutated)) != module.basis_digest(
        inputs, module._algorithm_digest(src)
    )


def test_a_measured_on_only_change_leaves_the_check_verdict_identical(
    monkeypatch, tmp_path, capsys
) -> None:
    """الشاهدُ المباشر الأقوى على أنّ `measured_on` فقد سلطته — **حكماً لا بصمةً**.

    ثباتُ الأساس وحده يُثبِت أنّ الختم خارج الحساب؛ ولا يُثبِت أنّه خارج **القرار**.
    فقد يعود من الباب الخلفيّ كفرعٍ في `--check`. لذلك يُقاس هنا رمزُ الخروج
    والمخرَج معاً: الختمُ وحده يتبدّل، وكلّ ما عداه ثابت، والحكم لا يتحرّك.
    """
    module = _guard()
    fresh = _current(module)

    fresh["measured_on"] = module._head_sha()
    rc_current, out_current = _run(module, monkeypatch, tmp_path, fresh, capsys)

    stale = dict(fresh)
    stale["measured_on"] = "0" * 40
    assert stale["measurement_basis_digest"] == fresh["measurement_basis_digest"], (
        "الختمُ حرّك الأساس — فهو داخلٌ في الحساب"
    )
    rc_stale, out_stale = _run(module, monkeypatch, tmp_path, stale, capsys)

    assert rc_current == 0, out_current
    assert rc_stale == rc_current, "الختمُ وحده قلب الحكم — فهو ما يزال سلطةَ طزاجة"
    assert out_stale == out_current, "الختمُ وحده غيّر المخرَج — فهو مقروءٌ في مسار القرار"
