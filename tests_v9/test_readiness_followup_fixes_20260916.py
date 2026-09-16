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


def test_imagery_scheduler_binds_its_pool_through_the_role_proving_path():
    src = (PLATFORM / "api/main.py").read_text(encoding="utf-8")
    assert "await bind_recovery_pool(_JOBS_POOL or _DB_POOL)" in src, (
        "قراءة المُجدوِل بلا سياق تحت FORCE RLS تُرجِع صفر صفوف بلا استثناء ⇒ عطل صامت"
    )
    assert "imagery_automation.set_pool(_DB_POOL)" not in src, (
        "مسبح التطبيق يُخضِع قراءةَ المُجدوِل لسياسة المستأجِر فيصير «لا حقول مُتابَعة» كاذباً"
    )


class _RolePool:
    """مسبح وهميّ يُعيد صفَّ دورٍ واحداً، أو يرفع عند تعذّر القياس."""

    def __init__(self, row, raises: bool = False):
        self._row, self._raises = row, raises

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                if pool._raises:
                    raise RuntimeError("no pg_roles")
                return SimpleNamespace(fetchrow=AsyncMock(return_value=pool._row))

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("row", "raises", "bound"),
    [
        ({"rolsuper": False, "rolbypassrls": True}, False, True),  # دور خدميّ ⇒ يُربَط
        ({"rolsuper": True, "rolbypassrls": False}, False, True),  # superuser ⇒ يُربَط
        ({"rolsuper": False, "rolbypassrls": False}, False, False),  # مُقيَّد ⇒ فشل مُعلَن
        (None, True, True),  # تعذّر القياس ⇒ لا يحجب بيئة التطوير
    ],
)
async def test_restricted_role_refuses_to_bind_instead_of_reading_zero_silently(row, raises, bound):
    """مراجعة #1009: `_JOBS_POOL or _DB_POOL` قد يكون الدورَ المُقيَّد نفسه.

    مسبحُ المهامّ يُصنَع من وصلة التطبيق حين تغيب `JOBS_DATABASE_URL`، ويصير None
    عند فشل إنشائه — فالقرار يجب أن يُقاس بالدور لا بهويّة الكائن.
    """
    import api.imagery_automation as mod

    automation = mod.imagery_automation
    previous = automation._pool
    automation._pool = None
    try:
        pool = _RolePool(row, raises=raises)
        assert await mod.bind_recovery_pool(pool) is bound
        assert (automation._pool is pool) is bound
    finally:
        automation._pool = previous


@pytest.mark.asyncio
async def test_absent_pool_binds_nothing():
    import api.imagery_automation as mod

    assert await mod.bind_recovery_pool(None) is False


def test_migration_really_forces_rls_on_the_imagery_automation_table():
    """التعليل الذي بُني عليه الخطأ كان «لا RLS جديدة على جداوله» — هذه تكذّبه."""
    sql = (ROOT / "migrations/v9_rls_tenant_isolation.sql").read_text(encoding="utf-8")
    assert "'imagery_automation_fields'" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql


def test_ci_step_pins_the_flag_that_turns_a_missing_database_into_a_failure():
    """مراجعة #1014 (مكتومة): الشهادةُ الحيّة تتخطّى نفسَها بلا DSN.

    شاهدُ `imagery_automation_fields` مُعلَّم `integration` وله `skipif` على مستوى
    الوحدة، فحذفُ العَلَم أو إعادةُ تسميته في تحريرٍ لاحق — مع غياب الـDSN — تجعل
    **وظيفةً مخصَّصةً للشهادة تخضرّ بلا أن تقيس السياسةَ المُهاجَرة**. وهذا صنفُ
    «التخطّي الصامت يُقرَأ نجاحاً» بعينه.

    فيُثبَّت العقدُ ساكناً هنا — في اختبار وحدةٍ يعمل دائماً لا في ملفٍّ يتخطّى نفسه —
    على غرار `test_hil_ci_requires_the_live_database_certificate`.
    """
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integration-tests"]["steps"]
    target = "pytest -v -m integration -rs tests_v9/test_imagery_automation_rls_live_pg.py"
    selected = [step for step in steps if step.get("run", "").strip() == target]
    assert len(selected) == 1, "خطوةُ شهادة RLS لأتمتة الصور غائبة أو مكرّرة"
    env = selected[0].get("env") or {}
    assert env.get("IMAGERY_RLS_CERTIFICATION_REQUIRED") == "1", (
        "بلا العَلَم يصير غيابُ القاعدة تخطّياً أخضرَ في وظيفةٍ تُعلِن أنّها تشهد"
    )
    # والعَلَمُ وحده لا يكفي: بلا DSN يرفع الملفُّ استثناءً عند الجمع، وبـDSN خاطئ
    # يقيس قاعدةً أخرى. الاثنان مُثبَّتان نصّاً كي لا يُعاد توجيهُهما صامتَين.
    assert env.get("TEST_DATABASE_ADMIN_URL"), "بلا DSN إداريّ لا تهيئةَ صفوفٍ ولا قياسَ دور"
    assert env.get("TEST_DATABASE_URL"), "بلا DSN مُقيَّد تُقاس السياسةُ بدورٍ يتجاوزها"
    assert "sahool_app_test" in env["TEST_DATABASE_URL"], (
        "الـDSN المحروس يجب أن يكون الدورَ المُقيَّد لا المُدير"
    )


def _load_live_witness_with_driver_blocked(monkeypatch, *, certification: bool):
    """يُحمِّل ملفَّ الشاهد الحيّ من مساره و`asyncpg` محجوب — كما لو كان المُشغِّل بلا سائق."""
    import importlib.util

    monkeypatch.setitem(sys.modules, "asyncpg", None)  # None ⇒ ImportError عند الاستيراد
    monkeypatch.setenv("IMAGERY_RLS_CERTIFICATION_REQUIRED", "1" if certification else "0")
    monkeypatch.setenv("TEST_DATABASE_ADMIN_URL", "postgresql://admin@localhost/x")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://sahool_app_test@localhost/x")
    path = ROOT / "tests_v9/test_imagery_automation_rls_live_pg.py"
    spec = importlib.util.spec_from_file_location("_imagery_rls_witness_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_missing_driver_is_a_hard_failure_under_certification(monkeypatch):
    """مراجعة #1014: `importorskip` قبل قراءة العَلَم كان يُخضِّر الشهادةَ بلا سائق.

    تحت `IMAGERY_RLS_CERTIFICATION_REQUIRED=1` يجب أن يُرفَع خطأُ الاستيراد نفسُه عند الجمع،
    لا أن تُتخطّى الوحدة — وإلّا أعلنت وظيفةُ الشهادة خضرةً ولم تقِس شيئاً.
    """
    # لا `pytest.raises(ImportError)` وحده: لو تخطّى الملفُّ نفسَه لخرج استثناءُ التخطّي
    # من هذا الاختبار فسُجِّل «متخطّى» لا «فاشل» — وهو الصنفُ نفسُه الذي يُكذَّب هنا.
    try:
        _load_live_witness_with_driver_blocked(monkeypatch, certification=True)
    except ImportError:
        return
    except pytest.skip.Exception:
        pytest.fail("غيابُ السائق صار تخطّياً تحت الشهادة — بوّابةٌ تخضرّ بلا قياس")
    pytest.fail("الشاهدُ حُمِّل بلا سائق ولم يرفع شيئاً")


def test_a_missing_driver_still_skips_outside_certification(monkeypatch):
    """خارج الشهادة يبقى غيابُ السائق تخطّياً مُعلَّلاً لا فشلاً — كي لا يُعاقَب تطويرٌ بلا قاعدة."""
    with pytest.raises(pytest.skip.Exception):
        _load_live_witness_with_driver_blocked(monkeypatch, certification=False)


# ── ٢) راية تاريخ الصور تقول ما تقيس ────────────────────────────────────────


def test_readiness_flag_names_what_it_measures_and_declares_its_window():
    src = (PLATFORM / "api/routers/field_ai_context.py").read_text(encoding="utf-8")
    assert '"imagery_history_absent"' in src
    assert '"imagery_observed_window_days": days if include_imagery else None' in src
    assert "requires_imagery_backfill_24_months" not in src.replace(
        "`requires_imagery_backfill_24_months`", ""
    ), "الاسمُ القديم يَعِد بأربعة وعشرين شهراً ولا يقيس إلّا خلوّ النافذة المطلوبة"


def test_unrequested_imagery_reports_unknown_not_verified_absence():
    """مراجعة #1009: `include_imagery=False` يترك الجرد على افتراضه الصفريّ.

    قراءةُ ذلك «غياباً مُتحقَّقاً» تُشغّل تعبئةً بلا سبب؛ ما لم يُقَس يُعلَن None.
    """
    src = (PLATFORM / "api/routers/field_ai_context.py").read_text(encoding="utf-8")
    block = src.split('"imagery_history_absent"')[1].split("evidence_freshness_score")[0]
    assert "if include_imagery else None" in block
    assert block.count("if include_imagery else None") == 2, (
        "الرايةُ ونافذتُها كلتاهما تُعلَنان مجهولتين حين لا يُستعلَم عن الصور"
    )


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
    assert conn.execute.call_args.args[-1] == "f1"

    conn.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="f1")

    with pytest.raises(ValueError):
        await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="")


@pytest.mark.asyncio
async def test_second_field_in_the_same_rounded_cell_never_steals_or_fails():
    """مراجعة #1009: المفتاح موقعٌ مُقرَّب والصفّ يحمل ارتباطاً واحداً.

    `DO UPDATE` كان يسرق ارتباطَ حقلٍ سابق، ويُفشِل **إنشاء الحقل** حين يملك الصفَّ
    مستأجِرٌ آخر لأنّ الصفّ غير مرئيّ تحت FORCE RLS فيُخفِق تحديثُ التعارض.
    """
    from api.weather_automation import WeatherAutomation

    automation = WeatherAutomation()
    conn = SimpleNamespace(execute=AsyncMock())
    await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="first")
    sql = conn.execute.call_args.args[0]
    assert "ON CONFLICT (location_key) DO NOTHING" in sql
    assert "DO UPDATE" not in sql, "تحديثُ التعارض يسرق ارتباطاً قائماً أو يُفشِل إنشاء الحقل"
    # حقلٌ ثانٍ في الخليّة نفسها: المفتاح واحد والارتباطُ لأوّل كاتب، بلا استثناء.
    await automation.register_on_connection(conn, lat=15.0004, lon=44.0004, field_id="second")
    assert conn.execute.call_args.args[1] == automation._key_str(15.0, 44.0)


@pytest.mark.asyncio
async def test_registration_does_not_seed_the_in_memory_scheduler_before_commit():
    """مراجعة #1009: معاملةٌ قد تتراجع (merge/split) بعد هذا النداء.

    زرعُ الذاكرة قبل الالتزام يترك حقلاً مُتراجَعاً عنه قيدَ المعالجة في `refresh_all`؛
    الذاكرةُ تُبنى من `load_from_db` أي من المُلتزَم وحده.
    """
    from api.weather_automation import WeatherAutomation

    automation = WeatherAutomation()
    conn = SimpleNamespace(execute=AsyncMock())
    await automation.register_on_connection(conn, lat=15.0, lon=44.0, field_id="f1")
    assert automation.registered_count() == 0
    src = (PLATFORM / "api/weather_automation.py").read_text(encoding="utf-8")
    body = src.split("async def register_on_connection")[1].split("def unregister_location")[0]
    assert "self.register_location(" not in body


def test_field_creation_calls_the_shared_intent_helper():
    """العقدُ بعد دمج حزمة B6/M4: الراوتر ينادي مدخلاً واحداً، والمدخلُ يُفوّض لتسجيل
    المتابعة. الفحصُ على الطرفين مقصود — لو استُبدل المدخلُ يوماً بتسجيلٍ يُسقِط الطقس
    (كما كانت الحزمةُ تفعل حرفيّاً) لَما احمرّ فحصُ الراوتر وحده."""
    router = (PLATFORM / "api/routers/fields.py").read_text(encoding="utf-8")
    assert "register_field_creation_intents(" in router
    entry = (PLATFORM / "api/onboarding.py").read_text(encoding="utf-8")
    assert "register_field_tracking_intents(" in entry, (
        "مدخلُ الإنشاء لا يُفوّض لتسجيل الصور والطقس ⇒ نيّةُ الطقس تسقط صامتة"
    )
    assert "maybe_enqueue_field_bootstrap(" in entry


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
