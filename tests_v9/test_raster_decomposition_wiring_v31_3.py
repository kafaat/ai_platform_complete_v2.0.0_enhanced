"""حارس: تفكيك raster main.py (phase2–5) موصولٌ بالكامل — لا رمز مُستخرَج معلَّق.

الجذر (رُصِد أثناء دمج phase5): التفكيك نقل مُعالِجات إلى وحدات شقيقة لكن نسي وصلها
بـmain: (١) ``raster_asset_persistence`` لم يُستورَد فاختفى ``main._persist_raster_asset``/
``_is_valid_field_id_text`` بينما ``raster_job_orchestration`` يستدعي
``ctx._persist_raster_asset`` ⇒ AttributeError على كلّ حفظ؛ (٢) سطر كتب
``_fieldctx._layers`` (اسم غير مُعرَّف + مخزن خاطئ) بدل ``ctx._field_layers``.

ساكنٌ عمداً (يقرأ المصدر نصّاً، لا ``import main``): وظيفة *Unit Tests* في CI تُثبّت
تبعيّات دُنيا بلا fastapi/rasterio، فاستيراد main يرمي ModuleNotFoundError. نفحص وصل
الرموز عبر تحليل مصدر main.py + الوحدات الشقيقة — يبقى الحارس فعّالاً في بيئة CI الدُّنيا.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RASTER = Path(__file__).resolve().parents[1] / "services" / "raster-service"
MAIN = RASTER / "main.py"


def _main_surface() -> str:
    """phase31: main.py أصبح bootstrap رفيعاً يكشف رموز التوافق ديناميكيّاً عبر __getattr__
    من raster_main_compat_exports و raster_main_runtime. «سطح main» الفعليّ = الثلاثة معاً."""
    parts = ("main.py", "raster_main_compat_exports.py", "raster_main_runtime.py")
    return "\n".join((RASTER / p).read_text(encoding="utf-8") for p in parts)


_DECOMP_MODULES = (
    "raster_job_orchestration",
    "scene_policy",
    "stac_search",
    "raster_asset_persistence",
    "raster_date_geo",
    "cdse_singleflight",
    "layer_lookup",
    "tile_cache_io",
)
# رموز يعتمدها عامل الـbackfill/الراوترات عبر main.* (اختفاؤها = كسر صامت وقت التشغيل).
# ملاحظة: phase23 أتمّ فصل main — لم يعُد يُعيد تصدير _is_valid_field_id_text ولا
# _select_backfill_scenes_by_policy (العامل/الاختبارات تستورد raster_asset_persistence
# و scene_policy مباشرةً)، فأُسقِطا من العقد. حارس بنية الاستيراد يضمن الفصل الكامل.
# phase28: أُسقِط _persist_raster_asset و_run_processing أيضاً — مُغلِّفات المعالجة/الحفظ
# أُزيلت من main.py، والعامل/الاختبارات تستورد raster_processing_runtime/
# raster_asset_persistence مباشرةً (وctx يُبنى صراحةً عبر make_processing_context).
_WORKER_CONTRACT = (
    "_stac_search",
    "_field_layers",
    "_layers",
)


def _defines(src: str, name: str) -> bool:
    """صحيحٌ إن كان main.py يُعرِّف/يُسمّي ``name`` على مستوى الوحدة (دالّة/صنف/إسناد/
    اسم مستورَد/ألياس) — أيّ منها يجعله متاحاً كـ``main.name`` وقت التشغيل."""
    patterns = (
        rf"^(?:async\s+def|def|class)\s+{re.escape(name)}\b",  # def/async def/class name
        # name = ...  (إسناد/ألياس، مع نوع اختياريّ). يُسمَح بمسافة بادئة لأنّ بعض
        # التعريفات على مستوى الوحدة تقع داخل try/except (مثل logger = setup_logging).
        rf"^\s*{re.escape(name)}\s*(?::[^=]+)?=[^=]",
        rf"\bas\s+{re.escape(name)}\b",  # import ... as name / X as name
        rf"^\s*import\s+{re.escape(name)}\b",  # import name
        # عضو استيراد مُقنطَر: ``from X import (\n    name,\n ...)`` — الاسم وحده على سطر
        # (بفاصلة/تعليق اختياريّ). التفكيك المرحليّ يعيد تصدير النماذج/الدوالّ هكذا.
        rf"^\s*{re.escape(name)}\s*,?\s*(?:#.*)?$",
    )
    return any(re.search(p, src, re.MULTILINE) for p in patterns)


def test_main_exposes_worker_and_test_contract() -> None:
    src = _main_surface()
    missing = [s for s in _WORKER_CONTRACT if not _defines(src, s)]
    assert not missing, f"main فقد رموزاً يعتمدها العامل/الاختبارات بعد التفكيك: {missing}"


def test_every_ctx_attr_used_by_decomposition_resolves_on_main() -> None:
    # ctx هو SimpleNamespace صريح (لا main): كلّ ``ctx.<attr>`` يُقرأ وقت التشغيل يجب أن
    # يكون قد أُسنِد على ctx **في مكانٍ ما من كود الإنتاج** — إمّا في مصنع السياق
    # make_processing_context أو على يد المُستدعي قبل التمرير. «التعريف على main» لا يكفي:
    # ctx كائن مستقلّ، فرمزٌ موجود على main لكنّه غير مُسنَد على ctx = AttributeError صامت
    # (بلاغ حيّ 2026-07-07: ctx._field_layers مفقود من المصنع فتفشل كلّ معالجة backfill لحقل).
    prod = [
        p for p in RASTER.glob("*.py") if not p.name.startswith("test_") and p.name != "main.py"
    ]
    ctx_set: set[str] = set()
    ctx_used: dict[str, set[str]] = {}
    for p in prod:
        s = p.read_text(encoding="utf-8")
        ctx_set |= set(re.findall(r"\bctx\.([A-Za-z_][A-Za-z0-9_]*)\s*=", s))
        used = set(re.findall(r"\bctx\.([A-Za-z_][A-Za-z0-9_]*)", s)) - set(
            re.findall(r"\bctx\.([A-Za-z_][A-Za-z0-9_]*)\s*=", s)
        )
        if used:
            ctx_used[p.name] = used
    missing = {name: sorted(u - ctx_set) for name, u in ctx_used.items() if u - ctx_set}
    assert not missing, (
        f"ctx.<attr> يُقرأ دون أن يُسنَد في أيّ مكان (AttributeError وقت التشغيل): {missing}"
    )


def test_no_undefined_fieldctx_alias() -> None:
    # الاسم الخاطئ _fieldctx يجب ألّا يعود (استُبدِل بـctx._field_layers).
    for mod in _DECOMP_MODULES:
        msrc = (RASTER / f"{mod}.py").read_text(encoding="utf-8")
        assert "_fieldctx" not in msrc, f"{mod}: اسم غير مُعرَّف _fieldctx عاد للظهور"
