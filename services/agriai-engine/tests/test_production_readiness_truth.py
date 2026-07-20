"""AgriAI production readiness truth: readyz + docs match the fail-closed behavior.

Deep-audit finding: ``pcse`` importable is necessary but NOT sufficient for real WOFOST —
the provider builders need integration completion. So production readiness must require an
explicitly-verified scientific path (SIM_PCSE_INTEGRATION_VERIFIED), never a mere import.
"""

import os
import sys
from pathlib import Path

_SERVICE_DIR = str(Path(__file__).resolve().parents[1])
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)

import wofost_adapter as wa  # noqa: E402


def test_readyz_requires_verified_scientific_path_in_production():
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "AGRIAI_PRODUCTION_MODE" in src
    # الجاهزيّة الإنتاجيّة تُبنى على حالة المسار العلميّ الصادقة، لا على توفّر المكتبة.
    assert "scientific_path_status" in src
    assert "scientific_ready" in src
    assert "verified_missing" in src


def test_wofost_docs_match_fail_closed_behavior():
    src = (Path(__file__).resolve().parents[1] / "wofost_adapter.py").read_text()
    assert "فشل مُغلَق" in src
    assert "لا ننهار أبداً" not in src
    assert "agriai_production_simulation_unavailable" in src


def test_scientific_ready_requires_all_three_conditions(monkeypatch):
    """pcse متاح وحده لا يكفي: يلزم التمكين + إثبات التكامل معاً."""
    # حتى لو كانت المكتبة متاحة، بلا راية التكامل ⇒ ليس جاهزاً علميّاً.
    monkeypatch.setattr(wa, "_PCSE_AVAILABLE", True, raising=False)
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1")
    monkeypatch.delenv("SIM_PCSE_INTEGRATION_VERIFIED", raising=False)
    st = wa.scientific_path_status()
    assert st["pcse_importable"] is True
    assert st["pcse_enabled"] is True
    assert st["integration_verified"] is False
    assert st["scientific_ready"] is False

    # بإثبات التكامل صراحةً ⇒ جاهز علميّاً.
    monkeypatch.setenv("SIM_PCSE_INTEGRATION_VERIFIED", "1")
    assert wa.scientific_path_status()["scientific_ready"] is True


def test_scientific_ready_false_when_pcse_missing(monkeypatch):
    monkeypatch.setattr(wa, "_PCSE_AVAILABLE", False, raising=False)
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1")
    monkeypatch.setenv("SIM_PCSE_INTEGRATION_VERIFIED", "1")
    assert wa.scientific_path_status()["scientific_ready"] is False


# تنظيف بيئة الاختبار من الرايات المحقونة (احتياط عبر العمليّات).
def teardown_module(_module):
    for k in ("SIM_PCSE_ENABLED", "SIM_PCSE_INTEGRATION_VERIFIED"):
        os.environ.pop(k, None)
