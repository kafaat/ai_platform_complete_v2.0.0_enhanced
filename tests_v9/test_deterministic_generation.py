"""`DETERMINISTIC-GENERATION-AND-MERGE-SAFETY-01` — الشطر L0: حتميّة المصنوعات.

**العلّة مقيسة على تاريخ هذا المستودع.** `release/SAHOOL_RELEASE_MANIFEST_20260626.json`
هو أكثر ملفّ حركةً في الشجرة (١٢٨ التزاماً منذ 2026-07-01)، وكان يكتب
`datetime.now(UTC).isoformat()` — ختماً بدقّة الميكروثانية من **ساعة الحائط**.

الأثر ليس «ضجيجاً في الفروق» بل **مولّد تعارض**: فرعان يُعيدان التوليد في لحظتين
مختلفتين يكتبان قيمتين مختلفتين في **نفس السطر**، فيتعارضان حتّى لو كانت الحمولة
متطابقة تماماً. ومع أربعة فروع متوازية في يوم واحد يصير التعارض حتميّاً لا محتملاً.

**وتصحيح لرقم ذكرتُه أنا:** قلتُ إنّ «٧٤ من ١٢٨ التزاماً غيّرت الختم فقط». التفصيل
الأدقّ بعد إعادة القياس: **٣** غيّرت `generated_at` **وحده**، و**٧١** غيّرته مع
`file_count`/`total_size_bytes` (أي حمولة تغيّرت فعلاً)، و**٥٢** غيّرت محتوى آخر.

**وتصويب أثقل من الرقم:** كتبتُ أنّ الإصلاح يجعل «إعادة التوليد على شجرة لم تتغيّر
حمولتها تُنتج صفر فرق». **لم يكن ذلك صحيحاً** كما نُفِّذ أوّلاً: الختم كان يُشتقّ من
`HEAD`، و`HEAD` يختلف بين فرعين بالضرورة — فبقي الفرعان يكتبان قيمتين مختلفتين في
نفس السطر. المُنجَز الفعليّ كان أضيق: إزالة اهتزاز الميكروثانية، وثبات القيمة على
**الالتزام نفسه**.

**ولماذا لم يمسكه هذا الملفّ:** كلّ اختبارات القبول أدناه تُثبّت `SOURCE_DATE_EPOCH`
صراحةً، فلا تعبر حدّ الالتزام أبداً ولا تستطيع رؤية الفرق. قياسٌ داخل ما افترضتُه —
وهو رابع وقوع في هذا الصنف بعينه في جلسة واحدة. الثلاثة الأخيرة في هذا الملفّ تُغلقه:
تبني مستودعاً حقيقيّاً بفرعين وتقيس الختم عبر الحدّ.

**ولا ارتداد إلى الساعة.** العقد الثلاثيّ في `scripts/ci/deterministic_time.py` يفشل
صراحةً بدل أن يعود إلى `time.time()`، لأنّ الارتداد الصامت يعمل في CI (حيث المتغيّر
مضبوط) وينهار عند المطوّر بلا رسالة تشرح لماذا انحرفت مصنوعته.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_CI = _ROOT / "scripts" / "ci"
sys.path.insert(0, str(_CI))

from deterministic_time import (  # noqa: E402
    DeterministicTimeUnavailable,
    generated_at_utc,
    source_epoch,
)

_MANIFEST = _ROOT / "release" / "SAHOOL_RELEASE_MANIFEST_20260626.json"
_BUILDER = _ROOT / "scripts" / "release" / "build_release_bundle.py"


def _executable_source(path: Path) -> str:
    """المصدر بلا تعليقات ولا سلاسل توثيق — ما **يُنفَّذ** لا ما يُشرَح.

    هذا ليس تجميلاً بل تصحيح عطل وقع **ثلاث مرّات في جلسة واحدة**: اختبارٌ يبحث عن
    نصّ محظور في الملفّ كلّه يُطلِق على التعليق الذي يشرح *لماذا* هو محظور. فيصير
    توثيق القاعدة انتهاكاً لها، ويُدرَّب الكاتب على حذف الشرح بدل إصلاح الفحص.

    التنفيذ على شجرة AST لا على regex: `#` داخل سلسلة نصّيّة ليس تعليقاً، ونزعه
    بالبحث النصّيّ يُنتِج عطلاً معاكساً.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ─────────────────────────── العقد نفسه ───────────────────────────


def test_the_environment_variable_wins_when_set(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert source_epoch() == 1700000000
    assert generated_at_utc() == "2023-11-14T22:13:20Z"


def test_git_history_is_the_second_source(monkeypatch):
    """بلا المتغيّر يُشتقّ الختم من آخر التزام — لا من الآن."""
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    expected = int(
        subprocess.run(
            ["git", "log", "-1", "--pretty=%ct"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
    )
    assert source_epoch(cwd=_ROOT) == expected


def test_it_fails_loudly_instead_of_falling_back_to_the_wall_clock(monkeypatch, tmp_path):
    """**التكذيب المحوريّ.** مجلّد بلا git وبلا المتغيّر ⇒ استثناء، لا `time.time()`.

    لو كان الارتداد إلى الساعة قائماً لَمرّ هذا الاختبار صامتاً وعادت اللاحتميّة كلّها.
    والرسالة تُسمّي العلاج (`SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct)`) لأنّ رفضاً
    لا يقول ماذا يفعل القارئ يُدرَّب على الالتفاف عليه.
    """
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    with pytest.raises(DeterministicTimeUnavailable) as excinfo:
        source_epoch(cwd=tmp_path)
    assert "SOURCE_DATE_EPOCH" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["not-a-number", "12.5", "-1", ""])
def test_an_invalid_stamp_is_rejected_not_ignored(monkeypatch, bad):
    """قيمة فاسدة تُرفَض. تجاهلها كان سيعيدنا إلى الساعة من الباب الخلفيّ."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", bad)
    with pytest.raises(ValueError):
        source_epoch()


def test_the_stamp_shape_is_pinned(monkeypatch):
    """`Z` بدقّة الثانية — شكلٌ واحد لا شكلان.

    `+00:00` و`Z` تعنيان اللحظة نفسها وتُنتجان **بايتات مختلفة**؛ وتثبيت الشكل جزء
    من الحتميّة لا تجميل. والدقّة بالثانية عمداً: الميكروثانية تأتي من ساعة الحائط.
    """
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    stamp = generated_at_utc()
    assert stamp.endswith("Z") and "+00:00" not in stamp
    assert stamp.count(":") == 2, "دقّة الثانية، بلا كسور"


# ─────────────────── المصنوعة الحقيقيّة، لا نموذج ───────────────────


def _build(env_extra: dict[str, str], out_dir: Path) -> bytes:
    """يُشغّل مولّد الحزمة الحقيقيّ ويكتب إلى **مجلّد مؤقّت**، لا إلى `release/`.

    أوّل صياغة بنَت إلى `release/` المتعقَّب، فكان تشغيل الجناح يُوسِّخ الشجرة —
    وهو `CHECK-STEPS-MUTATE-THE-TREE-01` عينه، أي فحصٌ يُعدِّل ما يفحصه. و`--root`
    يبقى المستودع الحقيقيّ (المولّد يُعدِّد الملفّات المتعقَّبة منه)، بينما
    `--release-dir` المطلق يُحوّل المخرَج بعيداً. لا ترميم بعديّ ولا `finally`:
    الكتابة لا تقع أصلاً.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **env_extra}
    result = subprocess.run(
        [sys.executable, str(_BUILDER), "--root", str(_ROOT), "--release-dir", str(out_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=900,
    )
    assert result.returncode == 0, f"build failed: {result.stderr[-800:]}"
    return (out_dir / _MANIFEST.name).read_bytes()


@pytest.mark.slow
def test_two_generations_are_byte_identical(tmp_path):
    """شرط القبول الأوّل: توليدان متتاليان ⇒ نفس SHA-256."""
    first = _build({"SOURCE_DATE_EPOCH": "1700000000"}, tmp_path / "a")
    second = _build({"SOURCE_DATE_EPOCH": "1700000000"}, tmp_path / "b")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert first == second


@pytest.mark.slow
def test_the_output_is_independent_of_timezone_and_locale(tmp_path):
    """شرط القبول الثاني: بيئتان مختلفتان جذريّاً ⇒ نفس البايتات.

    `TZ` و`LC_ALL` هما المتّجهان اللذان يُنتجان «يعمل عندي» الكلاسيكيّ: ختمٌ يُكتَب
    بتوقيت محلّيّ، أو ترتيبٌ يعتمد ترتيب المحارف في اللغة.
    """
    utc = _build({"SOURCE_DATE_EPOCH": "1700000000", "TZ": "UTC", "LC_ALL": "C"}, tmp_path / "utc")
    other = _build(
        {
            "SOURCE_DATE_EPOCH": "1700000000",
            "TZ": "Asia/Singapore",
            "LC_ALL": "en_US.UTF-8",
        },
        tmp_path / "sg",
    )
    assert hashlib.sha256(utc).hexdigest() == hashlib.sha256(other).hexdigest()


@pytest.mark.slow
def test_the_manifest_carries_no_timestamp_at_all(tmp_path):
    """`RELEASE-MANIFEST-SELF-REGENERATION-01`: البيان بلا زمنٍ إطلاقاً.

    **ولم يكن الختم ساعة حائط عند حذفه.** كان يُشتقّ من آخر التزام مسّ الحمولة،
    وحتميّاً عند رأسٍ ثابت. العيب أضيق: البيان يُولَّد **قبل** الالتزام الذي يحمله،
    فبعد التزامه يصير ذلك الالتزام «آخر تعديل للحمولة» وتكتب إعادةُ التوليد زمنه
    الجديد ⇒ المصنوعة **لا تطابق إعادة توليدها على التزامها نفسه** إلّا بدورة ذاتيّة.

    والحذف هو العلاج لا الاستثناء: الحقل بلا مستهلِك، ولا يمثّل وقت البناء الحقيقيّ
    أصلاً. ووقتُ البناء الفعليّ يذهب إلى `attested_at` **خارج** المصنوعة المُلتزَمة.
    """
    manifest = json.loads(_build({"SOURCE_DATE_EPOCH": "1700000000"}, tmp_path / "a").decode())
    assert "generated_at" not in manifest, "عاد الختم إلى مصنوعة تُلتزَم"
    assert not [k for k in manifest if "generated" in k or "_at" in k], (
        f"حقلٌ زمنيّ في البيان المُلتزَم: {sorted(manifest)}"
    )


@pytest.mark.slow
def test_the_manifest_is_byte_identical_under_any_source_epoch(tmp_path):
    """الخاصّيّة صارت **أقوى**: لا شيء في البيان يتبع الزمن، فلا متغيّر يُحرّكه.

    قبلها كان التأكيد «الختم وحده يتبع `SOURCE_DATE_EPOCH`»؛ والآن **البايتات كلّها
    ثابتة** مهما اختلف المتغيّر — وهي الخاصّيّة التي يفحصها شرط «الشجرة نظيفة بعد
    إعادة البناء» مباشرةً.
    """
    a = _build({"SOURCE_DATE_EPOCH": "1700000000"}, tmp_path / "a")
    b = _build({"SOURCE_DATE_EPOCH": "1600000000"}, tmp_path / "b")
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


# ────────────────── الحقول التي تُصنَع الآلة لا المصدر ──────────────────


def test_no_generated_artifact_stamps_the_checkout_directory():
    """`source_root` كان يطبع **اسم مجلّد السحب**، وله صفر قارئ في المستودع.

    مقيس أثناء العمل: التوليد داخل شجرة عمل اسمها `wt768` كتب `"source_root": "wt768"`
    في مصنوعة إصدار. حقلٌ بلا قارئ يسرّب البيئة ليس provenance بل ضجيج يتعارض — نفس
    صنف `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`.
    """
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert "source_root" not in payload
    assert "root.name" not in _executable_source(_BUILDER), "اسم مجلّد السحب لا يدخل مصنوعة"


def test_no_committed_generated_artifact_carries_a_wall_clock_stamp():
    """الإنفاذ العكسيّ: لا مصنوعة متعقَّبة تحمل ختماً بدقّة دون الثانية.

    الكسور العشريّة في ختم ISO لا تأتي إلّا من `datetime.now()`؛ فوجودها في ملفّ
    متعقَّب دليلٌ بنيويّ على عودة اللاحتميّة، بلا حاجة لقراءة المولّد.
    """
    import re

    tracked = subprocess.run(
        ["git", "ls-files", "--", "*.json"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    fractional = re.compile(r'"(?:generated_at|built_at)"\s*:\s*"20\d\d-\d\d-\d\dT[\d:]+\.\d+')
    offenders = []
    for rel in tracked:
        path = _ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if fractional.search(text):
            offenders.append(rel)
    assert not offenders, "مصنوعات تحمل ختم ساعة الحائط: " + " · ".join(offenders)


def test_a_generator_that_still_stamps_routes_through_the_contract():
    """المولّد الذي **ما زال يختم** يمرّ بالعقد — مُتحقَّق على المصدر لا على المخرَج."""
    src = _executable_source(_CI / "runtime_environment_preflight.py")
    assert "generated_at_utc" in src, "runtime_environment_preflight لا يمرّ بالعقد"
    assert "datetime.now(" not in src, "runtime_environment_preflight يقرأ ساعة الحائط"


def test_the_release_manifest_generator_stamps_nothing_at_all():
    """`build_release_bundle` خرج من العقد **بحذف الختم** لا بالالتفاف عليه.

    كان يمرّ بالعقد صحيحاً؛ ثمّ حُذِف `generated_at` في
    `RELEASE-MANIFEST-SELF-REGENERATION-01` لأنّ البيان يُولَّد **قبل** الالتزام الذي
    يحمله، فلا يطابق إعادة توليده على التزامه نفسه.

    فالتأكيد هنا **أقوى** من «يمرّ بالعقد»: لا ختمٌ أصلاً، ولا ساعةَ حائط — ولو عاد
    أحدهما لَعاد العطل، وهذا الاختبار هو ما يمنع عودته صامتةً.
    """
    src = _executable_source(_ROOT / "scripts" / "release" / "build_release_bundle.py")
    assert "datetime.now(" not in src, "عادت ساعة الحائط إلى مولّد البيان"
    assert "generated_at_utc(" not in src, "عاد الختم إلى مصنوعة تُلتزَم"


# ══════════════ الاختبار الذي كان غائباً فأفلت العطل ══════════════


def _git(repo: Path, *args: str, when: str | None = None) -> str:
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(repo),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    ).stdout.strip()


@pytest.fixture()
def two_branches(tmp_path, monkeypatch):
    """مستودع بفرعين **لا يمسّان الحمولة** — كلٌّ يُضيف مدخل دماغ فقط.

    هذه هي الحالة الحقيقيّة في هذا المستودع: جلستان تعملان بالتوازي، تُلحق كلٌّ
    بملفّات `sahool-brain/` ثمّ تُعيد التوليد.
    """
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    (repo / "payload.txt").write_text("real payload\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base", when="2020-01-01T00:00:00Z")
    base = _git(repo, "rev-parse", "HEAD")
    for name, when in (("A", "2021-01-01T00:00:00Z"), ("B", "2022-06-01T00:00:00Z")):
        _git(repo, "checkout", "-q", "-B", f"br{name}", base)
        # داخل الحلقة: git لا يتعقّب مجلّداً فارغاً، فـ`checkout` على القاعدة يمحوه.
        (repo / "brain").mkdir(exist_ok=True)
        (repo / "brain" / f"note_{name}.md").write_text(f"entry {name}\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"note {name}", when=when)
    return repo


def test_head_scoped_stamps_differ_between_branches(two_branches):
    """**العطل، مُعاد إنتاجه.** بنطاق `HEAD` يكتب الفرعان قيمتين مختلفتين.

    هذا ما كان عليه أوّل تنفيذ للعقد، وما زعمتُ أنّه يُزيل التعارض. الاختبار موجود
    ليبقى العطل مُقاساً لا موصوفاً — ولو أُعيد النطاق إلى `HEAD` لَسقط الاختبار
    التالي وبقي هذا أخضر، فيُقرأ الفرق فوراً.
    """
    _git(two_branches, "checkout", "-q", "brA")
    a = source_epoch(cwd=two_branches)
    _git(two_branches, "checkout", "-q", "brB")
    b = source_epoch(cwd=two_branches)
    assert a != b, "لو تساويا لَما كان هناك عطل أصلاً"


def test_payload_scoped_stamps_are_identical_across_branches(two_branches):
    """**الإصلاح.** فرعان لم يمسّا الحمولة ⇒ **نفس الختم** ⇒ صفر تعارض.

    هذا هو الادّعاء الذي كُتِب أوّلاً بلا اختبار يعبر حدّ الالتزام. اختبار القبول
    القائم يُثبّت `SOURCE_DATE_EPOCH` صراحةً، فلا يعبر ذلك الحدّ أبداً ولا يستطيع
    رؤية الفرق — قياسٌ داخل ما افترضه كاتبه.
    """
    scope = [".", ":(exclude)brain/"]
    _git(two_branches, "checkout", "-q", "brA")
    a = source_epoch(cwd=two_branches, payload=scope)
    _git(two_branches, "checkout", "-q", "brB")
    b = source_epoch(cwd=two_branches, payload=scope)
    assert a == b, f"الختم ما زال يتبع HEAD: {a} ≠ {b}"
    assert generated_at_utc(cwd=two_branches, payload=scope) == "2020-01-01T00:00:00Z"


def test_a_real_payload_change_does_move_the_stamp(two_branches):
    """وحدٌّ مقابل: الإصلاح لا يُجمّد الختم — تغيّر الحمولة **يجب** أن يُحرّكه.

    بلا هذا يمرّ إصلاحٌ يُعيد ثابتاً دائماً، وهو حتميّ وبلا معنى.
    """
    scope = [".", ":(exclude)brain/"]
    _git(two_branches, "checkout", "-q", "brA")
    before = source_epoch(cwd=two_branches, payload=scope)
    (two_branches / "payload.txt").write_text("changed\n", encoding="utf-8")
    _git(two_branches, "add", "-A")
    _git(two_branches, "commit", "-qm", "payload moved", when="2023-03-03T00:00:00Z")
    assert source_epoch(cwd=two_branches, payload=scope) > before


def test_the_release_payload_scope_is_derived_not_handwritten():
    """النطاق مُشتقّ من ثوابت المولّد — قائمتان تصفان الشيء نفسه تنحرفان."""
    sys.path.insert(0, str(_ROOT / "scripts" / "release"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("_brb", _BUILDER)
    brb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brb)
    scope = brb.payload_pathspec()
    for excluded in brb.EXCLUDE_DIRS:
        assert f":(exclude){excluded}/" in scope, f"{excluded} خارج نطاق الحمولة"
    for artifact in brb.SELF_GENERATED:
        assert f":(exclude){artifact}" in scope, f"{artifact} يُجزّئ نفسه"
    # `sahool-brain/` تحديداً: كلّ جلسة تُلحق به، فدخوله يُعيد العطل كاملاً.
    assert ":(exclude)sahool-brain/" in scope
