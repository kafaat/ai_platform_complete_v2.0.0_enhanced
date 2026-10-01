"""``TTSRequest.pitch`` يُتحقَّق منه كأخويه rate/volume — 422 لا 500.

**العطل:** كان ``pitch`` الحقلَ الوحيدَ بلا ``field_validator``، فقيمةٌ مثل ``"+abc"`` تبلغ
``edge_tts.Communicate`` فيرفضها ``TTSConfig`` (``^[+-]\\d+Hz$`` ⇒ ``ValueError``) داخل
مسار التركيب، ويعود المستخدمُ بـ500 «فشل التركيب» بدل 422 يقول ما الخطأ.

والصيغةُ المقبولة هي صيغةُ edge-tts نفسِها — فلا يُرفَض ما كانت المكتبةُ تقبله.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from functools import cache
from pathlib import Path

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit
pytest.importorskip("fastapi")

_ROOT = Path(__file__).resolve().parents[1]
_SVC = _ROOT / "services" / "tts-service"


@cache
def _request_model():
    """يُحمَّل ``main.py`` كما تحمّله شواهدُ الخدمة الأخرى: ``edge_tts`` مُرقَّعٌ إن غاب.

    النموذجُ لا يلمس ``edge_tts`` — الرقعةُ لإتمام الاستيراد وحدَه في طبقة الوحدات.
    """
    if "edge_tts" not in sys.modules:
        stub = types.ModuleType("edge_tts")
        stub.Communicate = object
        sys.modules["edge_tts"] = stub
    for path in (str(_ROOT), str(_SVC)):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location("sahool_tts_main_pitch", _SVC / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["sahool_tts_main_pitch"] = module
    spec.loader.exec_module(module)
    return module.TTSRequest


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "y" * 48)


@pytest.mark.parametrize("pitch", ["+0Hz", "-5Hz", "+12Hz"])
def test_pitch_in_edge_tts_format_is_accepted(pitch: str) -> None:
    assert _request_model()(text="مرحبا", pitch=pitch).pitch == pitch


@pytest.mark.parametrize("pitch", ["+abc", "5Hz", "+5", "+5hz", "", "+5Hz; drop"])
def test_malformed_pitch_is_rejected_before_synthesis(pitch: str) -> None:
    with pytest.raises(ValidationError, match="pitch"):
        _request_model()(text="مرحبا", pitch=pitch)
