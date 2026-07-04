"""حارس عقد «backend ⇒ واجهة»: كلّ endpoint جوهريّ يبقى بدليل واجهة/hook.

يستدعي منطق scripts/ci/endpoint_ui_coverage_gate.py نفسه (لا نسخ) — إن أُزيل
استدعاء واجهة لمسار جوهريّ (مثل farm-ledger/profitability أو crop-cards) يفشل
الحارس محليّاً وفي CI قبل أن تصبح القدرة الخلفيّة يتيمة عن المستخدم من جديد.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "ci" / "endpoint_ui_coverage_gate.py"
CONFIG = REPO / "config" / "endpoint_ui_coverage.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("endpoint_ui_coverage_gate_mod", GATE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_no_waiver_has_real_ui_evidence() -> None:
    """حارس ضدّ الدَّين الوهميّ: أيّ إعفاء backlog-ui له دليل واجهة حقيقيّ (تطابق
    حدوديّ في طبقة-API/هوك/مكوّن) يجب ترقيته إلى core لا إبقاؤه ديناً كاذباً.

    يمنع تضخّم سجلّ الإعفاءات بمسارات مرتبطة فعلاً — كما اكتُشف في مراجعة الوكلاء
    (183 إعفاءً وهميّاً رُقّيت). admin-ops/operational مستثناة (لا تتطلّب شاشة).
    """
    import re as _re

    mod = _load_gate()
    waived = mod.load_waivers()
    # ملفّات طبقة-API/مكوّن فقط (لا اختبارات) — دليل تشغيليّ حقيقيّ.
    fe: list[tuple[str, str]] = []
    for root in mod.FRONTEND_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for f in base.rglob("*"):
            rel = str(f.relative_to(REPO))
            if f.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".dart"}:
                continue
            if ".test." in rel or "/e2e/" in rel:
                continue
            fe.append((rel, f.read_text(encoding="utf-8", errors="ignore")))

    def boundary_hit(path: str) -> str | None:
        stem = _re.split(r"\{", path)[0].rstrip("/")
        alt = stem.replace("/api/v1/auth", "/auth")
        cands = {c for c in (stem, alt) if len(c) > len("/api/v1/") or c.startswith("/auth")}
        for rel, txt in fe:
            for c in cands:
                pat = _re.escape(c) + r"""(?:['"`?]|/\$\{|/[a-z]|$)"""
                if _re.search(pat, txt) and any(
                    k in rel
                    for k in (
                        "/services/",
                        "/hooks/",
                        "api.ts",
                        "/components/",
                        "/sections/",
                        "/screens/",
                    )
                ):
                    return rel
        return None

    false_debt = []
    for ep, w in waived.items():
        if w.get("reason_category") != "backlog-ui":
            continue  # admin-ops/operational: إعفاء دائم مشروع.
        ev = boundary_hit(ep)
        if ev:
            false_debt.append(f"{ep} → {ev}")
    assert not false_debt, "إعفاءات backlog-ui لها دليل واجهة حقيقيّ (رقّها إلى core): " + "; ".join(
        false_debt[:12]
    )


@pytest.mark.unit
def test_config_is_valid_and_nonempty() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["core_endpoints"], "العقد فارغ — يجب أن يلزم مسارات جوهريّة"
    assert cfg["classifications"], "التصنيف فارغ"
    audiences = {"farmer", "agronomist", "manager", "admin", "internal"}
    for entry in cfg["core_endpoints"]:
        assert entry["audience"] in audiences, entry
        assert entry["evidence"].startswith("/"), entry
        # المسارات الداخليّة لا تُطالَب بواجهة مستخدم — لا يجوز إلزامها في العقد.
        assert entry["audience"] != "internal", f"internal endpoint في العقد الملزم: {entry}"
    for rule in cfg["classifications"]:
        assert rule["audience"] in audiences, rule


@pytest.mark.unit
def test_every_core_endpoint_has_frontend_evidence() -> None:
    mod = _load_gate()
    assert mod.run_gate() == 0, "endpoint جوهريّ فقد دليله في الواجهة — راجع مخرجات البوّابة"


@pytest.mark.unit
def test_backend_route_collector_finds_platform_routes() -> None:
    """اكتشاف المسارات يعمل فعلاً (لا بوّابة فارغة تنجح بالصمت)."""
    mod = _load_gate()
    routes = mod.collect_backend_routes()
    assert len(routes) > 300, f"جامع المسارات وجد {len(routes)} فقط — انكسر النمط؟"
    assert any(p.startswith("/api/v1/farm-ledger/") for p in routes)
    assert any(p.startswith("/api/v1/crop-cards") for p in routes)


@pytest.mark.unit
def test_service_token_routes_not_ui_debt() -> None:
    """مسار محميّ بـService Token (مستهلكه آلة) لا يُصنّف دَين واجهة (backlog-ui).

    جوهر «من المستهلك»: القدرات الآليّة (scheduler/worker/خدمة داخليّة) لا تحتاج شاشة
    مستخدم — تصنيفها دَيناً يضخّم قائمة العمل بمطالب واجهة بلا مستهلك بشريّ. مكانها
    operational. هذا يمنع الخلط مصدريّاً.
    """
    mod = _load_gate()
    waived = mod.load_waivers()
    svc = mod.service_token_routes()
    misfiled = [
        ep for ep, w in waived.items() if w.get("reason_category") == "backlog-ui" and ep in svc
    ]
    assert not misfiled, (
        "مسارات service-token (مستهلكها آلة) مُصنّفة دَين واجهة — انقلها إلى operational: "
        + "; ".join(misfiled[:12])
    )


@pytest.mark.unit
def test_every_waiver_declares_intended_consumer() -> None:
    """كلّ إعفاء يعلن مستهلكه المقصود (human/machine/mixed) — لا لبس في الغرض.

    operational/admin-ops ⇒ machine (لا شاشة). backlog-ui ⇒ human أو mixed (يحتاج
    شاشة أو مراجعة). يمنع عودة السؤال «هل هذا للواجهة؟» بلا جواب مُوثَّق.
    """
    mod = _load_gate()
    waived = mod.load_waivers()
    valid = {"human", "machine", "mixed"}
    for ep, w in waived.items():
        assert w.get("intended_consumer") in valid, f"إعفاء بلا مستهلك مُعلَن: {ep}"
        if w.get("reason_category") in {"operational", "admin-ops"}:
            assert w["intended_consumer"] == "machine", (
                f"مسار تشغيليّ يجب أن يكون مستهلكه machine: {ep}"
            )
        if w.get("reason_category") == "backlog-ui":
            # بعد الفرز الكامل: كلّ دَين واجهة مستهلكه human محسوم (لا mixed غير محسوم).
            # mixed مسموح مؤقّتاً لمسارات جديدة قبل فرزها، لكن لا يجب أن يتراكم.
            assert w["intended_consumer"] in {"human", "mixed"}, (
                f"دَين واجهة يجب أن يكون مستهلكه human/mixed: {ep}"
            )


@pytest.mark.unit
def test_phantom_registry_excluded_from_evidence() -> None:
    """سجلّ السرد (backendCoverageRegistry) والتعليقات لا تُحتسب دليل تغطية.

    يمنع «التغطية الوهميّة»: مسار يُعدّ مغطّى لمجرّد وروده في سجلّ توثيق أو تعليق
    بلا شاشة/هوك يستدعيه فعلاً. نتحقّق أنّ نصّ السجلّ الفريد غائب عن corpus الدليل.
    """
    mod = _load_gate()
    corpus = mod.collect_frontend_corpus()
    registry = REPO / "frontend" / "src" / "config" / "backendCoverageRegistry.ts"
    if registry.exists():
        # علامة فريدة للسجلّ (تعريف النوع) — وجودها في corpus يعني تسرّب السجلّ.
        assert "interface BackendCoverageLayer" not in corpus, (
            "سجلّ السرد الزائف تسرّب إلى corpus الدليل — التغطية قد تصبح وهميّة"
        )
        assert "BackendCoverageLayer[]" not in corpus, "تعريف مصفوفة السجلّ تسرّب"


@pytest.mark.unit
def test_comment_only_path_is_not_evidence() -> None:
    """مسار مذكور في تعليق // فقط لا يُعدّ دليلاً (يُزال قبل بناء corpus)."""
    mod = _load_gate()
    corpus = mod.collect_frontend_corpus()
    # نمط تعليق شائع في lib/agroCalculators: '// GET /api/v1/seed/...'
    # المسار قد يظهر في corpus عبر هوك حقيقيّ، لكن سطر التعليق نفسه يجب أن يختفي.
    assert "// GET /api/v1/seed/germination-rate" not in corpus, (
        "سطر تعليق تسرّب إلى corpus الدليل — التعليقات لا تُزال"
    )


@pytest.mark.unit
def test_reverse_gate_no_userfacing_route_escapes_contract() -> None:
    """البوّابة العكسيّة: لا مسار مواجِه للمستخدم بلا (core+دليل) أو إعفاء صريح.

    هذا هو وعد العقد الحقيقيّ — إضافة backend مواجِه جديد بلا hook/شاشة/إعفاء تُفشِل
    CI هنا قبل أن تصبح القدرة يتيمة عن المستخدم.
    """
    mod = _load_gate()
    assert mod.run_reverse_gate() == 0, (
        "مسار مواجِه للمستخدم فلت من العقد — أضِفه إلى core (بدليل) أو إلى "
        "config/endpoint_ui_coverage_waivers.json بسبب صريح."
    )


@pytest.mark.unit
def test_every_waiver_has_explicit_reason() -> None:
    """كلّ إعفاء يحمل سبباً غير فارغ وفئة معروفة — لا إعفاء صامت.

    وطبقة التصنيف الثانية: دَين الواجهة (backlog-ui) يجب أن يحمل priority/ui_effort/
    ui_surface_hint — فالتصنيف قائمة عمل مُرتّبة لا مجرّد وسم «دَين». المسارات
    التشغيليّة (admin-ops/operational) تحمل none (لا شاشة مطلوبة).
    """
    mod = _load_gate()
    waived = mod.load_waivers()
    valid_cats = {"admin-ops", "operational", "backlog-ui"}
    valid_prio = {"high", "medium", "low", "none"}
    valid_effort = {"button", "panel", "page", "none"}
    for ep, w in waived.items():
        assert w.get("reason", "").strip(), f"إعفاء بلا سبب: {ep}"
        assert w.get("reason_category") in valid_cats, f"فئة إعفاء غير معروفة: {ep}"
        # طبقة ثانية إلزاميّة
        assert w.get("priority") in valid_prio, f"أولويّة مفقودة/غير صالحة: {ep}"
        assert w.get("ui_effort") in valid_effort, f"تقدير جهد مفقود/غير صالح: {ep}"
        assert w.get("ui_surface_hint", "").strip(), f"سطح واجهة مقترح مفقود: {ep}"
        if w["reason_category"] == "backlog-ui":
            # طبقة ثانية: أولويّة/جهد فعليّان (لا none).
            assert w["priority"] != "none", f"دَين backlog-ui بلا أولويّة فعليّة: {ep}"
            assert w["ui_effort"] != "none", f"دَين backlog-ui بلا تقدير جهد: {ep}"
            # طبقة ثالثة: تصنيف أهمّية إلزاميّ (حرجيّة وظيفيّة + درجة + شريحة).
            assert w.get("criticality") in {"critical", "decision-support", "informational"}, (
                f"دَين backlog-ui بلا تصنيف حرجيّة: {ep}"
            )
            assert isinstance(w.get("importance"), int) and w["importance"] > 0, (
                f"دَين backlog-ui بلا درجة أهمّية: {ep}"
            )
            assert w.get("importance_tier") in {"P0-حرِج", "P1-عالٍ", "P2-متوسّط", "P3-منخفض"}, (
                f"دَين backlog-ui بشريحة أهمّية غير صالحة: {ep}"
            )
        else:
            assert w["priority"] == "none", f"مسار تشغيليّ بأولويّة واجهة: {ep}"


@pytest.mark.unit
def test_no_stale_waivers() -> None:
    """لا إعفاء لمسار غير موجود أو صار مغطّى — السجلّ يبقى نظيفاً حيّاً."""
    mod = _load_gate()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    corpus = mod.collect_frontend_corpus()
    routes = mod.collect_backend_routes()
    core = {e["endpoint"] for e in cfg["core_endpoints"]}
    live = set(routes)
    stale = []
    for ep in mod.load_waivers():
        if ep not in live:
            stale.append(f"{ep} (غير موجود)")
        elif ep in core and mod.has_frontend_evidence(ep, corpus):
            stale.append(f"{ep} (صار مغطّى)")
    assert not stale, f"إعفاءات بائتة يجب إزالتها: {stale[:10]}"


@pytest.mark.unit
def test_mobile_frontend_root_is_scanned() -> None:
    """جذر Flutter الصحيح (mobile/sahool_app/lib) يُفحَص فعلاً — لا يُخفى بصمت."""
    mod = _load_gate()
    assert any("sahool_app/lib" in r for r in mod.FRONTEND_ROOTS), (
        "جذر الجوّال يجب أن يشير إلى mobile/sahool_app/lib"
    )
    corpus = mod.collect_frontend_corpus()
    # دليل حقيقيّ من تطبيق الجوّال (يُثبِت أنّ الجذر ليس فارغاً).
    assert "/api/v1/fields" in corpus


@pytest.mark.unit
def test_every_discovered_route_is_classified() -> None:
    """توصية تقرير التحقّق: كلّ مسار مُكتشَف (652+) يجب أن يقع في تصنيف صريح —
    core/admin/expert/farmer/manager/internal — لا unclassified يمرّ بصمت.
    غير /api/v1 يقع internal افتراضاً (تحرسه بوّابة عقود الخدمات الـ26)."""
    mod = _load_gate()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    routes = mod.collect_backend_routes()
    unclassified = sorted(
        p for p in routes if mod.classify(p, cfg["classifications"]) == "unclassified"
    )
    assert unclassified == [], f"مسارات بلا تصنيف ({len(unclassified)}): {unclassified[:8]}"
