"""Follow-ups from the independent review of the Xiaozhi package.

1. Critical-speech detection is linear. `validation_text` raised the gated length from
   1000 to 8000 characters; the old number pattern backtracked quadratically on a long
   digit/space run with no unit (1.4-1.7 s per request, blocking the TTS event loop).
   The linear helpers must give exactly the old answers.
2. A malformed MQTT broker URL is a failed send, not an exception: the parse sits inside
   the try of `send_mqtt_command`, so the caller still writes the failure record.
"""

from __future__ import annotations

import ast
import importlib.util
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
# Loaded by file path, not via sys.path: tts-service's `main`/`routers` must not shadow
# other services' modules in the shared unit run.
_SPEC = importlib.util.spec_from_file_location(
    "xiaozhi_followup_critical_speech", ROOT / "services" / "tts-service" / "critical_speech.py"
)
cs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cs)

_CASES = [
    "اسقِ 5 مل لكل لتر",
    "5ml",
    "5 lbs",
    "1, 2 / 3 kg",
    "٣ لتر",
    "۵ g",
    "x 10 liters y",
    "10 litersx",
    "no numbers here",
    "جرعة",
    "جرعة ثم 5",
    "PHI 7 days",
    "phi7",
    "dose: see label",
    "فترة ما قبل الحصاد 14",
    "5 \n\t ملعقة",
    "1 " * 50 + "x",
]


@pytest.mark.parametrize("text", _CASES)
def test_linear_detection_answers_exactly_as_the_original_patterns(text):
    assert cs._has_critical_number(text) is bool(cs._CRITICAL_NUMBER.search(text))
    assert cs._has_dose_label_number(text) is bool(cs._DOSE_LABEL_NUMBER.search(text))


@pytest.mark.parametrize(
    "validation_text",
    ["1 " * 3999 + "x", "5 ،" * 2666, "جرعة " * 1599],
    ids=["digit-space-run", "digit-comma-run", "labels-without-digit"],
)
def test_full_context_gate_stays_linear_on_adversarial_text(validation_text):
    started = time.perf_counter()
    try:
        cs.prepare_critical_speech("x", validation_text=validation_text)
    except cs.CriticalSpeechError:
        pass
    # The quadratic pattern took about 1.4 s here; linear is a few milliseconds.
    assert time.perf_counter() - started < 0.3


def test_a_dose_split_across_chunks_is_still_refused():
    full = "الجرعة الموصى بها 5 مل لكل لتر"
    with pytest.raises(cs.CriticalSpeechError):
        cs.prepare_critical_speech("الجرعة الموصى بها", validation_text=full)


def test_broker_url_parse_is_inside_the_send_try():
    source = (ROOT / "services" / "actuator-service" / "actuator_runtime.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    send = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_mqtt_command"
    )
    parses = [
        node
        for node in ast.walk(send)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_parse_mqtt_broker_url"
    ]
    assert parses, "send_mqtt_command no longer parses the broker URL"
    guarded = {
        id(inner)
        for node in ast.walk(send)
        if isinstance(node, ast.Try) and node.handlers
        for statement in node.body
        for inner in ast.walk(statement)
    }
    assert all(id(call) in guarded for call in parses)
