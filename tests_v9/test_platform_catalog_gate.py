"""بوّابة الكتالوج الموحّد (U0+U1+U2) — تثبيت الجرد، الأسماء القانونيّة، والحتميّة.

U0: تثبيت الجرد الحاليّ — 32 مكوّن backend و982 تركيبة Method/Path فريدة، بلا drift.
U1: كلّ مكوّن له اسم قانونيّ واحد؛ erp-bridge قانونيّ وodoo-bridge اسم مستعار؛
    compose/DNS تُربط بالقانونيّ ولا تُعامل كمكوّنات مستقلّة.
U2: المُصرِّف حتميّ — إعادة التوليد تنتج نفس البصمة بايتاً-ببايت (--check).

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


def test_ownership_conflicts_are_only_the_known_finding() -> None:
    """التطبيع القانونيّ يجب أن يُذيب انحراف أسماء الملكيّة كلّه؛ يبقى فقط
    المدخل الزائف الموثَّق (جدول ``IF`` — أثر CREATE TABLE IF NOT EXISTS)."""
    conflicts = json.loads(
        (ROOT / "ownership_conflicts.generated.json").read_text(encoding="utf-8")
    )["conflicts"]
    kinds = sorted(c["kind"] for c in conflicts)
    assert kinds == ["bogus_table_name"], conflicts
    assert conflicts[0]["table"] == "IF"


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
