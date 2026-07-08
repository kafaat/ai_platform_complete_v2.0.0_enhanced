"""تحقّق — محوّلا WaPOR v3 / WorldCereal (docs-based، صادق: بلا تخمين، active=false).

- parse_wapor_mapsets يقرأ الشكل الموثّق (code+caption) envelope-agnostic؛ mismatch ⇒ None.
- كلاهما active=false + live_verified=false؛ WorldCereal schema_verified_from_docs=false (لم تُتحقَّق).
- لا اعتمادات/أسرار في الجاهزيّة؛ activation_blockers صريحة.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402
import wapor_worldcereal as W  # noqa: E402


def test_parse_wapor_mapsets_documented_fields_envelope_agnostic():
    # الشكل الموثّق: عناصر تحمل code+caption. نتحمّل غلافين مختلفين (غير مفترَض).
    wrapped = {
        "response": {"items": [{"code": "L2-AETI-D", "caption": "Actual ET & Interception"}]}
    }
    bare = [{"code": "L2-NPP-D", "caption": "Net Primary Production"}]
    r1 = W.parse_wapor_mapsets(wrapped)
    r2 = W.parse_wapor_mapsets(bare)
    assert r1 == [{"code": "L2-AETI-D", "caption": "Actual ET & Interception"}]
    assert r2 == [{"code": "L2-NPP-D", "caption": "Net Primary Production"}]


def test_parse_wapor_mapsets_none_on_mismatch():
    # صدق: بلا عناصر تحمل الحقلَين الموثّقَين ⇒ None (لا تلفيق، لا افتراض غلاف).
    assert W.parse_wapor_mapsets({"foo": "bar"}) is None
    assert W.parse_wapor_mapsets(None) is None
    assert W.parse_wapor_mapsets([{"code": 123}]) is None  # code ليس نصّاً / لا caption


def test_wapor_readiness_honest_flags():
    r = W.wapor_readiness()
    assert r["active"] is False and r["live_verified"] is False
    assert r["schema_verified_from_docs"] is True  # endpoint+code/caption موثّقان
    assert "water_productivity" in r["provides"]
    assert r["reason_code"] == "live_not_verified"
    assert any("fixture" in b for b in r["activation_blockers"])
    # لا اعتمادات مخزّنة.
    import json

    assert "token" not in json.dumps(r).lower() and "password" not in json.dumps(r).lower()


def test_worldcereal_readiness_does_not_overclaim_schema():
    r = W.worldcereal_readiness()
    assert r["active"] is False and r["live_verified"] is False
    # صدق: لم تُتحقَّق الواجهة ⇒ لا نكتب parser ولا ندّعي docs verification.
    assert r["schema_verified_from_docs"] is False
    assert not hasattr(W, "parse_worldcereal")  # لا parser بلا مخطّط مُتحقَّق


def test_registry_entries_carry_honest_verification_flags():
    for k in ("wapor", "worldcereal"):
        e = M.PROVIDER_REGISTRY[k]
        assert e["active"] is False and e["live_verified"] is False
        assert "activation_blockers" in e and e["provides"]
    assert M.PROVIDER_REGISTRY["wapor"]["schema_verified_from_docs"] is True
    assert M.PROVIDER_REGISTRY["worldcereal"]["schema_verified_from_docs"] is False
