"""حجمُ ملفّات الراوترات — راتشِت يتقلّص ولا ينمو.

``ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01`` (المراجعة البنيويّة 2026-09-13 §٢.٢).

**المقيس الذي أوجب هذا الحارس:** تفكيكُ ``main.py`` نجح شكلاً — ``p1_main_decomposition_guard``
يرفض أيَّ مُزخرِف مسارٍ فيه ويحدّ أسطرَه — **وانتقل الثقلُ إلى حيث لا قياس**:
``api/routers/`` صار ١٦٨ ملفّاً، وفيه ``fields.py`` **٤٬٢٤١** سطراً و``weather.py``
**٣٬٠٢٢**، وفي raster ``routers/fields.py`` ١٬٧١٢. حارسُ ``main.py`` يحدّ الملفَّ الذي
سُمّي له فقط، فالانحدارُ لم يتوقّف بل غيّر عنوانَه — وهو الصنفُ نفسُه المسجَّل في
``COVERAGE-MASKED-BY-A-NEIGHBOURING-GUARD-01``.

**القاعدة راتشِت لا حائط:** كلُّ راوترٍ فوق ``CEILING`` سطراً دَينٌ مُعلَن بعدد أسطره.
راوترٌ جديد يتجاوز السقف يسقط · نموُّ راوترٍ مُعلَن فوق أساسه يسقط · و**تقلُّصٌ لا يُخفَّض
معه الأساس يسقط أيضاً**. ولا يُقاس هنا «أيُّ تقسيمٍ صحيح» — الادّعاءُ أضيق: **لا ملفَّ
راوتر يكبر بعد اليوم.**

**حدُّ صدق:** الأسطرُ مقياسٌ خشن (تعليقٌ عربيٌّ مطوّل يُحتسَب كسطرِ منطق). اختير لأنّه ما
يفرضه حارسُ ``main.py`` نفسُه، فتتّسق القاعدةُ على الملفّين؛ والسقفُ ٨٠٠ يفصل الستّة
المُعلَنة عن ١٧٧ راوتراً تحته.

يُشغَّل في ``capability-governance.yml`` مع بقيّة حرّاس ``tests/architecture/``
(``ARCH-TESTS-UNLISTED-IN-CI-01``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CEILING = 800

#: الأساسُ المُجمَّد — مقيسٌ على `9613db9a` بـ`wc -l`. **يُخفَّض عند التقسيم ولا يُرفَع.**
FROZEN_OVERSIZE: dict[str, int] = {
    "services/sahool-platform/api/routers/fields.py": 4241,
    "services/sahool-platform/api/routers/weather.py": 3022,
    "services/raster-service/routers/fields.py": 1712,
    "services/sahool-platform/api/routers/farm_operations_ledger.py": 1058,
    "services/sahool-platform/api/routers/decision_review.py": 923,
    "services/sahool-platform/api/routers/field_ai_context.py": 824,
}


def _line_count(path: Path) -> int:
    # نفسُ دلالة `wc -l`: عددُ أسطر الملفّ كما يراه المراجِع.
    return path.read_bytes().count(b"\n")


def measure_oversize_routers(root: Path = ROOT, ceiling: int = CEILING) -> dict[str, int]:
    """كلُّ `services/**/routers/*.py` فوق السقف (نقيّة، قابلة للاختبار على شجرةٍ مصطنعة)."""
    found: dict[str, int] = {}
    base = root / "services"
    if not base.exists():
        return found
    for path in sorted(base.glob("*/**/routers/*.py")):
        if "__pycache__" in path.parts or path.name.startswith("test_"):
            continue
        n = _line_count(path)
        if n > ceiling:
            found[path.relative_to(root).as_posix()] = n
    return found


def test_no_router_grows_and_no_new_router_exceeds_the_ceiling():
    live = measure_oversize_routers()
    new_files = sorted(set(live) - set(FROZEN_OVERSIZE))
    grown = sorted(f for f in live if f in FROZEN_OVERSIZE and live[f] > FROZEN_OVERSIZE[f])
    assert not new_files, (
        f"ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01: راوترٌ جديد فوق {CEILING} سطراً — "
        f"قسِّمه: {new_files}"
    )
    assert not grown, (
        "ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01: راوترٌ مُعلَن كبر — "
        + ", ".join(f"{f}: {live[f]} > {FROZEN_OVERSIZE[f]}" for f in grown)
    )


def test_the_frozen_baseline_is_lowered_when_a_router_is_split():
    live = measure_oversize_routers()
    stale = sorted(f for f, cap in FROZEN_OVERSIZE.items() if live.get(f, 0) < cap)
    assert not stale, "الأساسُ يصف كوناً زال — خفِّضه: " + ", ".join(
        f"{f}: live={live.get(f, 0)} < frozen={FROZEN_OVERSIZE[f]}" for f in stale
    )


def test_the_detector_measures_only_routers_above_the_ceiling(tmp_path):
    """تكذيبٌ ذاتيّ على شجرةٍ مصطنعة."""
    r = tmp_path / "services" / "svc" / "api" / "routers"
    r.mkdir(parents=True)
    (r / "big.py").write_text("x = 1\n" * 12, encoding="utf-8")
    (r / "small.py").write_text("x = 1\n" * 3, encoding="utf-8")
    (tmp_path / "services" / "svc" / "api" / "not_a_router.py").write_text(
        "x = 1\n" * 50, encoding="utf-8"
    )
    assert measure_oversize_routers(tmp_path, ceiling=10) == {"services/svc/api/routers/big.py": 12}
