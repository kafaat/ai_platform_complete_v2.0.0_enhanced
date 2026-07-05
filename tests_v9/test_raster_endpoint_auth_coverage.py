"""حارس تصنيف/حماية نقاط خدمة الراستر (Raster Endpoint Auth Coverage Guard).

يحوّل قاعدة «كلّ نقطة راستر مُصنَّفة وتُحمى بالحارس الصحيح لصنفها» إلى بوّابة CI
مفروضة. خدمة ``raster-service`` (المنفذ 8001) تعرّض نقاطاً تقع في أصناف أمنيّة
مختلفة، ولكلٍّ حارسه الإلزاميّ:

  • **field_scoped (مكشوف للمتصفّح)** — ``/v1/fields/{field_id}/...`` تُنادى مباشرةً
    من المتصفّح بالـfield_id فقط (لا توكن خدمة في توقيعها). يجب أن تستدعي
    ``_require_field_tenant(field_id)`` (تفويض ملكيّة الحقل — إغلاق IDOR).
  • **field_scoped (خدمة-لخدمة)** — ``/v1/fields/{field_id}/...`` التي تحمل ترويسة
    ``x_agent_token`` في توقيعها: ليست مكشوفة للمتصفّح بل يستدعيها العامل/الوكيل،
    فتُحمى بـ``_require_service_token`` (مطابقة الشقيقات — منع كشف الحقول). تُدرَج
    صراحةً في ``FIELD_SCOPED_SERVICE_ONLY`` بتبرير لكلّ منها.
  • **layer_scoped** — ``/tiles/{layer_id}/...`` و``/layers/{layer_id}/tilejson``
    يجب أن تستدعي ``_require_layer_tenant(layer_id)`` (تفويض ملكيّة الطبقة).
  • **service_only** — معالجة/مهامّ/رفع/أدوات (``/process``، ``/jobs/{id}``،
    ``/info/{layer_id}``، ``/cog/validate``، ...) يجب أن تستدعي
    ``_require_service_token`` (توكن خدمة-لخدمة، لا يُكشف للمتصفّح).
  • **public_catalog** — بحث صور أقمار عامّة بـbbox + فحوص صحّة: لا بيانات مستأجِر،
    مسموح بلا مصادقة، لكن **ضمن قائمة صريحة**
    مُبرَّرة (``PUBLIC_CATALOG``).

الآليّة (عبر ``ast`` لا regex — أمتن أمام الالتفاف/التنسيق):
  ١) يحلّل ``services/raster-service/main.py`` ويستخرج كلّ دالّة مُزخرفة بـ
     ``@app.<method>`` (المسار + النداءات في جسمها + هل ``x_agent_token``/``Header``
     في توقيعها).
  ٢) يصنّف كلّ نقطة بمسارها ويؤكّد وجود الحارس الإلزاميّ لصنفها، أو إدراجها في
     قائمة صريحة (public/خدمة field-scoped) مُبرَّرة.
  ٣) أيّ نقطة field/layer-scoped تفتقد حارس ملكيّتها، أو نقطة غير محميّة وغير
     مُدرَجة ⇒ فشل برسالة تسمّي المسار + ما ينقصه.

اختبار سلامة الحارس (guard-integrity) يثبت أنّ الكاشف يميّز فعلاً نقطة محميّة عن
غير محميّة على مقتطف صناعيّ — كي لا يصير الحارس no-op بصمت.
"""

from __future__ import annotations

import ast
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

HERE = os.path.dirname(__file__)
RASTER_MAIN = os.path.normpath(os.path.join(HERE, "..", "services", "raster-service", "main.py"))
# توحيد main↔cert: المسارات فُكِّكت من main.py إلى routers/؛ يمسح الكاشف الاثنين معاً
# (main.py للحُرّاس المتبقّية + كلّ routers/*.py حيث صارت المعالِجات @router) — لا إضعاف.
RASTER_ROUTERS_DIR = os.path.normpath(
    os.path.join(HERE, "..", "services", "raster-service", "routers")
)

HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete"})

# حُرّاس الملكيّة/الخدمة المعروفون — وجود نداءٍ لأيّها داخل جسم الدالّة ⇒ النقطة
# محميّة بذلك الحارس.
FIELD_GUARD = "_require_field_tenant"
LAYER_GUARD = "_require_layer_tenant"
SERVICE_GUARD = "_require_service_token"
GUARD_NAMES: frozenset[str] = frozenset({FIELD_GUARD, LAYER_GUARD, SERVICE_GUARD})

# ─────────────────────────────────────────────────────────────────────────────
# قائمة field-scoped الخدميّة (FIELD_SCOPED_SERVICE_ONLY): نقاط ``/v1/fields/...``
# **ليست** مكشوفة للمتصفّح — تحمل ترويسة ``x_agent_token`` في توقيعها ويستدعيها
# العامل/الوكيل (خدمة-لخدمة) لا المتصفّح مباشرةً. تُحمى بـ``_require_service_token``
# (مطابقة الشقيقات — منع كشف الحقول)، فلا يلزمها ``_require_field_tenant`` المكشوف.
# كلّ إدخال هنا مُبرَّر صراحةً؛ ولا يُقبل إلّا إذا حمل فعلاً ترويسة التوكن + استدعى
# ``_require_service_token`` (يُفرَض أدناه)، فلا يمكن أن «يهرب» field-route مكشوف
# من فحص الملكيّة بمجرّد إدراجه هنا.
# ─────────────────────────────────────────────────────────────────────────────
FIELD_SCOPED_SERVICE_ONLY: set[str] = {
    # جسر استيراد STAC→معالجة: خلفيّة، يأخذ band hrefs ويبني VRT ثمّ /process.
    # يستدعيه العامل بعد /imagery/best — لا يُنادى من المتصفّح.
    "/v1/fields/{field_id}/process-from-stac",
    # معالجة CDSE (المزوّد الافتراضيّ): يحسب المؤشّر خادميّاً (evalscript) → COG. خلفيّة،
    # يستدعيه المنسّق (imagery_automation) خدمة-لخدمة بترويسة التوكن — لا يُنادى من المتصفّح.
    "/v1/fields/{field_id}/process-cdse",
    # وصفة مناطق الإدارة (VRT) من شبكة المؤشّر — خدمة-لخدمة (مطابقة الشقيقات).
    "/v1/fields/{field_id}/prescription",
    # كشف التغيّر المكاني للحقل بين تاريخين — خدمة-لخدمة (مطابقة الشقيقات).
    "/v1/fields/{field_id}/change",
}

# ─────────────────────────────────────────────────────────────────────────────
# قائمة الخدمة (SERVICE_ONLY): نقاط معالجة/مهامّ/رفع/أدوات تتطلّب توكن خدمة-لخدمة
# (``_require_service_token``). يُفرَض وجود النداء فعلاً (الإدراج وحده لا يكفي).
# مبنيّة من قراءة الكود: كلّ نقطة هنا تستدعي ``_require_service_token``.
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_ONLY: set[str] = {
    "/imagery/search",  # بحث متقدّم (POST) — توكن خدمة.
    "/imagery/timeseries/analyze",  # تحليل سلسلة زمنيّة من قيم محسوبة.
    "/imagery/timeseries/parallel",  # تحليل سلسلة زمنيّة متوازٍ.
    "/zones/classify",  # تصنيف مناطق الإدارة من بكسلات.
    "/change/detect",  # كشف تغيّر من شبكتين مُمرَّرتين.
    "/fvc/compute",  # نسبة التغطية النباتيّة من شبكة NDVI.
    "/sar/rvi",  # مؤشّر الغطاء الراداري RVI.
    "/terrain/slope",  # انحدار من DEM.
    "/salinity/classify",  # تصنيف الملوحة.
    "/salinity/calibrate",  # معايرة الملوحة.
    "/upload/raster",  # رفع راستر — يكتب ملفّات.
    "/upload/drone",  # رفع أورثوموزاييك درون.
    "/process",  # معالجة مؤشّر (غير متزامن → job).
    "/process/batch",  # معالجة دفعيّة لعدّة مؤشّرات.
    "/jobs/{job_id}",  # حالة مهمّة.
    "/jobs/{job_id}/result",  # نتيجة مهمّة.
    "/info/{layer_id}",  # معلومات طبقة راستر.
    "/cog/validate",  # تحقّق COG.
    "/storage/cleanup",  # تنظيف التخزين — يحذف ملفّات.
    "/storage/stats",  # إحصاء التخزين يكشف بنية داخلية؛ محمي بتوكن خدمة.
    "/offline/packs",  # سرد حزم offline محمي بتوكن خدمة.
    "/offline/packs/{pack_name}",  # تنزيل الحزم محمي بتوكن خدمة.
    "/indices",  # قائمة صيغ المؤشّرات (محميّة بتوكن خدمة في الكود الحاليّ).
    # ── كتالوج GIS سحابيّ + تحليلات حقول: تكشف بنية/تصدير ⇒ توكن خدمة + ترويسة ──
    "/v1/fields/analytics/geoparquet/export",  # تصدير GeoParquet لحقول — توكن خدمة.
    "/v1/tile-cache/stats",  # إحصاء ذاكرة بلاطات يكشف بنية داخلية — توكن خدمة.
}

# ─────────────────────────────────────────────────────────────────────────────
# القائمة العامّة (PUBLIC_CATALOG): نقاط مسموح بقاؤها بلا أيّ حارس، مع تبرير.
#
# المبدأ: بحث صور أقمار عامّة بـbbox (Sentinel/Landsat/DEM/STAC) — لا تقرأ بيانات
# مستأجِر ولا ملكيّة حقل/طبقة؛ معاملاتها إحداثيّات جغرافيّة عامّة. كذلك فحوص الصحّة.
# مراقبة التخزين وحزم offline ليست عامّة بعد إصلاح 20260626 وتُصنّف SERVICE_ONLY.
# ─────────────────────────────────────────────────────────────────────────────
PUBLIC_CATALOG: set[str] = {
    # ── بحث الصور الفضائيّة العامّ (بـbbox، لا بيانات مستأجِر) ──
    "/imagery/search/recent",  # آخر صور Sentinel-2 لمنطقة — بحث عامّ بـbbox.
    "/imagery/search/season",  # صور الموسم الزراعي — بحث عامّ بـbbox.
    "/imagery/search/radar",  # رادار Sentinel-1 — بحث عامّ بـbbox.
    "/imagery/search/landsat",  # أرشيف Landsat — بحث عامّ بـbbox.
    "/imagery/search/landsat-thermal",  # v147: بحث Landsat الحراريّ الفريد — بحث عامّ بـbbox.
    "/imagery/best",  # أفضل مشهد حديث — اختيار من بحث عامّ بـbbox.
    "/imagery/dem",  # نموذج ارتفاع Copernicus — مرجع جغرافيّ عامّ بـbbox.
    "/imagery/timeseries",  # توفّر المشاهد الزمنيّ — بحث عامّ بـbbox (GET، لا قيم).
    # ── بنية تحتيّة: فحوص صحّة/جاهزيّة + مقاييس (k8s/Prometheus، لا أسرار) ──
    "/healthz",  # فحص حياة العمليّة — بنية تحتيّة، لا بيانات.
    "/readyz",  # فحص جاهزيّة (وصول Earth Search) — بنية تحتيّة، لا بيانات.
    "/metrics",  # مقاييس Prometheus (عدّ مهامّ/طبقات مُجمَّع، لا بيانات مستأجِر).
    # ── مراقبة تخزين + حزم خرائط offline (خلفيّة ثابتة، لا بيانات مستأجِر) ──
    # ── كتالوج GIS سحابيّ عامّ (STAC/COG/imagery policy) — بحث/سياسة عامّة بـbbox ──
    "/stac",  # صفحة STAC الجذر — كتالوج صور عامّ، لا بيانات مستأجِر.
    "/stac/collections",  # مجموعات STAC — كتالوج عامّ.
    "/stac/mosaicjson",  # MosaicJSON — تركيب فسيفساء عامّ من مشاهد.
    "/v1/scenes/quality-score",  # تقييم جودة مشهد — حساب من بيانات وصفيّة عامّة.
    "/v1/cog/registry/preview",  # معاينة سجلّ COG — كتالوج عامّ، لا بيانات مستأجِر.
    "/v1/tiles/observability",  # مراقبة البلاطات (عدّ مُجمَّع) — لا بيانات مستأجِر.
    "/v1/imagery/backfill/policy",  # سياسة ردم الصور — قواعد ثابتة، لا بيانات.
    "/v1/imagery/quality/policy",  # سياسة جودة الصور — قواعد ثابتة، لا بيانات.
    "/v1/imagery/scenes/rank",  # ترتيب المشاهد — حساب من بيانات وصفيّة عامّة بـbbox.
    "/v1/imagery/mosaic/plan",  # خطّة فسيفساء — تخطيط عامّ من بحث بـbbox.
}


# ─────────────────────────────────────────────────────────────────────────────
# كاشف ast
# ─────────────────────────────────────────────────────────────────────────────
def _iter_app_routes(tree: ast.AST):
    """يولّد (المسار، عُقدة_الدالّة) لكلّ دالّة مُزخرفة بـ``@app.<method>(path)``."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in HTTP_METHODS:
                continue
            base = dec.func.value
            # @app.<m> (main.py) أو @router.<m> (بعد التفكيك في routers/) — كلاهما نقطة.
            if not (isinstance(base, ast.Name) and base.id in ("app", "router")):
                continue
            if not (dec.args and isinstance(dec.args[0], ast.Constant)):
                continue
            path = dec.args[0].value
            if isinstance(path, str):
                yield path, node


def _guard_calls(node: ast.AST) -> set[str]:
    """أسماء حُرّاس الملكيّة/الخدمة المُستدعاة داخل جسم الدالّة (Name أو Attribute)."""
    found: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name in GUARD_NAMES:
            found.add(name)
    return found


def _has_agent_token_header(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """هل لأيّ معامِل في التوقيع قيمة افتراضيّة ``Header(...)`` (ترويسة x_agent_token)؟

    يكشف النمط ``x_agent_token: str = Header(None)`` — مؤشّر «خدمة-لخدمة»: النقطة
    تتوقّع توكن خدمة في الترويسة (لا تُنادى من المتصفّح بلا توكن).
    """
    defaults: list[ast.expr] = list(node.args.defaults)
    defaults += [d for d in node.args.kw_defaults if d is not None]
    for d in defaults:
        for sub in ast.walk(d):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "Header"
            ):
                return True
    return False


def _collect_routes() -> list[tuple[str, set[str], bool]]:
    """يُرجِع (المسار، حُرّاس_مُستدعاة، هل_فيه_ترويسة_توكن) لكلّ نقطة ``@app`` في main.py."""
    import glob

    sources = [RASTER_MAIN] + sorted(glob.glob(os.path.join(RASTER_ROUTERS_DIR, "*.py")))
    routes: list[tuple[str, set[str], bool]] = []
    for src_path in sources:
        if not os.path.isfile(src_path):
            continue
        with open(src_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=src_path)
        for path, node in _iter_app_routes(tree):
            routes.append((path, _guard_calls(node), _has_agent_token_header(node)))
    return routes


# ─────────────────────────────────────────────────────────────────────────────
# التصنيف
# ─────────────────────────────────────────────────────────────────────────────
def _is_field_scoped(path: str) -> bool:
    return path.startswith("/v1/fields/{field_id}/")


def _is_layer_scoped(path: str) -> bool:
    # ``/tiles/{layer_id}/...`` أو ``/layers/{layer_id}/...``
    return path.startswith("/tiles/{layer_id}") or path.startswith("/layers/{layer_id}/")


def test_raster_main_exists_and_has_routes():
    """شبكة أمان: الملفّ موجود وثمّة نقاط فعلاً (وإلّا الحارس فارغ بصمت)."""
    assert os.path.isfile(RASTER_MAIN), f"main.py للراستر غير موجود: {RASTER_MAIN}"
    routes = _collect_routes()
    # عتبة دنيا متحفّظة: الخدمة بها عشرات النقاط؛ لو هبطت كثيراً فالكاشف معطوب.
    assert len(routes) >= 30, (
        f"عدد نقاط الراستر المكتشَف ({len(routes)}) أقلّ من المتوقَّع — الكاشف قد يكون معطوباً."
    )
    # تأكّد أنّ الكاشف يرى حُرّاساً فعلاً (وإلّا فحص الملكيّة لا معنى له).
    all_guards: set[str] = set()
    for _p, guards, _h in routes:
        all_guards |= guards
    assert FIELD_GUARD in all_guards, "الكاشف لم يرَ أيّ نداء _require_field_tenant."
    assert LAYER_GUARD in all_guards, "الكاشف لم يرَ أيّ نداء _require_layer_tenant."
    assert SERVICE_GUARD in all_guards, "الكاشف لم يرَ أيّ نداء _require_service_token."


def test_every_raster_endpoint_is_correctly_protected_for_its_class():
    """كلّ نقطة راستر محميّة بالحارس الصحيح لصنفها، أو مُدرَجة صراحةً (مُبرَّرة)."""
    violations: list[str] = []
    for path, guards, has_header in _collect_routes():
        if _is_field_scoped(path):
            if path in FIELD_SCOPED_SERVICE_ONLY:
                # خدمة-لخدمة: يجب أن تحمل ترويسة التوكن **و** تستدعي _require_service_token
                # فعلاً (لا «هروب» field-route مكشوف بمجرّد الإدراج).
                if not has_header or SERVICE_GUARD not in guards:
                    violations.append(
                        f"{path}: مُدرَج كـfield-scoped خدمة-لخدمة لكنّه لا يحمل ترويسة توكن "
                        f"أو لا يستدعي {SERVICE_GUARD} "
                        f"(header={has_header}, guards={sorted(guards)})."
                    )
            elif FIELD_GUARD not in guards:
                violations.append(
                    f"{path}: نقطة field-scoped مكشوفة بلا {FIELD_GUARD} (حماية IDOR) — "
                    f"أضِف الحارس أو أدرِجها في FIELD_SCOPED_SERVICE_ONLY إن كانت خدمة-لخدمة "
                    f"(guards={sorted(guards)})."
                )
        elif _is_layer_scoped(path):
            if LAYER_GUARD not in guards:
                violations.append(
                    f"{path}: نقطة layer-scoped بلا {LAYER_GUARD} (حماية IDOR) "
                    f"(guards={sorted(guards)})."
                )
        elif path in SERVICE_ONLY:
            if SERVICE_GUARD not in guards:
                violations.append(
                    f"{path}: مُدرَج كـservice-only لكنّه لا يستدعي {SERVICE_GUARD} "
                    f"(guards={sorted(guards)})."
                )
        elif path in PUBLIC_CATALOG:
            continue  # عامّ صراحةً — لا حارس مطلوب.
        else:
            violations.append(
                f"{path}: غير مُصنَّف — لا حارس ملكيّة/خدمة وليس في PUBLIC_CATALOG/SERVICE_ONLY. "
                f"أصلِح بإضافة الحارس المناسب أو إدراجه في القائمة الصريحة المناسبة "
                f"(guards={sorted(guards)}, header={has_header})."
            )
    assert violations == [], "نقاط راستر غير محميّة/مُصنَّفة بشكلٍ صحيح:\n" + "\n".join(
        f"  • {v}" for v in violations
    )


def test_allowlists_have_no_stale_entries():
    """لا إدخالات ميتة: كلّ مُدرَج في القوائم الصريحة لا يزال نقطةً حيّة فعلاً (نظافة)."""
    live_paths = {path for path, _g, _h in _collect_routes()}
    stale_public = sorted(PUBLIC_CATALOG - live_paths)
    stale_service = sorted(SERVICE_ONLY - live_paths)
    stale_field_svc = sorted(FIELD_SCOPED_SERVICE_ONLY - live_paths)
    assert stale_public == [], f"إدخالات ميتة في PUBLIC_CATALOG: {stale_public}"
    assert stale_service == [], f"إدخالات ميتة في SERVICE_ONLY: {stale_service}"
    assert stale_field_svc == [], f"إدخالات ميتة في FIELD_SCOPED_SERVICE_ONLY: {stale_field_svc}"


# ─────────────────────────────────────────────────────────────────────────────
# سلامة الحارس (guard-integrity): يثبت أنّ الكاشف يميّز فعلاً المحميّ عن غيره على
# مقتطف صناعيّ — كي لا يصير الحارس no-op بصمت لو كُسِر منطق الكشف.
# ─────────────────────────────────────────────────────────────────────────────
_SYNTHETIC = """
from fastapi import FastAPI, Header

app = FastAPI()


@app.get("/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png")
async def guarded_field(field_id: str):
    await _require_field_tenant(field_id)
    return {}


@app.get("/v1/fields/{field_id}/leaky")
async def unguarded_field(field_id: str):
    return {}


@app.get("/tiles/{layer_id}/{z}/{x}/{y}.png")
async def guarded_layer(layer_id: str):
    _require_layer_tenant(layer_id)
    return {}


@app.post("/process")
async def service_route(x_agent_token: str = Header(None)):
    _require_service_token(x_agent_token)
    return {}


@app.get("/imagery/search/recent")
async def public_route(west: float):
    return {}


def not_a_route():
    return None
"""


def _detect_synthetic() -> dict[str, tuple[set[str], bool]]:
    tree = ast.parse(_SYNTHETIC)
    out: dict[str, tuple[set[str], bool]] = {}
    for path, node in _iter_app_routes(tree):
        out[path] = (_guard_calls(node), _has_agent_token_header(node))
    return out


def test_guard_integrity_detects_protection_vs_none():
    """الكاشف يرى المسارات الخمسة ويميّز حُرّاسها (وترويسة التوكن) بدقّة."""
    result = _detect_synthetic()
    # not_a_route لا يُلتقَط؛ المسارات الخمسة فقط.
    assert set(result) == {
        "/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png",
        "/v1/fields/{field_id}/leaky",
        "/tiles/{layer_id}/{z}/{x}/{y}.png",
        "/process",
        "/imagery/search/recent",
    }
    guarded_field = result["/v1/fields/{field_id}/tiles/{z}/{x}/{y}.png"]
    leaky_field = result["/v1/fields/{field_id}/leaky"]
    guarded_layer = result["/tiles/{layer_id}/{z}/{x}/{y}.png"]
    service = result["/process"]
    public = result["/imagery/search/recent"]

    assert FIELD_GUARD in guarded_field[0], "كاشف معطوب: فاته _require_field_tenant."
    assert FIELD_GUARD not in leaky_field[0], "كاشف معطوب: ادّعى حارساً غير موجود."
    assert LAYER_GUARD in guarded_layer[0], "كاشف معطوب: فاته _require_layer_tenant."
    assert SERVICE_GUARD in service[0], "كاشف معطوب: فاته _require_service_token."
    assert service[1] is True, "كاشف معطوب: فاته ترويسة x_agent_token (Header)."
    assert public[0] == set(), "كاشف معطوب: ادّعى حارساً على نقطة عامّة."
    assert public[1] is False, "كاشف معطوب: ادّعى ترويسة توكن على نقطة عامّة."

    # ولو طبّقنا منطق التصنيف على المقتطف: الحقل المكشوف غير المحميّ يجب أن يُكشف.
    assert _is_field_scoped("/v1/fields/{field_id}/leaky")
    assert FIELD_GUARD not in leaky_field[0], (
        "حارس التصنيف لن يكشف حقلاً مكشوفاً بلا _require_field_tenant — no-op."
    )
