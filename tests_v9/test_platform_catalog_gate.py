"""بوّابة الكتالوج الموحّد (U0+U1+U2) — تثبيت الجرد، الأسماء القانونيّة، والحتميّة.

U0: تثبيت الجرد الحاليّ — 32 مكوّن backend و982 تركيبة Method/Path فريدة، بلا drift.
U1: كلّ مكوّن له اسم قانونيّ واحد؛ erp-bridge قانونيّ وodoo-bridge اسم مستعار؛
    compose/DNS تُربط بالقانونيّ ولا تُعامل كمكوّنات مستقلّة.
U2: المُصرِّف حتميّ — إعادة التوليد تنتج نفس البصمة بايتاً-ببايت (--check).
U3: wired مدفوع بأدلّة fail-closed (بوّابة العقود المُقوّاة): 29 مستهلَكاً مثبتاً،
    agriai-engine غير-مستهلَك عمداً (بمُحفِّز إعادة فتح)، qdrant-seed وgis-workflow-service
    مهمّتان مستقلّتان؛ سجلّ ملكيّة الجداول نظيف (مدخل IF الزائف أُزيل من مصدره).
U4: كلّ مجموعة تكرار (method,path) مقاسة تحمل قراراً بشريّاً صالحاً (تصنيف + سبب +
    انتهاء للمؤقّت)، وكلّ إعفاء واجهة محكوم بمالك/انتهاء/تتبّع؛ فحص الانتهاء الزمنيّ
    في --enforce-expiry فقط فلا يلوّث حتميّة المخرجات.

الصدق: قدرات U2 مشتقّة آليّاً (curated=false) ولا تحمل دلالات حَوكميّة مُختلَقة
(approval/idempotency/سياق تبقى null حتى تُعلَن صراحةً في U5).
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
COMPILER = ROOT / "scripts" / "architecture" / "build_platform_catalog.py"
CATALOG = ROOT / "platform_catalog.generated.json"

# U0 — الأرقام المُثبَّتة (تغييرها المتعمَّد = قرار معماريّ يُحدَّث هنا بوعي)
PINNED_BACKEND_COMPONENTS = 32
PINNED_UNIQUE_METHOD_PATH = 982


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_u0_inventory_pinned() -> None:
    counts = _catalog()["counts"]
    assert counts["backend_components"] == PINNED_BACKEND_COMPONENTS
    assert counts["unique_method_path"] == PINNED_UNIQUE_METHOD_PATH
    # frontend + mobile مكوّنا كتالوج من الطراز الأوّل
    assert counts["components"] == PINNED_BACKEND_COMPONENTS + 2


def test_u2_compiler_is_deterministic_and_no_drift() -> None:
    """--check يعيد البناء ويقارن بايتاً-ببايت — drift أو لا-حتميّة ⇒ فشل."""
    proc = subprocess.run(
        [sys.executable, str(COMPILER), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, (
        f"platform-catalog drift/non-determinism:\n{proc.stdout}{proc.stderr}"
    )


def test_u1_erp_bridge_canonical_and_alias() -> None:
    cat = _catalog()
    comps = {c["component_id"]: c for c in cat["components"]}
    assert "erp-bridge" in comps, "erp-bridge هو الاسم القانونيّ"
    assert "odoo-bridge" not in comps, "odoo-bridge اسم مستعار — لا يظهر كمكوّن مستقلّ"
    aliases = set(comps["erp-bridge"]["aliases"])
    assert "odoo-bridge" in aliases
    # صفّا الجرد وcompose كلاهما انصهرا في القانونيّ
    assert comps["erp-bridge"]["sources"]["service_inventory"] == "odoo-bridge"
    assert any(a.startswith("sahool-") for a in aliases)


def test_u1_no_component_split_identity() -> None:
    """لا مكوّن يظهر مرّتين بهويّتين (اسم compose واسم جرد)."""
    cat = _catalog()
    ids = [c["component_id"] for c in cat["components"]]
    assert len(ids) == len(set(ids))
    # لا component_id يبدأ بـsahool- (بادئة compose عرضٌ لا هويّة) — عدا الاسم
    # الحقيقيّ الوحيد sahool-platform.
    offenders = [i for i in ids if i.startswith("sahool-") and i != "sahool-platform"]
    assert not offenders, offenders


def test_ownership_conflicts_are_zero() -> None:
    """U3: التطبيع القانونيّ أذاب انحراف الأسماء، والمدخل الزائف (جدول ``IF`` —
    أثر CREATE TABLE IF NOT EXISTS) أُزيل من مصدره db_ownership.yml — السجلّ نظيف،
    وأيّ تعارض جديد يُفشِل بوّابة الحَوكمة U3 في المُصرِّف نفسه."""
    conflicts = json.loads(
        (ROOT / "ownership_conflicts.generated.json").read_text(encoding="utf-8")
    )["conflicts"]
    assert conflicts == [], conflicts
    ownership = (ROOT / "docs" / "architecture" / "db_ownership.yml").read_text(encoding="utf-8")
    assert "\n  IF:\n" not in ownership


def test_u3_wired_is_evidence_driven() -> None:
    """U3: السلك من أدلّة بوّابة العقود المُقوّاة لا من تخمينات compose —
    29 مستهلَكاً مثبتاً؛ agriai-engine غير-مستهلَك عمداً (False + مُحفِّز إعادة فتح)؛
    qdrant-seed وgis-workflow-service مهمّتان مستقلّتان (null)."""
    comps = {c["component_id"]: c for c in _catalog()["components"]}
    agriai = comps["agriai-engine"]
    assert agriai["status"]["wired"] is False
    assert agriai["consumer_contract"]["wiring_disposition"] == "intentional-unconsumed"
    assert agriai["consumer_contract"]["reopen_trigger"], "غير-مستهلَك عمداً بلا مُحفِّز = إخفاء"
    for job in ("qdrant-seed", "gis-workflow-service"):
        assert comps[job]["status"]["wired"] is None
        assert comps[job]["consumer_contract"]["wiring_disposition"] == "standalone-job"
    backend_wired = [
        c["component_id"]
        for c in comps.values()
        if c["status"]["wired"] is True and c["consumer_contract"]["declared"]
    ]
    assert len(backend_wired) == 29, sorted(backend_wired)
    # كلّ مكوّن backend مصرَّح عقده وأدلّته صالحة (fail-closed مرّت)
    for c in comps.values():
        if c["consumer_contract"]["declared"]:
            assert c["consumer_contract"]["evidence_valid"] is True, c["component_id"]


def test_u4_all_duplicate_groups_carry_valid_decisions() -> None:
    """U4: كلّ مجموعة تكرار مقاسة مصنَّفة بقرار له سبب؛ المؤقّت يحمل انتهاءً؛
    الواجهات القديمة تسمّي مالكاً قانونيّاً وواجهةً مختلفَين وكلاهما عضو المجموعة."""
    cat = _catalog()
    groups = cat["cross_service_duplicate_method_paths"]
    assert cat["counts"]["duplicate_groups_classified"] == len(groups) == 14
    for g in groups:
        assert g["classified"] is True, g
        assert g["classification"], g
        assert str(g["decision"]).strip(), g
        if g["classification"] == "legacy_bff_facade":
            assert g["canonical_owner"] and g["facade"], g
            assert g["canonical_owner"] != g["facade"], g
            assert g["canonical_owner"] in g["components"], g
            assert g["facade"] in g["components"], g
    facades = {
        (g["method"], g["path"]): g["canonical_owner"]
        for g in groups
        if g["classification"] == "legacy_bff_facade"
    }
    # فصل الحقيقة عن الواجهة: raster يملك STAC وagriai يملك التخطيط — المنصّة واجهة فقط.
    assert facades[("GET", "/stac")] == "raster-service"
    assert facades[("POST", "/plan")] == "agriai-engine"


def test_u4_ui_waivers_governed() -> None:
    """U4: الإعفاءات الخمسون كلّها محكومة — مالك (مكوّن كتالوج فعليّ) + انتهاء صالح
    + تتبّع؛ ومالك إعفاءات break-glass مُشتقّ من مصدر مساره لا من الافتراض الأعمى."""
    cat = _catalog()
    waivers = cat["ui_waiver_governance"]
    assert len(waivers) == cat["counts"]["ui_waivers"] == 50
    component_ids = {c["component_id"] for c in cat["components"]}
    from datetime import date

    for w in waivers:
        assert w["owner"] in component_ids, w
        date.fromisoformat(w["expires_on"])
        assert w["tracking"], w


def test_capabilities_do_not_invent_governance_semantics() -> None:
    caps = _catalog()["capabilities"]
    assert caps, "قدرات مشتقّة موجودة"
    for cap in caps:
        assert cap["curated"] is False
        assert cap["approval_required"] is None
        assert cap["idempotency_required"] is None
        assert cap["required_context"] is None


def test_overrides_contain_only_non_discoverable_facts() -> None:
    """ملفّ overrides لا يحمل معلومات قابلة للاكتشاف الآليّ (منافذ/مسارات/جداول)."""
    text = (ROOT / "config" / "platform_catalog_overrides.yml").read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("port:", "health:", "tables:", "/api/", "proxy_pass", "compose_service:"):
        assert forbidden not in body, f"معلومة قابلة للاكتشاف في overrides: {forbidden}"


def test_manifest_never_claims_live_activation() -> None:
    manifest = json.loads(
        (ROOT / "runtime_capability_manifest.generated.json").read_text(encoding="utf-8")
    )
    for comp in manifest["components"]:
        assert comp["status"]["configured"] is None
        assert comp["status"]["activated"] is None


def test_compiler_importable_pure() -> None:
    spec = importlib.util.spec_from_file_location("platform_catalog_compiler", COMPILER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.build)
