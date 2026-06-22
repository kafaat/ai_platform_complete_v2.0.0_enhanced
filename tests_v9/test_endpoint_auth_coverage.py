"""حارس تغطية المصادقة على نقاط الـHTTP (Endpoint Auth Coverage Guard).

يحوّل قاعدة "كلّ نقطة حسّاسة يجب أن تُصادَق" إلى بوّابة CI مفروضة: يفشل إن
عُرِّفت نقطة HTTP في منصّة ``sahool-platform`` بلا مصادقة *ولم* تكن مُصنَّفة
صراحةً في قائمة ``PUBLIC_ALLOWLIST`` العامّة (مع تبرير لكلّ منها).

الآليّة (عبر ``ast`` لا regex — أمتن أمام الالتفاف/التنسيق):
  ١) يمسح كلّ ``*.py`` تحت ``services/sahool-platform/api/`` (main.py + routers/).
  ٢) لكلّ دالّة مُزخرفة بـ``@app.<method>`` أو ``@router.<method>`` (get/post/
     put/patch/delete) يستخرج المسار، ويفحص هل لأيّ معامِل قيمة افتراضيّة
     ``Depends(...)`` يمرّ سلسلة ندائها بأحد تبعيّات المصادقة المعروفة
     (``require_permission`` / ``get_current_user`` / … إلخ). إن وُجدت ⇒
     "مُصادَقة".
  ٣) يؤكّد: كلّ نقطة إمّا مُصادَقة أو ضمن ``PUBLIC_ALLOWLIST``. أيّ نقطة جديدة
     بلا مصادقة وخارج القائمة ⇒ فشل برسالة تسمّي المسار + الملفّ.

اختبار سلامة الحارس (guard-integrity) يثبت أنّ الكاشف يميّز فعلاً المُصادَق عن
غير المُصادَق على مقتطف صناعيّ — كي لا يصير الحارس صامتاً (no-op) بصمت.

ملاحظة تنسيق #410: أربع نقاط (decision/for-location، decision/explain،
consistency/irrigation، consistency/freshness) تُضاف لها المصادقة في فرع موازٍ
(#410)، فنستثنيها كليّاً من نطاق هذا الحارس تفادياً للتسابق — انظر
``ISSUE_410_PENDING``.
"""

from __future__ import annotations

import ast
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

HERE = os.path.dirname(__file__)
API_DIR = os.path.normpath(os.path.join(HERE, "..", "services", "sahool-platform", "api"))

# أسماء تبعيّات المصادقة المعروفة: وجود أيّها داخل ``Depends(...)`` لمعامِل ⇒ النقطة
# مُصادَقة. (``require_permission``/``require_role`` نداءات تُرجِع تبعيّة؛
# ``get_current_user``/``_require_service_token`` تُمرَّر كاسم مباشر.)
AUTH_DEPENDENCIES: frozenset[str] = frozenset(
    {
        "require_permission",
        "require_role",
        "require_admin",
        "require_superuser",
        "require_tenant",
        "get_current_user",
        "_require_service_token",
    }
)

HTTP_METHODS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete"})

# ملفّات مرجعيّة مُستثناة من النطاق: ليست جزءاً من تطبيق المنصّة (لا تُضمَّن عبر
# ``app.include_router``)، وتُنشئ تطبيق FastAPI خاصّاً بها لأغراض التوثيق.
#   • ``chat_proxy_reference.py``: نمط مرجعيّ لـproxy آمن لـClaude — *مُصادَق*
#     فعلاً لكن عبر تحقّق JWT يدويّ داخل الجسم (``_tenant_from_jwt``) لا عبر
#     ``Depends(...)`` في التوقيع؛ فلا يلتقطه الكاشف ولا هو نقطة منصّة حيّة.
EXCLUDED_FILES: frozenset[str] = frozenset({"chat_proxy_reference.py"})

# نقاط #410 — تُضاف لها المصادقة في فرع موازٍ؛ مُستثناة من نطاق هذا الحارس كليّاً
# لتفادي التسابق (لا نُدرجها في القائمة ولا نطالبها بمصادقة هنا).
ISSUE_410_PENDING: frozenset[str] = frozenset(
    {
        "/api/v1/decision/for-location",
        "/api/v1/decision/explain",
        "/api/v1/consistency/irrigation",
        "/api/v1/consistency/freshness",
    }
)

# ─────────────────────────────────────────────────────────────────────────────
# القائمة العامّة (PUBLIC_ALLOWLIST): نقاط مسموح بقاؤها بلا مصادقة، مع تبرير.
#
# المبدأ: نقاط *حساب نقيّ/مرجع معرفيّ* تأخذ معاملاتها من الاستعلام وتُرجِع معرفة
# محسوبة (أدلّة محاصيل، تقاويم، حاسبات زراعيّة) — بلا ``tenant_connection`` ولا
# قاعدة بيانات ولا بيانات مخصوصة بمستأجِر — فلا تكشف أصولاً. أضِف أيّ نقطة جديدة
# هنا *فقط* إن كانت عامّة حقّاً، وإلّا أضِف لها ``Depends(require_permission(...))``.
# ─────────────────────────────────────────────────────────────────────────────
PUBLIC_ALLOWLIST: set[str] = {
    # ── بنية تحتيّة: فحوص صحّة/جاهزيّة (تُستدعى من k8s/المُوازِن، لا أسرار) ──
    "/healthz",  # فحص حياة العمليّة — بنية تحتيّة، لا بيانات.
    "/readyz",  # فحص جاهزيّة (DB/تبعيّات) — بنية تحتيّة، لا بيانات.
    # ── المصادقة نفسها: إصدار التوكن لا يمكن أن يتطلّب توكناً (دجاجة/بيضة) ──
    "/api/v1/auth/login",  # تسجيل الدخول يُصدِر JWT — عامّ بالضرورة.
    "/api/v1/auth/signup",  # إنشاء حساب يُصدِر JWT — عامّ بالضرورة.
    # ── أمثال/تقاويم زراعيّة تراثيّة (معرفة عامّة، بلا حالة) ──
    "/api/v1/agricultural-proverbs",  # أمثال زراعيّة تراثيّة — معرفة عامّة.
    "/api/v1/agricultural-proverbs/for-date",  # أمثال ليوم — حساب تقويميّ نقيّ.
    "/api/v1/calendars/today",  # تقويم اليوم — حساب فلكيّ/تقويميّ نقيّ.
    "/api/v1/calendars/lunar-mansions",  # منازل القمر — مرجع فلكيّ ثابت.
    "/api/v1/calendars/himyarite-months",  # الأشهر الحِميَريّة — مرجع تراثيّ.
    "/api/v1/calendars/regional-profiles",  # ملفّات تقاويم إقليميّة — مرجع.
    "/api/v1/calendars/context",  # سياق تقويميّ — حساب نقيّ.
    "/api/v1/cultural-calendar",  # تقويم ثقافيّ زراعيّ — مرجع عامّ.
    "/api/v1/regional-calendar",  # تقويم إقليميّ — مرجع عامّ.
    "/api/v1/astronomical-timing/stars",  # توقيت نجميّ — مرجع فلكيّ ثابت.
    # ── أطالس/أدلّة محاصيل ومناطق زراعيّة (معرفة مرجعيّة، بلا حالة مستأجِر) ──
    "/api/v1/agro-zones/list",  # قائمة المناطق الزراعيّة — مرجع.
    "/api/v1/agro-zones/profile",  # ملفّ منطقة — مرجع.
    "/api/v1/agro-zones/identify",  # تحديد منطقة من إحداثيّات — حساب نقيّ.
    "/api/v1/agro-zones/suited-crops",  # محاصيل ملائمة لمنطقة — مرجع.
    "/api/v1/agro-zones/by-elevation",  # مناطق حسب الارتفاع — مرجع.
    "/api/v1/agro-zones/identify-smart",  # تحديد منطقة ذكيّ — حساب نقيّ.
    "/api/v1/aromatic-crops/list",  # محاصيل عطريّة — مرجع.
    "/api/v1/climate-analogs/list",  # نظائر مناخيّة — مرجع.
    "/api/v1/climate-analogs/detail",  # تفصيل نظير مناخيّ — مرجع.
    "/api/v1/climate-analogs/desert-crops",  # محاصيل صحراويّة — مرجع.
    "/api/v1/climate-analogs/strategic-tiers",  # طبقات استراتيجيّة — مرجع.
    "/api/v1/climate-analogs/strategy",  # استراتيجيّة مناخيّة — مرجع.
    "/api/v1/coffee/site-suitability",  # ملاءمة موقع البنّ — حساب نقيّ.
    "/api/v1/coffee/guide",  # دليل البنّ — مرجع.
    "/api/v1/coffee/varieties",  # أصناف البنّ — مرجع.
    "/api/v1/coffee/pests",  # آفات البنّ — مرجع.
    "/api/v1/high-value-crops/list",  # محاصيل عالية القيمة — مرجع.
    "/api/v1/high-value-crops/detail",  # تفصيل محصول — مرجع.
    "/api/v1/niche-crops/list",  # محاصيل متخصّصة — مرجع.
    "/api/v1/niche-crops/detail",  # تفصيل محصول متخصّص — مرجع.
    "/api/v1/fodder-alternatives/list",  # بدائل علفيّة — مرجع.
    "/api/v1/introduction/candidates",  # محاصيل مُرشَّحة للإدخال — مرجع/حساب.
    "/api/v1/introduction/card",  # بطاقة محصول مُدخَل — مرجع.
    "/api/v1/wofost/crop-types",  # أنواع محاصيل WOFOST — مرجع نموذج.
    "/api/v1/wofost/adaptation-guidance",  # إرشاد تكييف WOFOST — حساب نقيّ.
    # ── حاسبات/أدلّة زراعيّة (تأخذ معاملات، تُرجِع نتيجة محسوبة، بلا حالة) ──
    "/api/v1/chemical-safety/banned",  # قائمة مبيدات محظورة — مرجع تنظيميّ عامّ.
    "/api/v1/diagnose/symptoms",  # قائمة أعراض للتشخيص — مرجع.
    "/api/v1/economics/cost-categories",  # فئات التكلفة — مرجع.
    "/api/v1/economics/break-even",  # حاسبة نقطة التعادل — حساب نقيّ.
    "/api/v1/ipm/pests",  # آفات IPM — مرجع.
    "/api/v1/ipm/plan",  # خطّة IPM — حساب من معاملات.
    "/api/v1/ipm/crop-pests",  # آفات محصول — مرجع.
    "/api/v1/irrigation/soil-types",  # أنواع التربة للريّ — مرجع.
    "/api/v1/irrigation/moisture-decision",  # قرار رطوبة — حساب نقيّ من معاملات.
    "/api/v1/orchard/plan",  # خطّة بستان — حساب من معاملات.
    "/api/v1/orchard/economics",  # اقتصاد بستان — حساب نقيّ.
    "/api/v1/planting/crops",  # محاصيل الزراعة — مرجع.
    "/api/v1/planting/window",  # نافذة الزراعة — حساب تقويميّ.
    "/api/v1/planting/check",  # فحص توقيت زراعة — حساب نقيّ.
    "/api/v1/postharvest/moisture-check",  # فحص رطوبة ما بعد الحصاد — حساب نقيّ.
    "/api/v1/postharvest/pests",  # آفات التخزين — مرجع.
    "/api/v1/postharvest/best-practices",  # ممارسات فضلى — مرجع.
    "/api/v1/practices/list",  # قائمة ممارسات — مرجع.
    "/api/v1/practices/guide",  # دليل ممارسات — مرجع.
    "/api/v1/propagation/methods",  # طرق الإكثار — مرجع.
    "/api/v1/propagation/method-guide",  # دليل طريقة إكثار — مرجع.
    "/api/v1/propagation/crop",  # إكثار محصول — مرجع.
    "/api/v1/propagation/rootstock",  # أصول التطعيم — مرجع.
    "/api/v1/rotation/principles",  # مبادئ الدورة الزراعيّة — مرجع.
    "/api/v1/rotation/evaluate",  # تقييم دورة — حساب نقيّ.
    "/api/v1/rotation/suggest",  # اقتراح دورة — حساب نقيّ.
    "/api/v1/seasonal-risk/calendar",  # تقويم المخاطر الموسميّة — مرجع.
    "/api/v1/seasonal-risk/stage-check",  # فحص مرحلة — حساب نقيّ.
    "/api/v1/seasonal-risk/chill-hours",  # ساعات البرودة — حساب نقيّ.
    "/api/v1/seed/criteria",  # معايير البذور — مرجع.
    "/api/v1/seed/germination-rate",  # معدّل الإنبات — حساب نقيّ.
    "/api/v1/seed/storage-check",  # فحص تخزين البذور — حساب نقيّ.
    "/api/v1/seed/sowing-depth",  # عمق البذر — حساب نقيّ.
    "/api/v1/soil-sampling/subsamples",  # عيّنات فرعيّة — حساب نقيّ.
    "/api/v1/soil-sampling/depth",  # عمق العيّنة — حساب نقيّ.
    "/api/v1/soil-sampling/protocol",  # بروتوكول العيّنات — مرجع.
    "/api/v1/water-harvesting/potential",  # جهد حصاد المياه — حساب نقيّ.
    "/api/v1/water-harvesting/methods",  # طرق حصاد المياه — مرجع.
    "/api/v1/water-harvesting/method-guide",  # دليل طريقة — مرجع.
    "/api/v1/water-harvesting/upstream-flood",  # فيضان أعلى المجرى — حساب نقيّ.
    "/api/v1/water-sensitivity/crops",  # حساسيّة المياه للمحاصيل — مرجع.
    "/api/v1/water-sensitivity/calendar",  # تقويم الحساسيّة — مرجع.
    "/api/v1/water-sensitivity/wheat-calendar",  # تقويم القمح — مرجع.
    "/api/v1/geo-locate/field",  # تحديد جغرافيّ من إحداثيّات — حساب نقيّ، لا DB.
    "/api/v1/geo-locate/recommend",  # توصية من إحداثيّات — حساب نقيّ، لا DB.
    # تركيب حالة من معاملات مُمرَّرة — حساب نقيّ (لا يقرأ DB؛ field_id وسم فقط):
    "/api/v1/field/operational-state",
    "/api/v1/recommendations/capacity-profiles",  # ملفّات القدرة — مرجع ثابت.
    "/api/v1/weather/current",  # طقس حاليّ — معطى بيئيّ عامّ (إحداثيّات).
    "/api/v1/weather/forecast",  # توقّع الطقس — معطى بيئيّ عامّ.
    "/api/v1/weather/historical",  # طقس تاريخيّ — معطى بيئيّ عامّ.
}


def _iter_route_functions(tree: ast.AST):
    """يولّد (اسم_الدالّة، المسار، عُقدة_الدالّة) لكلّ دالّة موجِّه HTTP في الشجرة."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in HTTP_METHODS:
                continue
            base = dec.func.value
            if not (isinstance(base, ast.Name) and base.id in ("app", "router")):
                continue
            if not (dec.args and isinstance(dec.args[0], ast.Constant)):
                continue
            path = dec.args[0].value
            if isinstance(path, str):
                yield node.name, path, node


def _default_grants_auth(default: ast.expr) -> bool:
    """هل القيمة الافتراضيّة لمعامِل (مثل ``Depends(get_current_user)``) تمنح مصادقة؟

    نمشي شجرة التعبير ونبحث عن أيّ اسم/سمة من ``AUTH_DEPENDENCIES`` — يغطّي
    ``Depends(get_current_user)`` و``Depends(require_permission(Permission.X))``
    معاً (الأوّل ``Name``، الثاني نداء داخل نداء).
    """
    for sub in ast.walk(default):
        if isinstance(sub, ast.Name) and sub.id in AUTH_DEPENDENCIES:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in AUTH_DEPENDENCIES:
            return True
    return False


def _function_is_authenticated(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """هل لأيّ معامِل في الدالّة قيمة افتراضيّة ``Depends(...)`` تمنح مصادقة؟"""
    defaults: list[ast.expr] = list(node.args.defaults)
    defaults += [d for d in node.args.kw_defaults if d is not None]
    return any(_default_grants_auth(d) for d in defaults)


def _api_python_files() -> list[str]:
    """كلّ ``*.py`` تحت api/ (main.py + routers/)، عدا ``__init__.py``."""
    files: list[str] = []
    for root, _dirs, names in os.walk(API_DIR):
        for name in names:
            if name.endswith(".py") and name != "__init__.py":
                if name in EXCLUDED_FILES:
                    continue  # ملفّ مرجعيّ خارج النطاق (انظر EXCLUDED_FILES).
                files.append(os.path.join(root, name))
    return sorted(files)


def _collect_unauthenticated_routes() -> list[tuple[str, str]]:
    """يُرجِع (المسار، المسار_النسبيّ_للملفّ) لكلّ نقطة بلا مصادقة (عدا #410)."""
    offenders: list[tuple[str, str]] = []
    for fp in _api_python_files():
        with open(fp, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=fp)
        rel = os.path.relpath(fp, API_DIR)
        for _name, path, node in _iter_route_functions(tree):
            if path in ISSUE_410_PENDING:
                continue  # نطاق #410 — مُستثنىً لتفادي التسابق.
            if _function_is_authenticated(node):
                continue
            offenders.append((path, rel))
    return offenders


def test_api_directory_exists_and_has_routes():
    """شبكة أمان: المسار صحيح وثمّة نقاط فعلاً (وإلّا الحارس فارغ بصمت)."""
    assert os.path.isdir(API_DIR), f"دليل api غير موجود: {API_DIR}"
    files = _api_python_files()
    assert any(f.endswith("main.py") for f in files), "main.py غير موجود تحت api/"
    total_routes = 0
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=fp)
        total_routes += sum(1 for _ in _iter_route_functions(tree))
    # عتبة دنيا متحفّظة: المنصّة بها مئات النقاط؛ لو هبطت لصفر فالكاشف معطوب.
    assert total_routes >= 100, (
        f"عدد النقاط المكتشَف ({total_routes}) أقلّ من المتوقَّع — الكاشف قد يكون معطوباً."
    )


def test_every_unauthenticated_endpoint_is_in_public_allowlist():
    """كلّ نقطة بلا مصادقة يجب أن تكون مُصنَّفة صراحةً في ``PUBLIC_ALLOWLIST``."""
    offenders = _collect_unauthenticated_routes()
    not_allowlisted = sorted(
        {(path, rel) for path, rel in offenders if path not in PUBLIC_ALLOWLIST}
    )
    assert not_allowlisted == [], (
        "نقاط HTTP مُعرَّفة بلا مصادقة وخارج PUBLIC_ALLOWLIST:\n"
        + "\n".join(f"  • {path}  ({rel})" for path, rel in not_allowlisted)
        + "\n\nأصلِح بأحد أمرين: (أ) أضِف مصادقة "
        "`Depends(require_permission(Permission.X))` (أو get_current_user)، "
        "أو (ب) إن كانت النقطة عامّة حقّاً أضِفها إلى PUBLIC_ALLOWLIST "
        "في هذا الملفّ مع تعليق يُبرّر علنيّتها."
    )


def test_allowlist_has_no_stale_entries():
    """لا إدخالات ميتة في القائمة: كلّ مُدرَج موجود فعلاً وغير مُصادَق (نظافة)."""
    live_unauth = {path for path, _rel in _collect_unauthenticated_routes()}
    # /healthz و/readyz نقطتا @app في main.py ويلتقطهما الكاشف؛ تبقى البقيّة كذلك.
    stale = sorted(PUBLIC_ALLOWLIST - live_unauth)
    assert stale == [], (
        "إدخالات في PUBLIC_ALLOWLIST لم تَعُد نقاطاً غير مُصادَقة (صارت مُصادَقة "
        f"أو حُذِفت) — نظّفها: {stale}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# سلامة الحارس (guard-integrity): يثبت أنّ الكاشف يميّز فعلاً المُصادَق عن غيره
# على مقتطف صناعيّ — كي لا يصير الحارس no-op بصمت.
# ─────────────────────────────────────────────────────────────────────────────

_SYNTHETIC = """
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/public/calc")
def public_calc(x: int = 0):
    return {"x": x}


@router.get("/secure/perm")
def secure_perm(user=Depends(require_permission(Permission.AUDIT_VIEW))):
    return {}


@router.post("/secure/user")
def secure_user(user=Depends(get_current_user)):
    return {}


@app.get("/internal/svc")
def internal_svc(_=Depends(_require_service_token)):
    return {}


def not_a_route():
    return None
"""


def _detect(snippet: str) -> dict[str, bool]:
    tree = ast.parse(snippet)
    out: dict[str, bool] = {}
    for _name, path, node in _iter_route_functions(tree):
        out[path] = _function_is_authenticated(node)
    return out


def test_guard_integrity_detects_auth_vs_no_auth():
    """الكاشف يرى المسارات الأربعة ويميّز المُصادَق (3) عن غير المُصادَق (1)."""
    result = _detect(_SYNTHETIC)
    # غير الموجِّه (not_a_route) لا يُلتقَط.
    assert set(result) == {
        "/public/calc",
        "/secure/perm",
        "/secure/user",
        "/internal/svc",
    }
    assert result["/public/calc"] is False, "كاشف معطوب: عدّ نقطة عامّة مُصادَقة."
    assert result["/secure/perm"] is True, "كاشف معطوب: فاته require_permission."
    assert result["/secure/user"] is True, "كاشف معطوب: فاته get_current_user."
    assert result["/internal/svc"] is True, "كاشف معطوب: فاته _require_service_token."
