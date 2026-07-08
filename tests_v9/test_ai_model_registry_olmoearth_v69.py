"""تحقّق V69 — OlmoEarth كنموذج أساس AI (لا مزوّد صور) + عقد embedding صادق.

- OlmoEarth في AI_MODEL_REGISTRY، **لا** في PROVIDER_REGISTRY، **لا** نشط.
- provides_imagery=False + requires (أوزان/سلاسل زمنيّة/تحقّق محلّيّ) + لا يُغني عن مزوّد صور.
- عقد embedding: بلا أوزان/مدخلات ⇒ unavailable بسبب صريح؛ حتّى مع توفّرهما لا متّجه مُختلَق.
- السِجِلّات الأربعة (providers/research/external/ai_models) منفصلة تماماً.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402


def test_olmoearth_is_ai_model_not_imagery_provider():
    o = M.AI_MODEL_REGISTRY["olmoearth"]
    assert o["type"] == "ai_foundation_model"
    assert o["provides_imagery"] is False
    assert o["active_provider"] is False
    # ليس مزوّد صور ولا نشط.
    assert "olmoearth" not in M.PROVIDER_REGISTRY
    assert "olmoearth" not in M.active_providers()


def test_olmoearth_requires_are_honest():
    o = M.AI_MODEL_REGISTRY["olmoearth"]
    assert o["requires_model_weights"] is True
    assert o["requires_satellite_time_series"] is True
    assert o["requires_local_validation_yemen"] is True
    # يعتمد على مزوّدي صور فعليّين (لا يُغني عنهم).
    assert set(o["requires_imagery_provider"]) == {"sentinel1", "sentinel2", "landsat"}


def test_embedding_contract_never_fabricates():
    # بلا أوزان ⇒ غير متاح.
    r1 = M.olmoearth_embedding_contract(has_weights=False, inputs_available=True)
    assert (
        r1["available"] is False and r1["reason"] == "no_model_weights" and r1["embedding"] is None
    )
    # بلا مدخلات ⇒ غير متاح.
    r2 = M.olmoearth_embedding_contract(has_weights=True, inputs_available=False)
    assert r2["available"] is False and r2["reason"] == "no_satellite_time_series"
    # مع توفّرهما ⇒ متاح لكن **لا متّجه مُختلَق** (استدلال خلف GPU + تحقّق محلّيّ).
    r3 = M.olmoearth_embedding_contract(has_weights=True, inputs_available=True)
    assert r3["available"] is True and r3["embedding"] is None
    assert r3["status"] == "ready_pending_local_validation"


def test_olmoearth_runtime_status_diagnoses_missing_weights():
    # جهاز بلا أوزان (مسار غير موجود) ⇒ weights_missing + المسار المتوقّع (صادق قابل للتنفيذ).
    r = M.olmoearth_runtime_status("/no/such/olmoearth.pt")
    assert r["ready"] is False
    assert r["reason_code"] == "weights_missing"
    assert r["checkpoint_expected"] == "/no/such/olmoearth.pt"


def test_olmoearth_runtime_never_ready_without_local_validation():
    # صدق: حتّى مع أوزان+GPU لا يصير ready تلقائيّاً — يبقى ready_pending_validation
    # (تفعيل بشريّ بعد benchmark يمنيّ). نختبر أنّ الدالّة لا تُرجِع ready=True أبداً هنا.
    r = M.olmoearth_runtime_status("/no/such/olmoearth.pt")
    assert r["ready"] is False
    # القيم المسموحة لرمز السبب.
    assert r["reason_code"] in {
        "weights_missing",
        "cuda_unavailable",
        "library_missing",
        "ready_pending_validation",
    }


def test_all_four_registries_disjoint():
    providers = set(M.PROVIDER_REGISTRY)
    research = set(M.RESEARCH_REGISTRY)
    external = set(M.EXTERNAL_SOURCE_REGISTRY)
    ai = set(M.AI_MODEL_REGISTRY)
    regs = [providers, research, external, ai]
    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            assert regs[i].isdisjoint(regs[j]), "السِجِلّات يجب أن تكون منفصلة"


def test_status_endpoint_exposes_ai_models():
    src = (_RASTER / "routers" / "observability.py").read_text(encoding="utf-8")
    assert "AI_MODEL_REGISTRY" in src, "نقطة الحالة تكشف نماذج الذكاء الاصطناعيّ"
