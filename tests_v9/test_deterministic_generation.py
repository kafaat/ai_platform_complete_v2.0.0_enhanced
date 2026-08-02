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
فالمكسب ليس «إلغاء ٧٤ التزاماً» بل خاصّيّة أقوى وأدقّ: **إعادة التوليد على شجرة لم
تتغيّر حمولتها تُنتج الآن صفر فرق بدل فرق سطريّ مضمون** — وهي الخاصّيّة التي تحوّل
«أعِد التوليد قبل الالتزام» من مصدر تعارض إلى عمليّة محايدة.

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
def test_the_stamp_follows_the_source_epoch_not_the_run(tmp_path):
    """تكذيب مباشر: تغيير `SOURCE_DATE_EPOCH` وحده يجب أن يُغيّر الختم — لا شيء غيره."""
    a = json.loads(_build({"SOURCE_DATE_EPOCH": "1700000000"}, tmp_path / "a").decode("utf-8"))
    b = json.loads(_build({"SOURCE_DATE_EPOCH": "1600000000"}, tmp_path / "b").decode("utf-8"))
    assert a["generated_at"] == "2023-11-14T22:13:20Z"
    assert b["generated_at"] == "2020-09-13T12:26:40Z"
    assert {k: v for k, v in a.items() if k != "generated_at"} == {
        k: v for k, v in b.items() if k != "generated_at"
    }, "لا شيء سوى الختم يتبع الزمن"


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


def test_both_known_stamped_generators_route_through_the_contract():
    """الحارسان المُصلَحان يستعملان العقد — مُتحقَّق على المصدر لا على المخرَج."""
    for script in (
        _ROOT / "scripts" / "release" / "build_release_bundle.py",
        _CI / "runtime_environment_preflight.py",
    ):
        src = _executable_source(script)
        assert "generated_at_utc" in src, f"{script.name} لا يمرّ بالعقد"
        assert "datetime.now(" not in src, f"{script.name} ما زال يقرأ ساعة الحائط"
