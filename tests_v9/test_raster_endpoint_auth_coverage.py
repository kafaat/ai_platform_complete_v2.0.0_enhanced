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
  • **layer_scoped** — ``/v1/tiles/{layer_id}/...`` و``/v1/layers/{layer_id}/tilejson``
    يجب أن تستدعي ``_require_layer_tenant(layer_id)`` (تفويض ملكيّة الطبقة).
  • **service_only** — معالجة/مهامّ/رفع/أدوات (``/v1/process``، ``/v1/jobs/{id}``،
    ``/v1/info/{layer_id}``، ``/v1/cog/validate``، ...) يجب أن تستدعي
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
# تُخزَّن بالصيغة المجرّدة الحاليّة (بعد التفكيك: routers/ تستورد الأسماء المجرّدة من
# raster_security_context). الكاشف يُطبّع النداءات المكتشَفة بإزالة الشرطة السفليّة
# البادئة، فيلتقط الصيغتين معاً: القديمة ``main._require_*`` (ما تبقّى في main.py وبعض
# الراوترات) والجديدة المجرّدة ``require_*`` — بلا إضعاف، مجرّد توحيد صيغة الاسم.
FIELD_GUARD = "require_field_tenant"
LAYER_GUARD = "require_layer_tenant"
SERVICE_GUARD = "require_service_token"
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
    # يستدعيه العامل بعد /v1/imagery/best — لا يُنادى من المتصفّح.
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
    "/v1/gis/admin-boundaries",  # A6/A7: قراءة طبقة الحدود المشتركة (خدمة-لخدمة، bbox مُطهَّر). (PR-R3: هُوجِر من /gis/admin-boundaries)
    "/v1/imagery/search",  # بحث متقدّم (POST) — توكن خدمة.
    "/v1/raw/process",  # فحص راستر خام: metadata+إحصاءات نطاقات (require_service_token في processing.py). (PR-R3: هُوجِر من /raw/process)
    "/v1/imagery/timeseries/analyze",  # تحليل سلسلة زمنيّة من قيم محسوبة. (PR-R3: هُوجِر من /imagery/timeseries/analyze)
    "/v1/imagery/timeseries/parallel",  # تحليل سلسلة زمنيّة متوازٍ. (PR-R3: هُوجِر من /imagery/timeseries/parallel)
    "/v1/zones/classify",  # تصنيف مناطق الإدارة من بكسلات. (PR-R3: هُوجِر من /zones/classify)
    "/v1/change/detect",  # كشف تغيّر من شبكتين مُمرَّرتين. (PR-R3: هُوجِر من /change/detect)
    "/v1/fvc/compute",  # نسبة التغطية النباتيّة من شبكة NDVI. (PR-R3: هُوجِر من /fvc/compute)
    "/v1/sar/rvi",  # مؤشّر الغطاء الراداري RVI. (PR-R3: هُوجِر من /sar/rvi)
    "/v1/terrain/slope",  # انحدار من DEM. (PR-R3: هُوجِر من /terrain/slope)
    "/v1/salinity/classify",  # تصنيف الملوحة. (PR-R3: هُوجِر من /salinity/classify)
    "/v1/salinity/calibrate",  # معايرة الملوحة. (PR-R3: هُوجِر من /salinity/calibrate)
    "/v1/upload/raster",  # رفع راستر — يكتب ملفّات. (PR-R2: هُوجِر من /upload/raster)
    "/v1/upload/drone",  # رفع أورثوموزاييك درون. (PR-R2: هُوجِر من /upload/drone)
    "/v1/process",  # معالجة مؤشّر (غير متزامن → job). (PR-R3: هُوجِر من /process)
    "/v1/process/batch",  # معالجة دفعيّة لعدّة مؤشّرات. (PR-R3: هُوجِر من /process/batch)
    "/v1/jobs/{job_id}",  # حالة مهمّة. (PR-R2: هُوجِر من /jobs/{job_id})
    "/v1/jobs/{job_id}/result",  # نتيجة مهمّة. (PR-R2: هُوجِر من /jobs/{job_id}/result)
    "/v1/info/{layer_id}",  # معلومات طبقة راستر. (PR-R3: هُوجِر من /info/{layer_id})
    "/v1/cog/validate",  # تحقّق COG. (PR-R3: هُوجِر من /cog/validate)
    "/v1/storage/cleanup",  # تنظيف التخزين — يحذف ملفّات. (PR-R2: هُوجِر من /storage/cleanup)
    "/v1/storage/stats",  # إحصاء التخزين يكشف بنية داخلية؛ محمي بتوكن خدمة. (PR-R2: هُوجِر من /storage/stats)
    "/v1/offline/packs",  # سرد حزم offline محمي بتوكن خدمة. (PR-R2: هُوجِر من /offline/packs)
    "/v1/offline/packs/{pack_name}",  # تنزيل الحزم محمي بتوكن خدمة. (PR-R2: هُوجِر من /offline/packs/{pack_name})
    "/v1/indices",  # قائمة صيغ المؤشّرات (محميّة بتوكن خدمة في الكود الحاليّ). (PR-R3: هُوجِر من /indices)
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
    "/v1/imagery/search/recent",  # آخر صور Sentinel-2 لمنطقة — بحث عامّ بـbbox.
    "/v1/imagery/search/season",  # صور الموسم الزراعي — بحث عامّ بـbbox.
    "/v1/imagery/search/radar",  # رادار Sentinel-1 — بحث عامّ بـbbox.
    "/v1/imagery/search/landsat",  # أرشيف Landsat — بحث عامّ بـbbox.
    "/v1/imagery/search/landsat-thermal",  # v147: بحث Landsat الحراريّ الفريد — بحث عامّ بـbbox.
    "/v1/imagery/best",  # أفضل مشهد حديث — اختيار من بحث عامّ بـbbox.
    "/v1/imagery/dem",  # نموذج ارتفاع Copernicus — مرجع جغرافيّ عامّ بـbbox.
    "/v1/imagery/timeseries",  # توفّر المشاهد الزمنيّ — بحث عامّ بـbbox (GET، لا قيم). (PR-R3: هُوجِر من /imagery/timeseries)
    # ── بنية تحتيّة: فحوص صحّة/جاهزيّة + مقاييس (k8s/Prometheus، لا أسرار) ──
    "/healthz",  # فحص حياة العمليّة — بنية تحتيّة، لا بيانات.
    "/readyz",  # فحص جاهزيّة (وصول Earth Search) — بنية تحتيّة، لا بيانات.
    "/metrics",  # مقاييس Prometheus (عدّ مهامّ/طبقات مُجمَّع، لا بيانات مستأجِر).
    # هويّة البناء — نفس صنف الثلاثة أعلاه لا استثناءً لها. مُصنَّفة
    # `infrastructure/provenance` في `platform_route_placement_contract.json`، وتُعيدها
    # `weather-service` و`soil-service` و`sahool-platform` بلا حارس كذلك. والحمولة نَسَبٌ
    # عامّ بالكامل — service · git_sha · build_id · source_repository · source_ref ·
    # metadata_source — تُقرأ من ملفّ صورة للقراءة فقط، ولا سرّ فيها ولا بيانات مستأجِر.
    # وحجبُها يكسر الغرض: مُنسّق النشر يقرؤها ليُثبِت أنّ الصورة الجارية هي المُختبَرة.
    "/runtime-identity",  # نَسَب بناء غير قابل للتغيير — بنية تحتيّة، لا بيانات.
    # ── مراقبة تخزين + حزم خرائط offline (خلفيّة ثابتة، لا بيانات مستأجِر) ──
    # ── كتالوج GIS سحابيّ عامّ (STAC/COG/imagery policy) — بحث/سياسة عامّة بـbbox ──
    "/v1/stac",  # صفحة STAC الجذر — كتالوج صور عامّ، لا بيانات مستأجِر. (PR-R3: هُوجِر من /stac)
    "/v1/stac/collections",  # مجموعات STAC — كتالوج عامّ. (PR-R3: هُوجِر من /stac/collections)
    "/v1/stac/mosaicjson",  # MosaicJSON — تركيب فسيفساء عامّ من مشاهد. (PR-R3: هُوجِر من /stac/mosaicjson)
    "/v1/scenes/quality-score",  # تقييم جودة مشهد — حساب من بيانات وصفيّة عامّة.
    "/v1/cog/registry/preview",  # معاينة سجلّ COG — كتالوج عامّ، لا بيانات مستأجِر.
    "/v1/tiles/observability",  # مراقبة البلاطات (عدّ مُجمَّع) — لا بيانات مستأجِر.
    "/v1/providers/status",  # V63.4: سِجِلّ المزوّدين الوصفيّ (active/planned) — بيانات ثابتة عامّة، لا مستأجِر.
    "/v1/imagery/backfill/policy",  # سياسة ردم الصور — قواعد ثابتة، لا بيانات.
    "/v1/imagery/quality/policy",  # سياسة جودة الصور — قواعد ثابتة، لا بيانات.
    "/v1/imagery/scenes/rank",  # ترتيب المشاهد — حساب من بيانات وصفيّة عامّة بـbbox.
    "/v1/imagery/mosaic/plan",  # خطّة فسيفساء — تخطيط عامّ من بحث بـbbox.
    # ── طبقات تضاريس/تربة من مصادر عالميّة عامّة (Copernicus DEM / SoilGrids) — ──
    # لا تقرأ بيانات مستأجِر؛ إحداثيّات z/x/y جغرافيّة عامّة (نظير /imagery/dem). fail-closed
    # شفّاف بلا مصدر مُهيّأ. tid سياقٌ ناعم (نسبة/معدّل) لا حارس ملكيّة بيانات.
    "/v1/elevation/hillshade/{z}/{x}/{y}.png",  # ظلّ تضاريس من DEM عامّ.
    "/v1/slope/{z}/{x}/{y}.png",  # انحدار مُصنّف من DEM عامّ.
    "/v1/terrain/tilejson",  # TileJSON طبقة تضاريس — وصف عامّ + توفّر.
    "/v1/terrain/status",  # حالة تهيئة DEM — علم بيئة عامّ، لا بيانات مستأجِر.
    "/v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png",  # خاصّيّة تربة من SoilGrids عالميّ.
    "/v1/soil/tilejson",  # TileJSON طبقة تربة — وصف عامّ + توفّر + تحذير.
    "/v1/soil/properties",  # قائمة خصائص/أعماق التربة المدعومة — بيانات وصفيّة ثابتة.
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


def _call_name(sub: ast.Call) -> str | None:
    """اسم الدالّة المُستدعاة (Name.id أو Attribute.attr)، أو None."""
    fn = sub.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _guard_calls(node: ast.AST, aliases: dict[str, frozenset[str]] | None = None) -> set[str]:
    """أسماء حُرّاس الملكيّة/الخدمة المُستدعاة داخل جسم الدالّة (Name أو Attribute).

    ``aliases`` (اختياريّ): خريطة اسم-دالّة → مجموعة الحُرّاس القانونيّة التي تستدعيها
    فعلاً (غلاف محليّ رفيع يفوّض إلى حارس معروف). النداء إلى غلافٍ كهذا يُحتسَب حمايةً
    بذلك الحارس — إثباتيّ لا إضعاف: الدالّة تستدعي الحارس فعلاً. مثال: ``_require_field``
    في ``routers/cdse_tiles.py`` يستدعي ``require_field_tenant(...)``.
    """
    found: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        name = _call_name(sub)
        if name is None:
            continue
        # توحيد الصيغة القديمة (``_require_*`` / ``main._require_*``) مع الجديدة
        # المجرّدة (``require_*``) بإزالة الشرطة السفليّة البادئة، فيُخزَّن الاسم القانونيّ.
        canonical = name.lstrip("_")
        if canonical in GUARD_NAMES:
            found.add(canonical)
        elif aliases and name in aliases:
            found |= aliases[name]
    return found


def _build_guard_aliases(trees: list[ast.AST]) -> dict[str, frozenset[str]]:
    """يبني خريطة أغلفة الحُرّاس: اسم دالّة → الحُرّاس القانونيّة التي تستدعيها (تعدّيّاً).

    غلاف محليّ رفيع مثل ``async def _require_field(fid): await require_field_tenant(...)``
    يُدخِله التفكيك (phase13–15)؛ الكاشف لا «يتتبّع» النداء غير المباشر افتراضيّاً. نحلّ
    المستوى (وتعدّيّاً غلاف-يستدعي-غلافاً) كي يُحتسَب النداء إلى الغلاف حمايةً بحارسه —
    دون إضعاف: نُدرِج فقط دوالّ تستدعي حارساً معروفاً فعلاً.
    """
    func_nodes: dict[str, ast.AST] = {}
    for tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                func_nodes[n.name] = n
    # المرور الأوّل: الحُرّاس القانونيّة المُستدعاة مباشرةً في جسم كلّ دالّة.
    resolved: dict[str, set[str]] = {}
    for fname, n in func_nodes.items():
        direct = _guard_calls(n)  # بلا أغلفة — نداء حارس قانونيّ مباشر فقط.
        if direct:
            resolved[fname] = set(direct)
    # نقطة ثابتة: غلافٌ يستدعي غلافاً يرث حُرّاسه.
    changed = True
    while changed:
        changed = False
        for fname, n in func_nodes.items():
            cur = resolved.get(fname, set())
            for sub in ast.walk(n):
                if not isinstance(sub, ast.Call):
                    continue
                cn = _call_name(sub)
                if cn and cn in resolved:
                    new = resolved[cn] - cur
                    if new:
                        cur = cur | new
                        resolved[fname] = cur
                        changed = True
    return {k: frozenset(v) for k, v in resolved.items()}


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
    trees: list[ast.AST] = []
    for src_path in sources:
        if not os.path.isfile(src_path):
            continue
        with open(src_path, encoding="utf-8") as f:
            trees.append(ast.parse(f.read(), filename=src_path))
    # أغلفة الحُرّاس المحليّة (مثل _require_field في cdse_tiles) تُحلّ أوّلاً كي يُحتسَب
    # النداء غير المباشر حمايةً بحارسه — دون إضعاف.
    aliases = _build_guard_aliases(trees)
    routes: list[tuple[str, set[str], bool]] = []
    for tree in trees:
        for path, node in _iter_app_routes(tree):
            routes.append((path, _guard_calls(node, aliases), _has_agent_token_header(node)))
    return routes


# ─────────────────────────────────────────────────────────────────────────────
# التصنيف
# ─────────────────────────────────────────────────────────────────────────────
def _is_field_scoped(path: str) -> bool:
    return path.startswith("/v1/fields/{field_id}/")


def _is_layer_scoped(path: str) -> bool:
    # ``/v1/tiles/{layer_id}/...`` أو ``/v1/layers/{layer_id}/...`` (PR-R4: هُوجِرا من
    # ``/tiles/{layer_id}/...``/``/layers/{layer_id}/...``)
    return path.startswith("/v1/tiles/{layer_id}") or path.startswith("/v1/layers/{layer_id}/")


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
