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
    """كلّ إعفاء يحمل سبباً غير فارغ وفئة معروفة — لا إعفاء صامت."""
    mod = _load_gate()
    waived = mod.load_waivers()
    valid_cats = {"admin-ops", "operational", "backlog-ui"}
    for ep, w in waived.items():
        assert w.get("reason", "").strip(), f"إعفاء بلا سبب: {ep}"
        assert w.get("reason_category") in valid_cats, f"فئة إعفاء غير معروفة: {ep}"


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
