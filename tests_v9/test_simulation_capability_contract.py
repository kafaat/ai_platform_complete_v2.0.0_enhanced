"""حارس عقد قدرة المحاكاة + سجلّ المحاصيل + فصل I/O (SIM-PCSE-01) + برهان سلبيّ.

يفرض معيار ``capability-contract-standard`` (A5): ``supported:true`` بلا ``limits`` ⇒ يُرفَض. + شروط المالك:
لا ملوحة في PCSE (منع ازدواج المحرّكين) · الإنتاج المحتمل غير معروض (WLP) · المحاصيل بالاسم بمصدر معاملات ·
المعايرة uncalibrated حتى golden · الراية default-off. فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_SVC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "agriai-engine"))
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

import sim_crop_registry  # noqa: E402
import simulation_capability as sc  # noqa: E402
import simulation_io as sio  # noqa: E402


def test_contract_declares_limits_status_and_refs():
    cap = sc.SIMULATION_CAPABILITY
    assert cap.supported is True
    assert cap.limits and cap.status_enum and cap.references  # إلزاميّة (منع fail-open)
    assert all(c.ref.strip() for c in cap.covers)  # كلّ ادّعاء بمرجع
    assert cap.calibration_status == "uncalibrated_pending_golden"
    assert cap.flag == "SIM_PCSE_ENABLED"


def test_negative_capability_without_limits_is_rejected():
    """برهان سلبيّ (نظير A5): عقد supported=true بلا حدود = fail-open مقنّع — يُرفَض بنيويّاً."""

    def _validate(cap: sc.SimulationCapability) -> None:
        if cap.supported and not (cap.limits and cap.status_enum and cap.references):
            raise ValueError("capability supported without declared limits (masked fail-open)")

    bad = sc.SimulationCapability(
        supported=True,
        model="x",
        references=(),
        covers=(),
        limits=(),
        status_enum=(),
        supported_crops=(),
        calibration_status="",
        flag="",
    )
    with pytest.raises(ValueError):
        _validate(bad)
    _validate(sc.SIMULATION_CAPABILITY)  # الحقيقيّ يمرّ


def test_no_double_engine_no_salinity_in_pcse_contract():
    """شرط المالك: لا التقاء محرّكين — العقد يُعلن أنّ PCSE لا يُنمذج الملوحة (تبقى fao56/غسيل A5)."""
    limits_blob = " ".join(sc.SIMULATION_CAPABILITY.limits)
    assert "ملوحة" in limits_blob and "fao56" in limits_blob


def test_wlp_only_potential_not_exposed_documented():
    """شرط المالك: قيد WLP يوثّق صراحةً أنّ الإنتاج المحتمل (potential) غير معروض."""
    limits_blob = " ".join(sc.SIMULATION_CAPABILITY.limits)
    assert "WLP" in limits_blob and ("potential" in limits_blob or "المحتمل" in limits_blob)


def test_supported_crops_v1_by_name_with_parameter_source():
    assert sc.SIMULATION_CAPABILITY.supported_crops == ("barley", "potato", "wheat")
    assert sim_crop_registry.is_supported("wheat") and sim_crop_registry.is_supported("Potato")
    assert not sim_crop_registry.is_supported("sorghum")  # محصول يمنيّ حسّاس — خارج v1 عمداً
    assert not sim_crop_registry.is_supported("tomato") and not sim_crop_registry.is_supported(
        "onion"
    )
    # كلّ محصول مدعوم يحمل مصدر معاملاته + نسخته (لا اختلاق).
    for name in sc.SIMULATION_CAPABILITY.supported_crops:
        crop = sim_crop_registry.get(name)
        assert crop is not None and crop.parameter_source and crop.parameter_version


def test_io_separation_roundtrip_pure():
    """فصل I/O: SimulationInputs/Output عقد مُهيكَل نقيّ (يُقاس عليه golden) بلا استيراد FastAPI/pcse."""
    inp = sio.SimulationInputs.from_dicts({"crop": "Wheat"}, {"daily": []}, {}, {})
    assert inp.crop_name == "wheat"
    out = sio.SimulationOutput(
        yield_kg_ha=100.0,
        biomass=200.0,
        water_use=50.0,
        stages=[],
        provenance="pcse_wofost_uncalibrated",
    )
    assert sio.SimulationOutput.from_dict(out.to_dict()) == out
    src = open(os.path.join(_SVC, "simulation_io.py"), encoding="utf-8").read()
    assert "import fastapi" not in src and "from fastapi" not in src and "import pcse" not in src
