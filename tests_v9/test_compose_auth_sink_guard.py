"""`SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01` — الخاصّيّة، لا شكلُ النصّ.

**ولمَ عقدٌ ثانٍ بدل توسيع الأوّل:** `compose_no_default_secrets_guard` يفرض «لا
سرَّ افتراضيّ منشور». والخاصّيّة هنا «سرٌّ يحكم تفعيلَ استيثاق خادم لا تصل قيمتُه
فارغةً». والعقدان يتقاطعان ولا يتطابقان: `${VAR:-}` الفارغة تُرضي ذاك وتنتهك هذا،
والقيمةُ الحرفيّة تنتهك الاثنين **لسببين مختلفين**.

**والفرق القانونيّ مقيسٌ حيّاً** بـ`docker compose config` لا مأخوذٌ من وثيقة:

  ``${V?e}``   ⇒ required to exist            — ويقبل الفارغ
  ``${V:?e}``  ⇒ required to exist AND non-empty

فوجودُ `?` في التعبير ليس شاهداً على fail-closed. هذا الفرقُ حرفٌ واحد، وعليه
يقوم العقد كلُّه.

فحص صرف + مِسبار `compose` حين تتوفّر الأداة — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "compose_auth_sink_guard.py"
SINKS = ROOT / "docs" / "architecture" / "compose_auth_sinks.json"
SINK = "QDRANT__SERVICE__API_KEY"


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_a_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_a_{name}"] = module
    spec.loader.exec_module(module)
    return module


guard = _load("compose_auth_sink_guard")
surface = _load("compose_surface")


def _compose_available() -> bool:
    """يُنفَّذ عند **جمع** الاختبارات — فيُحاط بمهلةٍ والتقاطِ خطأ.

    عميلُ docker عالقاً أو بطيئاً كان سيُعلِّق الجمعَ كلَّه لا هذا الملفّ وحده،
    وهو إخفاقٌ يقرؤه القارئ «الجناح معطَّل» لا «الأداة غائبة». رفعتها مراجعةٌ
    خارجيّة وأصابت. والسلوك لا يتغيّر: `False` عند عدم التوفّر.
    """
    if not shutil.which("docker"):
        return False
    try:
        probe = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


needs_compose = pytest.mark.skipif(
    not _compose_available(), reason="docker compose غير متاح — المِسبار الحيّ لا يُحاكى"
)


def _config(tmp_path: Path, value: str, env: dict[str, str]) -> int:
    """يكتب مِسباراً بقيمةٍ واحدة ويُرجِع رمزَ خروج `docker compose config`."""
    probe = tmp_path / "docker-compose.probe.yml"
    probe.write_text(
        f"services:\n  q:\n    image: alpine\n    environment:\n      {SINK}: {value}\n",
        encoding="utf-8",
    )
    environ = {k: v for k, v in os.environ.items() if k != "QDRANT_API_KEY"}
    environ.update(env)
    return subprocess.run(
        ["docker", "compose", "-f", str(probe), "config"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environ,
    ).returncode


def _guard_sees(tmp_path, monkeypatch, value: str, name: str = "probe") -> bool:
    """أيُدين الحارسُ هذه القيمة لو وردت في ملفّ compose على السطح؟"""
    probe = tmp_path / f"docker-compose.{name}.yml"
    probe.write_text(
        f"services:\n  q:\n    image: alpine\n    environment:\n      {SINK}: {value}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "compose_files", lambda: [probe])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    return f"docker-compose.{name}.yml::{SINK}" in [key for key, _ in guard.findings()]


# ── عقد الاستيفاء: مقيسٌ بـcompose الحيّة، الحالات الثلاث ────────────────────


@needs_compose
def test_unset_secret_is_rejected(tmp_path):
    assert _config(tmp_path, "${QDRANT_API_KEY:?QDRANT_API_KEY required}", {}) != 0


@needs_compose
def test_empty_secret_is_rejected(tmp_path):
    """العمودُ الحاسم: الفارغُ لا الغائب.

    `${V?msg}` تحجب الغائب أيضاً، فاختبارٌ يقيس الغياب وحده يمرّ عليها ويترك
    الثغرة قائمة. هذا هو الاختبار الذي يفصل الصيغتين.
    """
    assert (
        _config(tmp_path, "${QDRANT_API_KEY:?QDRANT_API_KEY required}", {"QDRANT_API_KEY": ""}) != 0
    )


@needs_compose
def test_nonempty_secret_is_accepted(tmp_path):
    assert (
        _config(
            tmp_path,
            "${QDRANT_API_KEY:?QDRANT_API_KEY required}",
            {"QDRANT_API_KEY": "non-empty-test-value"},
        )
        == 0
    )


@needs_compose
def test_the_question_mark_without_colon_lets_an_empty_value_through(tmp_path):
    """أساسُ العقد كلِّه، مقيسٌ لا مرويّ — ولولاه لكان `?` علاجاً مقبولاً."""
    assert _config(tmp_path, "${QDRANT_API_KEY?required}", {"QDRANT_API_KEY": ""}) == 0


@needs_compose
def test_the_adopted_form_still_validates_the_real_unified_stack():
    """`:?` لا تكسر المكدّس الحقيقيّ — الخدمة ليست خلف profile.

    القياسُ الذي فرض `:-` الفارغة في مواضع أخرى (الاستيفاء يسبق ترشيح الـprofiles)
    لا ينطبق هنا، وهذا يُثبِته على الملفّ نفسه لا على مِسبار.
    """
    env = dict(os.environ)
    env["QDRANT_API_KEY"] = "probe-key"
    result = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.unified.yml", "config", "--quiet"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        env=env,
    )
    assert "QDRANT_API_KEY" not in (result.stderr or ""), (
        f"المكدّس الموحَّد يشكو من المفتاح رغم ضبطه: {result.stderr[:400]}"
    )


# ── ما يجب أن يمسكه الحارس — كلُّ صيغةٍ على حدة ──────────────────────────────


@pytest.mark.parametrize(
    ("value", "must_be_caught", "note"),
    [
        ('"${QDRANT_API_KEY}"', True, "استيفاءٌ عارٍ"),
        ('"${QDRANT_API_KEY?required}"', True, "`?` تقبل الفارغ"),
        ('"${QDRANT_API_KEY:-}"', True, "`:-` فارغة"),
        ('"${QDRANT_API_KEY-default}"', True, "`-` بلا نقطتين"),
        ('"test_qdrant_key"', True, "حرفيّةٌ في تركيبٍ بلا استثناء"),
        ('"${QDRANT_API_KEY:-fallback}"', True, "غيرُ فارغ لكنّه سرٌّ منشور"),
        ('"${QDRANT_API_KEY:?required}"', False, "الصيغةُ المقبولة وحدها"),
        ("${QDRANT_API_KEY:?QDRANT_API_KEY required}", False, "بلا اقتباس — مقبولةٌ كذلك"),
    ],
)
def test_the_guard_catches_every_form_that_does_not_prove_required_and_nonempty(
    tmp_path, monkeypatch, value, must_be_caught, note
):
    """المقيسُ الخاصّيّة: `required AND non-empty`، لا «فيه علامة استفهام».

    ولذلك تُدان `${V:-fallback}` رغم أنّها **لا** تؤول إلى الخالي: «غير فارغ»
    شرطٌ لازم لا كافٍ لمصرف استيثاق — والافتراضيُّ المنشور سرٌّ يعرفه كلّ قارئ.
    """
    assert _guard_sees(tmp_path, monkeypatch, value) is must_be_caught, note


def test_an_unregistered_key_is_not_condemned_for_its_name(tmp_path, monkeypatch):
    """لا نمط `.*API_KEY` — التعميم يحتاج قياساً لكلّ خدمة لا تشابهَ أسماء.

    `VLLM_API_KEY` اعتمادُ عميلٍ اختياريّ: إدانتُه تكسر مكدّساً يعمل بلا مزوّدٍ
    خارجيّ بحقّ، وتُدرِّب الكاتب على تجاهل الحارس.
    """
    probe = tmp_path / "docker-compose.probe.yml"
    probe.write_text(
        'services:\n  s:\n    image: alpine\n    environment:\n      VLLM_API_KEY: "${VLLM_API_KEY:-}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "compose_files", lambda: [probe])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    assert guard.findings() == []
    assert "VLLM_API_KEY" not in guard._sinks()


# ── شهودُ `GUARD-SCOPE-COMPLETENESS` الخمسة ──────────────────────────────────


def test_the_surface_is_shared_and_declares_its_source():
    witness = surface.discovery_witness()
    assert witness["universe_source"].startswith("git ls-files"), (
        "السطح يُشتقّ من git — والمشاركة مع الحارس الآخر هي ما يمنع تعريفين ينحرفان"
    )
    assert witness["discovered_paths"], "سطحٌ فارغ يمرّ أخضر عن سؤالٍ لم يُطرَح"


def test_the_discovered_set_equals_the_git_tracked_set_exactly():
    tracked = subprocess.run(
        ["git", "ls-files", "--", "docker-compose*.yml", "frontend/docker-compose*.yml"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    ).stdout.split()
    expected = set(tracked) - set(surface.EXCLUSIONS)
    discovered = {str(p.relative_to(ROOT)) for p in surface.compose_files()}
    assert discovered == expected, (
        f"لم يُرَ: {sorted(expected - discovered)} · رُئي بلا تعقّب: {sorted(discovered - expected)}"
    )


def test_the_stack_that_carried_the_defect_is_on_the_surface():
    """شاهدٌ مُسمّىً على الملفّ بعينه — لا تساوي مجموعاتٍ يمرّ بها القارئ.

    تساوي المجموعات يكشف خروجَه، لكنّ من يقرأ العقد يستحقّ سطراً يقول الاسم:
    الملفّ الذي حمل العطل يجب أن يبقى مفحوصاً.
    """
    discovered = {str(p.relative_to(ROOT)) for p in surface.compose_files()}
    assert "docker-compose.unified.yml" in discovered, (
        "المكدّس الذي حمل العطل خرج من سطح الاكتشاف — الحارس يصير حارسَ لا شيء"
    )


def test_the_guard_actually_scanned_the_stack_that_carried_the_defect():
    """«لم يجد» ليست «لم ينظر» — وهما متطابقتان في الخضرة.

    `docker-compose.unified.yml` مطابقٌ الآن فلا يُنتِج انتهاكاً، فلا يمكن أن
    يُقاس من `findings()` أنّه فُحِص. ولو خرج من سطح الفاحص لبقي كلُّ شيءٍ أخضر
    بينما المكدّس الذي حمل العطل صار بلا حراسة. فيُقاس **ما مرّ عليه الفحص**.
    """
    assert "docker-compose.unified.yml" in guard.scanned_files(), (
        "المكدّس الذي حمل العطل خرج من سطح الفحص — الحارس أخضرُ عن سؤالٍ لم يُطرَح"
    )


def test_a_new_compose_file_carrying_the_sink_is_seen(tmp_path, monkeypatch):
    assert _guard_sees(tmp_path, monkeypatch, '"${QDRANT_API_KEY}"', name="probe"), (
        "ملفٌّ جديد على السطح بمصرفٍ منتهِك لم يُرَ — الحارس يفحص ما يعرفه لا ما يوجد"
    )


def test_a_registered_sink_that_vanishes_from_the_surface_blocks(tmp_path, monkeypatch):
    """اختفاءُ مصرفٍ مُسجَّل بلا تحديث العقد **يحجب** ولا يُبلَّغ فقط.

    حارسٌ لا يجد ما يفحص يبقى أخضر بلا معنى — وهو «أخضرُ عن سؤالٍ لم يُطرَح» في
    أنقى صوره.
    """
    empty = tmp_path / "docker-compose.empty.yml"
    empty.write_text("services:\n  s:\n    image: alpine\n", encoding="utf-8")
    monkeypatch.setattr(guard, "compose_files", lambda: [empty])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    assert guard.unmeasured_sinks() == [SINK]


@pytest.mark.parametrize(
    ("body", "case"),
    [
        (
            f"services:\n  s:\n    image: alpine\n    # كانت هنا {SINK} قبل حذف الخدمة\n",
            "اسمٌ باقٍ في تعليقٍ حرّ",
        ),
        (
            "services:\n  s:\n    image: alpine\n    environment:\n"
            f"      # {SINK}: ${{QDRANT_API_KEY:?x}}\n",
            "سطرُ إسنادٍ مُعطَّلٌ بـ`#`",
        ),
    ],
)
def test_a_sink_surviving_only_inside_a_comment_is_not_counted_as_live(
    tmp_path, monkeypatch, body, case
):
    """«حيّ» يُشتقّ من إسنادٍ فعليّ لا من ورودِ الاسم نصّاً.

    مطابقةُ substring على الملفّ كلِّه تعدّ التعليقَ حياةً، فتصمت عن اختفاءِ
    مصرفٍ مُسجَّل — وهي الخاصّيّة التي أُعلِنت حاجبةً في هذه الشريحة نفسها.
    وقِستُ الحالتين قبل الإصلاح فمرّتا **صامتتين**.
    """
    probe = tmp_path / "docker-compose.ghost.yml"
    probe.write_text(body, encoding="utf-8")
    monkeypatch.setattr(guard, "compose_files", lambda: [probe])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    assert guard.unmeasured_sinks() == [SINK], f"{case}: عُدَّ حياةً فلم يُبلَّغ عن اختفائه"


def test_liveness_and_violation_are_derived_from_one_source(tmp_path, monkeypatch):
    """السؤالان — «أهو حيّ؟» و«أهو منتهِك؟» — يمرّان بالاشتقاق نفسه.

    فلا يمكن أن يقول أحدُهما «موجود» والآخر «غير موجود» عن السطر ذاته، وهو
    الانحرافُ الذي أوجد الثقب.
    """
    probe = tmp_path / "docker-compose.probe.yml"
    probe.write_text(
        f'services:\n  q:\n    image: alpine\n    environment:\n      {SINK}: "${{QDRANT_API_KEY}}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "compose_files", lambda: [probe])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    assert guard.unmeasured_sinks() == [], "إسنادٌ فعليّ ومع ذلك أُعلِن مختفياً"
    assert [key for key, _ in guard.findings()] == [f"docker-compose.probe.yml::{SINK}"]


# ── الاستثناء التجريبيّ: مقيَّدٌ لا مُعمَّم ───────────────────────────────────


def test_the_test_stack_literal_is_allowed_only_by_a_scoped_exception():
    """الحرفيّةُ تُدان بالخاصّيّة، ويُرفَع عنها الحجب باستثناءٍ مُسمّى — لا بقاعدة.

    فلو حُذف المدخل عاد `docker-compose.test.yml` انتهاكاً؛ الإعفاء بيانٌ مراجَع
    لا فرعٌ في الشيفرة.
    """
    keys = {key for key, _ in guard.findings()}
    assert f"docker-compose.test.yml::{SINK}" in keys, (
        "القيمةُ الحرفيّة يجب أن تُدان أوّلاً — الاستثناء يرفع الحجب ولا يُلغي القياس"
    )
    assert f"docker-compose.test.yml::{SINK}" in guard._exceptions()
    assert guard.violations() == []


def test_every_exception_is_file_scoped_service_scoped_reasoned_and_non_production():
    entries = json.loads(SINKS.read_text(encoding="utf-8"))["exceptions"]["entries"]
    for key, entry in entries.items():
        assert "::" in key, f"استثناءٌ غير مقيَّدٍ بالملفّ والمتغيّر: {key}"
        assert str(entry.get("service", "")).strip(), f"استثناءٌ بلا خدمة: {key}"
        assert entry.get("non_production") is True, f"استثناءٌ بلا إقرار non_production: {key}"
        for field in ("reason", "owner", "expires_on"):
            assert str(entry.get(field, "")).strip(), f"استثناءٌ بلا {field}: {key}"


def test_an_exception_on_a_production_stack_is_refused(monkeypatch):
    """«لا يُعمَّم إلى الإنتاج» مفروضٌ بنيويّاً لا بالثقة في كاتب المدخل.

    فمدخلٌ يُعلِن `non_production: true` على مكدّسٍ إنتاجيّ يُرفَض رغم إعلانه —
    التصنيفُ يقوله السجلّ، لا المستفيدُ من الإعفاء.
    """
    monkeypatch.setattr(
        guard,
        "_exceptions",
        lambda: {
            f"docker-compose.unified.yml::{SINK}": {
                "service": "qdrant",
                "non_production": True,
                "reason": "مِسبار",
                "owner": "probe",
                "expires_on": "2027-01-01",
            }
        },
    )
    defects = guard.exception_defects()
    assert any("مكدّسٍ إنتاجيّ" in d for d in defects), (
        "استثناءٌ على مكدّسٍ إنتاجيّ مرّ — الإعفاء التجريبيّ عُمِّم إلى الإنتاج"
    )


def test_a_stale_exception_is_reported_so_the_list_can_only_shrink(monkeypatch):
    """المقيس **القدرة على الكشف**، لا حالةُ الشجرة اليوم."""
    monkeypatch.setattr(
        guard,
        "_exceptions",
        lambda: {
            "docker-compose.ghost.yml::QDRANT__SERVICE__API_KEY": {
                "service": "qdrant",
                "non_production": True,
                "reason": "مِسبار",
                "owner": "probe",
                "expires_on": "2027-01-01",
            }
        },
    )
    assert any("بائت" in d for d in guard.exception_defects()), (
        "مدخلٌ لا انتهاك يقابله لم يُرَ بائتاً — الإعفاء المؤقّت يصير أبديّاً بلا صاحب"
    )


# ── العقد على الشجرة الحيّة ──────────────────────────────────────────────────


def test_the_live_tree_proves_required_and_nonempty_for_every_sink():
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_unified_stack_uses_the_accepted_form():
    """شاهدٌ مباشر على العطل المُصلَح — لا يمرّ عبر الحارس.

    فلو عُطِّل الحارس كلُّه بقي هذا يقول إنّ الملفّ نفسه تغيّر.
    """
    lines = (ROOT / "docker-compose.unified.yml").read_text(encoding="utf-8").splitlines()
    # **أسطرُ الإسناد وحدها.** أوّل صياغةٍ عندي فحصت الملفّ كنصّ، فأدانت التعليقَ
    # الذي يقتبس الصيغة القديمة ليشرح ما أُصلِح — أي أنّها كانت تُعاقِب التوثيق،
    # وهو نمطٌ مُسجَّل في هذا المستودع: عدٌّ يُعاقِب الشرح يُدرِّب كاتبه على حذفه.
    assignments = [
        ln.split(":", 1)[1].strip()
        for ln in lines
        if ln.strip().startswith(f"{SINK}:") and not ln.strip().startswith("#")
    ]
    assert assignments, f"لم يُعثَر على إسنادٍ لـ{SINK} في المكدّس الموحَّد"
    for value in assignments:
        assert value.startswith("${QDRANT_API_KEY:?"), f"صيغةٌ غير مقبولة باقية: {value}"


def test_every_declared_sink_is_named_sourced_and_measured():
    doc = json.loads(SINKS.read_text(encoding="utf-8"))
    assert doc["contract"] == "SERVER-AUTH-SECRET-MUST-BE-NONEMPTY-01"
    assert doc["sinks"], "سجلُّ مصارفَ فارغ يمرّ أخضر عن سؤالٍ لم يُطرَح"
    assert doc["production_stacks"]["files"], "بلا مكدّساتٍ إنتاجيّة مُعلَنة لا يُفرَض حدُّ الاستثناء"
    for name, spec in doc["sinks"].items():
        assert name.isupper(), f"اسمُ مصرفٍ ليس متغيّرَ بيئةٍ حاويةً: {name}"
        for field in ("service", "source_env", "policy", "allowed_form", "why", "measured_on"):
            assert str(spec.get(field, "")).strip(), f"مصرفٌ بلا {field}: {name}"
        assert spec["policy"] == "REQUIRED_NONEMPTY"
        assert ":?" in spec["allowed_form"], (
            f"{name}: الصيغةُ المسموحة يجب أن تُثبِت غيرَ الفارغ — `?` وحدها تُثبِت الوجود"
        )


# ── D06-C1: عميلُ Qdrant يثبت الاعتماد محليّاً لا بالصدفة من مصرف الخادم ─────────


def test_sink_must_use_the_declared_source_env_not_any_required_variable(tmp_path, monkeypatch):
    """`${WRONG_SECRET:?x}` غير فارغ، لكنه ليس QDRANT_API_KEY المملوك للعقد."""
    probe = tmp_path / "docker-compose.probe.yml"
    probe.write_text(
        "services:\n  q:\n    image: qdrant/qdrant:v1.11.0\n    environment:\n"
        f"      {SINK}: ${{WRONG_SECRET:?required}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "compose_files", lambda: [probe])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    rows = guard.findings()
    assert rows and rows[0][0] == f"docker-compose.probe.yml::{SINK}", (
        "الحارس قبِل متغيّراً آخر لمجرّد أنّه `:?` — الشكل ثُبِّت بدل ملكيّة السرّ"
    )


def test_all_declared_qdrant_clients_are_locally_required_and_nonempty():
    defects = guard.client_binding_defects()
    assert defects == [], "\n".join(defects)


def test_bare_qdrant_client_binding_is_rejected(monkeypatch):
    key = "docker-compose.v9.yml::sahool-rag-retrieval::QDRANT_API_KEY"
    monkeypatch.setattr(
        guard,
        "_required_clients",
        lambda: {
            key: {
                "service": "sahool-rag-retrieval",
                "source_env": "QDRANT_API_KEY",
                "policy": "REQUIRED_NONEMPTY",
                "allowed_form": "${QDRANT_API_KEY:?…}",
            }
        },
    )
    monkeypatch.setattr(guard, "_production_client_assignments", lambda: {key: "${QDRANT_API_KEY}"})
    defects = guard.client_binding_defects()
    assert any("استيفاءٌ عارٍ" in item for item in defects), (
        "إسنادُ عميلٍ عارٍ مرّ — الرابطُ المحليّ عاد يعتمد على بقاء مصرف الخادم في الملف نفسه"
    )


def test_new_qdrant_client_on_a_production_stack_must_be_registered(tmp_path, monkeypatch):
    rel = "docker-compose.v9.yml"
    probe = tmp_path / rel
    probe.write_text(
        "services:\n"
        "  registered:\n    image: alpine\n    environment:\n"
        "      QDRANT_API_KEY: ${QDRANT_API_KEY:?required}\n"
        "  newcomer:\n    image: alpine\n    environment:\n"
        "      QDRANT_API_KEY: ${QDRANT_API_KEY:?required}\n",
        encoding="utf-8",
    )
    registered_key = f"{rel}::registered::QDRANT_API_KEY"
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "_production_files", lambda: {rel})
    monkeypatch.setattr(
        guard,
        "_required_clients",
        lambda: {
            registered_key: {
                "service": "registered",
                "source_env": "QDRANT_API_KEY",
                "policy": "REQUIRED_NONEMPTY",
                "allowed_form": "${QDRANT_API_KEY:?…}",
            }
        },
    )
    defects = guard.client_binding_defects()
    assert any("غير مسجّل" in item and "newcomer" in item for item in defects), (
        "خدمةُ Qdrant جديدة دخلت production_stacks خارج سجلّ روابط العملاء"
    )


def test_registered_qdrant_client_that_disappears_blocks(monkeypatch):
    key = "docker-compose.v9.yml::ghost::QDRANT_API_KEY"
    monkeypatch.setattr(
        guard,
        "_required_clients",
        lambda: {
            key: {
                "service": "ghost",
                "source_env": "QDRANT_API_KEY",
                "policy": "REQUIRED_NONEMPTY",
                "allowed_form": "${QDRANT_API_KEY:?…}",
            }
        },
    )
    monkeypatch.setattr(guard, "_production_client_assignments", lambda: {})
    assert any("اختفى" in item for item in guard.client_binding_defects())
