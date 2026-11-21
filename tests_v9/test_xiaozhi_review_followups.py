"""Follow-ups from the independent review of the Xiaozhi package.

1. Critical-speech detection is linear. `validation_text` raised the gated length from
   1000 to 8000 characters; the old number pattern backtracked quadratically on a long
   digit/space run with no unit (1.4-1.7 s per request, blocking the TTS event loop).
   The linear helpers must give exactly the old answers.
2. A malformed MQTT broker URL is a failed send, not an exception: the parse sits inside
   the try of `send_mqtt_command`, so the caller still writes the failure record. The two
   listeners parse it inside a try too, so a bad URL is logged instead of killing the task.
"""

from __future__ import annotations

import ast
import importlib.util
import re
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


@pytest.mark.parametrize(
    "function_name", ["send_mqtt_command", "mqtt_ack_listener", "mqtt_sensor_listener"]
)
def test_broker_url_parse_is_inside_a_try(function_name):
    source = (ROOT / "services" / "actuator-service" / "actuator_runtime.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    send = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name
    )
    parses = [
        node
        for node in ast.walk(send)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_parse_mqtt_broker_url"
    ]
    assert parses, f"{function_name} no longer parses the broker URL"
    guarded = {
        id(inner)
        for node in ast.walk(send)
        if isinstance(node, ast.Try) and node.handlers
        for statement in node.body
        for inner in ast.walk(statement)
    }
    assert all(id(call) in guarded for call in parses)


# Debian's base-passwd ships these groups and users in every python:*-slim image
# (/usr/share/base-passwd/{group,passwd}.master). `groupadd voice` therefore exits 9
# and the image never builds, which is what broke the Xiaozhi gateway image.
_DEBIAN_BASE_NAMES = frozenset(
    "root daemon bin sys adm tty disk lp mail news uucp man proxy kmem dialout fax "
    "voice cdrom floppy tape sudo audio dip www-data backup operator list irc src "
    "gnats shadow utmp video sasl plugdev staff games users nogroup nobody sync "
    "_apt".split()
)
_ACCOUNT_CMD = re.compile(r"\b(groupadd|useradd|addgroup|adduser)\b([^&;|\n]*)")


def _debian_dockerfiles():
    for path in sorted(ROOT.rglob("Dockerfile*")):
        if "node_modules" in path.parts or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        froms = re.findall(r"(?im)^FROM\s+(\S+)", text)
        if any(re.match(r"python:[\w.]+-slim", image) for image in froms):
            yield path, text.replace("\\\n", " ")


def test_dockerfile_accounts_do_not_reuse_debian_base_names():
    offenders = []
    for path, text in _debian_dockerfiles():
        for command, args in _ACCOUNT_CMD.findall(text):
            tokens = args.split()
            if "-f" in tokens or "--force" in tokens:
                continue  # an explicit "reuse if present" is a deliberate choice
            positional = [t for t in tokens if not t.startswith("-") and not t.isdigit()]
            # Option values (gid/uid/group/shell/home) precede the account name.
            name = positional[-1] if positional else ""
            if name in _DEBIAN_BASE_NAMES:
                offenders.append(f"{path.relative_to(ROOT)}: {command} {name}")
    assert not offenders, offenders


def test_the_base_name_check_catches_the_original_voice_group():
    text = (
        "RUN groupadd --gid 10001 voice && useradd --uid 10001 --gid voice --no-create-home voice"
    )
    hits = [args.split()[-1] for _, args in _ACCOUNT_CMD.findall(text)]
    assert "voice" in hits and set(hits) & _DEBIAN_BASE_NAMES
