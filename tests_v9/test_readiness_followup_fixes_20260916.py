"""شواهد انحدار لإصلاحات ما بعد #1007 (تحقّق الجاهزية 2026-09-16) — بلا خدمات حيّة.

كلّ حالة هنا وُلدت من عطلٍ **مقيس** في مراجعة المتبقّي، لا من افتراض:

١) مجدوِل الصور كان على مسبح التطبيق بتعليل «لا RLS جديدة على جداوله»، والهجرة
   `v9_rls_tenant_isolation.sql` تُدرِج `imagery_automation_fields` في مصفوفة
   ENABLE+FORCE بسياسة قراءة فاشلة-مغلقة ⇒ صفر صفوف بلا استثناء تحت دور مُقيَّد.
٢) `requires_imagery_backfill_24_months` كانت تُحسَب «عدد التواريخ = صفر» فتَعِد
   بما لا تقيس؛ حقلٌ بمشهد واحد يُبلِّغ «لا حاجة للتعبئة».
٣) نيّة متابعة الطقس لم تكن تُسجَّل عند إنشاء الحقل (فجوة M4)، بخلاف الصور.
٤) حرّاس الحاويات لم يغطّوا خدمات الذكاء، فتحويل فحص الصحّة إلى الجاهزيّة يمرّ.
٥) `a or b or 0` في مسار تلميح الريّ كان يخلط «لا حساب» بـ«صفر مِلّيمتر».
٦) سطرُ المشهد الفارغ من CDSE كان بلا bbox ولا نافذة ولا عتبة سُحُب، والبايتات
   تُحذَف، فتعذّر نسبةُ السبب لاحقاً.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
pytestmark = pytest.mark.unit

if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))


# ── ١) مجدوِل الصور على مسبح المهامّ (BYPASSRLS) كالطقس ──────────────────────


def test_imagery_scheduler_is_wired_to_the_jobs_pool_like_weather():
    src = (PLATFORM / "api/main.py").read_text(encoding="utf-8")
    assert "imagery_automation.set_pool(_JOBS_POOL or _DB_POOL)" in src, (
        "قراءة المُجدوِل بلا سياق تحت FORCE RLS تُرجِع صفر صفوف بلا استثناء ⇒ عطل صامت"
    )
    assert "imagery_automation.set_pool(_DB_POOL)" not in src, (
        "مسبح التطبيق يُخضِع قراءةَ المُجدوِل لسياسة المستأجِر فيصير «لا حقول مُتابَعة» كاذباً"
    )


def test_migration_really_forces_rls_on_the_imagery_automation_table():
    """التعليل الذي بُني عليه الخطأ كان «لا RLS جديدة على جداوله» — هذه تكذّبه."""
    sql = (ROOT / "migrations/v9_rls_tenant_isolation.sql").read_text(encoding="utf-8")
    assert "'imagery_automation_fields'" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql


# ── ٢) راية تاريخ الصور تقول ما تقيس ────────────────────────────────────────


def test_readiness_flag_names_what_it_measures_and_declares_its_window():
    src = (PLATFORM / "api/routers/field_ai_context.py").read_text(encoding="utf-8")
    assert '"imagery_history_absent"' in src
    assert '"imagery_observed_window_days": days' in src
    assert "requires_imagery_backfill_24_months" not in src.replace(
        "`requires_imagery_backfill_24_months`", ""
    ), "الاسمُ القديم يَعِد بأربعة وعشرين شهراً ولا يقيس إلّا خلوّ النافذة المطلوبة"


def test_no_consumer_still_reads_the_retired_flag():
    targets = [
        ROOT / "services/ai_agronomist/ai_evidence_runtime.py",
        ROOT / "frontend/src/sections/ChatbotPage.tsx",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert "requires_imagery_backfill_24_months" not in text, (
            f"{path.name} ما زال يقرأ رايةً مُتقاعدة ⇒ الشرطُ يصير ميّتاً بصمت"
        )
        assert "imagery_history_absent" in text


# ── ٣) نيّتا الصور والطقس تُثبَّتان في معاملة إنشاء الحقل (M4) ────────────────


@pytest.mark.asyncio
async def test_field_creation_registers_both_imagery_and_weather_intents():
    from api.imagery_automation import register_field_tracking_intents

    conn = SimpleNamespace(execute=AsyncMock())
    geometry = {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
    }
    result = await register_field_tracking_intents(
        conn,
        field_id="f1",
        tenant_id="11111111-1111-1111-1111-111111111111",
        geometry=geometry,
        lat=15.005,
        lon=44.005,
    )
    assert result == {"imagery": True, "weather": True}
    tables = [
        call.args[0].split("INSERT INTO ")[1].split()[0] for call in conn.execute.call_args_list
    ]
    assert tables == ["imagery_automation_fields", "weather_automation_locations"]


@pytest.mark.asyncio
async def test_missing_centroid_registers_imagery_only_and_invents_no_location():
    from api.imagery_automation import register_field_tracking_intents

    conn = SimpleNamespace(execute=AsyncMock())
    geometry = {
        "type": "Polygon",
        "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
    }
    result = await register_field_tracking_intents(
        conn,
        field_id="f1",
        tenant_id="11111111-1111-1111-1111-111111111111",
        geometry=geometry,
        lat=None,
        lon=None,
    )
    assert result == {"imagery": True, "weather": False}
    assert conn.execute.await_count == 1


@pytest.mark.asyncio
async def test_weather_registration_uses_callers_transaction_and_failure_propagates():
    from api.weather_automation import WeatherAutomation

    automation = WeatherAutomation()
    conn = SimpleNamespace(execute=AsyncMock())
    await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="f1")
    sql = conn.execute.call_args.args[0]
    assert "INSERT INTO weather_automation_locations" in sql
    assert "ON CONFLICT (location_key) DO UPDATE" in sql
    assert conn.execute.call_args.args[-1] == "f1"

    conn.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="f1")

    with pytest.raises(ValueError):
        await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="")


def test_field_creation_calls_the_shared_intent_helper():
    src = (PLATFORM / "api/routers/fields.py").read_text(encoding="utf-8")
    assert "register_field_tracking_intents(" in src


# ── ٤) حرّاس الحاويات يغطّون خدمات الذكاء ────────────────────────────────────


def test_container_guard_covers_the_ollama_dependent_services():
    from importlib import util as _util

    spec = _util.spec_from_file_location(
        "followup_container_guard", ROOT / "scripts/ci/container_fleet_contract_guard.py"
    )
    module = _util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for rel in (
        "services/local-ai-rag/Dockerfile",
        "services/rag-retrieval/Dockerfile",
        "services/ai_agronomist/Dockerfile",
    ):
        assert rel in module.NO_READYZ_HEALTHCHECK, (
            f"{rel} خارج الحارس ⇒ تحويل فحص الصحّة إلى /readyz يمرّ صامتاً"
        )


def test_ai_service_dockerfiles_probe_liveness_not_readiness():
    for rel in (
        "services/local-ai-rag/Dockerfile",
        "services/rag-retrieval/Dockerfile",
        "services/ai_agronomist/Dockerfile",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        healthcheck = [ln for ln in text.splitlines() if "HEALTHCHECK" in ln]
        assert healthcheck, f"{rel} بلا HEALTHCHECK"
        joined = " ".join(healthcheck)
        assert "/healthz" in joined
        assert "/readyz" not in joined, (
            f"{rel} يقيس الجاهزيّة كحياة ⇒ بطء تحميل النموذج يصير إعادة تشغيل دوريّة"
        )


# ── ٥) الكميّة غير المحسوبة تبقى مجهولة لا صفراً ─────────────────────────────


def test_first_measured_keeps_absent_unknown_and_measured_zero_valid():
    from core.guardrails import _first_measured

    assert _first_measured(None, None) is None
    assert _first_measured(None, 12.5) == 12.5
    assert _first_measured(0, 12.5) == 0.0  # الصفرُ المقيس قياسٌ لا غياب
    assert _first_measured(True, 4) == 4.0  # bool ليس قياساً
    assert _first_measured("7", 4) == 4.0
    assert _first_measured(float("nan"), 4) == 4.0
    assert _first_measured(float("inf"), None) is None


def test_irrigation_hint_does_not_say_zero_millimetres_for_an_uncomputed_amount():
    src = (PLATFORM / "core/guardrails.py").read_text(encoding="utf-8")
    assert 'irr.get("net_irrigation_mm") or 0' not in src, (
        "`or 0` يخلط «لا كميّة محسوبة» بـ«صفر مِلّيمتر» — دلالتان مختلفتان"
    )
    assert "_first_measured(irr.get(" in src
    assert "كميّة الريّ غير محسوبة" in src


# ── ٦) سطرُ المشهد الفارغ يحمل طلبَه ────────────────────────────────────────


def test_empty_cdse_scene_log_carries_the_request_that_produced_it():
    src = (ROOT / "services/raster-service/raster_cdse_tile_runtime.py").read_text(encoding="utf-8")
    block = src.split("CDSE returned an empty raster")[1].split("_unlink_best_effort")[0]
    for token in ("window=", "bbox=", "max_cloud_pct=", "mosaicking=", "bytes=", "polygon_mask="):
        assert token in block, f"سطرُ المشهد الفارغ بلا {token} ⇒ السببُ غير منسوب بعد حذف البايتات"
    assert "_unlink_best_effort(cog_path" in src, (
        "البايتات الفارغة لا تُخزَّن — والسطر يبقى الأثر الوحيد"
    )
