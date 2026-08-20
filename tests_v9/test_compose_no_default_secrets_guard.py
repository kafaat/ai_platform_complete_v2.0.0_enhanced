"""`COMPOSE-DEFAULT-SECRET-IS-A-PUBLISHED-SECRET-01` — وشهودُ نطاقه الخمسة.

`${APP_DB_PASSWORD:-sahool_app_pw}` ليست قيمةً مريحة للتطوير. هي كلمة مرور
**منشورة** لدورٍ مقيّد يحمل RLS: كلّ من قرأ المستودع يعرفها، وكلّ بيئة أُقلعت بلا
ضبطٍ صريح تعمل بها.

وهذا الملفّ يفرض `GUARD-SCOPE-COMPLETENESS` (دفتر القرارات 2026-08-20): لا يُقبَل
حارس جديد إلّا بخمسة شهود — مصدرُ السطح، وما رآه، وما استبعده ولماذا، **وتساوي
المجموعات** لا العدّادات، وشاهدُ طفرة. والرابع هو الحامل: عدّادٌ يقول «فُحِص ١٦
ملفّاً» صادقٌ ومُضلِّل معاً — لا يقول أيّها ولا يكشف سابع عشر دخل الشجرة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "compose_no_default_secrets_guard.py"
EXCEPTIONS = ROOT / "docs" / "architecture" / "compose_secret_exceptions.json"


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_g_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"_g_{name}"] = module
    spec.loader.exec_module(module)
    return module


guard = _load("compose_no_default_secrets_guard")
surface = _load("compose_surface")


# ── الشهود ①②③: المصدر وما رآه وما استبعده ──────────────────────────────────


def test_the_surface_declares_its_source_and_is_not_a_hand_written_list():
    witness = surface.discovery_witness()
    assert witness["universe_source"].startswith("git ls-files"), (
        "السطح يجب أن يُشتقّ من git لا من قائمةٍ في ملفّ — القائمة تبيت، والاشتقاق لا"
    )
    assert witness["discovered_paths"], "سطحٌ فارغ يمرّ أخضر عن سؤالٍ لم يُطرَح"
    for path, reason in witness["excluded_paths"].items():
        assert str(reason).strip(), f"استبعادٌ بلا سبب: {path}"


# ── الشاهد ④: تساوي المجموعات، لا عدّادات ────────────────────────────────────


def test_the_discovered_set_equals_the_git_tracked_set_exactly():
    """المقيس **تساوٍ** لا عدد — وهذا هو الفارق كلّه.

    عدّادٌ متطابق يمرّ ولو كان الحارس يفحص ملفّاً ويغفل آخر بالعدد نفسه. والمجموعة
    تقول أيّها بالضبط، فتكشف الفرق في الاتّجاهين: ما رآه ولم يكن، وما كان ولم يره.
    """
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
        f"السطح ينحرف عن المتعقَّب. لم يُرَ: {sorted(expected - discovered)} · "
        f"رُئي بلا تعقّب: {sorted(discovered - expected)}"
    )


# ── الشاهد ⑤: شاهدُ الطفرة — عنصرٌ جديد على السطح يجب أن يُرى ────────────────


def test_a_new_compose_file_on_the_surface_is_seen_by_the_guard(tmp_path, monkeypatch):
    """ملفٌّ جديد يدخل السطح ويحمل سرّاً افتراضيّاً — يجب أن يُدان لا أن يُغفَل.

    وهو الشاهد الذي يفصل «حارساً يفحص ما يعرفه» عن «حارسٍ يفحص ما يوجد».
    """
    new = tmp_path / "docker-compose.probe.yml"
    new.write_text(
        "services:\n  probe:\n    image: alpine\n"
        "    environment:\n      APP_DB_PASSWORD: ${APP_DB_PASSWORD:-planted_secret}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "compose_files", lambda: [new])
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    keys = [key for key, _ in guard.findings()]
    assert "docker-compose.probe.yml::APP_DB_PASSWORD" in keys, (
        "ملفٌّ جديد على السطح بسرٍّ افتراضيّ لم يُرَ — الحارس يفحص ما يعرفه لا ما يوجد"
    )


# ── العقد نفسه ───────────────────────────────────────────────────────────────


def test_the_live_tree_carries_no_default_secret():
    result = subprocess.run(
        [sys.executable, str(GUARD)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_empty_default_is_accepted_and_a_valued_one_is_not():
    """الشكلان المقبولان مقيسان لا مُعلَنان — و`:-` الفارغ هو ما يُبقي profiles تعمل.

    القياس الذي فرض هذا: `:?required` على خدمةٍ خلف profile يكسر
    `docker compose config` للمكدّس الافتراضيّ (الاستيفاء يسبق الترشيح). فلو رفض
    الحارس الفارغَ أيضاً لدفع الكاتب إلى `:?` فكسر مكدّساً لا يستعمل الخدمة.
    """
    assert guard._is_secret("APP_DB_PASSWORD")
    assert not guard._is_secret("DECISION_WORKER_ASSERTION_KEY_ID"), (
        "`_KEY_ID` معرّفٌ لا سرّ — إدانتُه تُدرِّب الكاتب على تجاهل الحارس"
    )


def test_every_exception_is_named_owned_and_dated():
    entries = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))["exceptions"]
    for key, entry in entries.items():
        assert "::" in key, f"استثناءٌ على مستوى الملفّ لا المتغيّر: {key} — إعفاءُ جملة"
        for field in ("reason", "owner", "expires_on"):
            assert str(entry.get(field, "")).strip(), f"استثناء بلا {field}: {key}"


def test_a_stale_exception_is_reported_so_the_list_can_only_shrink(monkeypatch):
    """المقيس **القدرة على الكشف**، لا حالةُ الشجرة اليوم.

    أوّل صياغةٍ عندي أكّدت ``stale_exceptions() == []`` وحدها — فمرّت طفرةٌ تجعل
    الدالّة تُرجِع الفارغ **دائماً** (`live = set(_exceptions())`): الشجرة نظيفة،
    فالتأكيد يصدق، والقدرة زالت. أمسكها `guard_mutation_guard` وهو محقّ — وهو
    صنف «أخضرُ عن سؤالٍ لم يُطرَح» واقعاً في اختباري أنا.

    فيُزرَع مدخلٌ بائت ويُقاس أنّه **يُرى**، ثمّ يُقاس أنّ الحيّ لا يُدان.
    """
    live_key = next(iter(guard._exceptions()), None)
    assert live_key, "لا استثناء مُسجَّل — لا يمكن قياس التمييز بين الحيّ والبائت"

    planted = {
        live_key: guard._exceptions()[live_key],
        "docker-compose.ghost.yml::GHOST_PASSWORD": {
            "reason": "مِسبار",
            "owner": "probe",
            "expires_on": "2026-01-01",
        },
    }
    monkeypatch.setattr(guard, "_exceptions", lambda: planted)
    stale = guard.stale_exceptions()
    assert "docker-compose.ghost.yml::GHOST_PASSWORD" in stale, (
        "مدخلٌ لا انتهاك يقابله لم يُرَ بائتاً — القائمة تتوقّف عن التقلّص فيصير "
        "الإعفاء المؤقّت أبديّاً بلا صاحب"
    )
    assert live_key not in stale, "مدخلٌ حيّ أُدين بائتاً — الإدانة الخاطئة تُدرِّب على الحذف"
