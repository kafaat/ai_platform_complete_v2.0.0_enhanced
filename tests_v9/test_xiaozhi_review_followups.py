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
import shlex
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


# Debian's base-passwd ships these groups and users in every Debian-family image
# (/usr/share/base-passwd/{group,passwd}.master). `groupadd voice` therefore exits 9
# and the image never builds, which is what broke the Xiaozhi gateway image.
_DEBIAN_BASE_NAMES = frozenset(
    "root daemon bin sys adm tty disk lp mail news uucp man proxy kmem dialout fax "
    "voice cdrom floppy tape sudo audio dip www-data backup operator list irc src "
    "gnats shadow utmp video sasl plugdev staff games users nogroup nobody sync "
    "_apt".split()
)
_DEBIAN_FAMILY_IMAGE = re.compile(r"^(?:docker\.io/)?(?:library/)?(python|debian|ubuntu)[:@]")
_ACCOUNT_COMMANDS = frozenset({"groupadd", "useradd", "addgroup", "adduser"})
# Options whose value is the next token (shadow-utils and Debian adduser).
_OPTIONS_WITH_VALUE = frozenset(
    "-b --base-dir -c --comment -d --home-dir -e --expiredate -f --inactive -g --gid "
    "-G --groups -k --skel -K --key -p --password -R --root -P --prefix -s --shell "
    "-u --uid -Z --selinux-user --home --ingroup --gecos --firstuid --lastuid "
    "--firstgid --lastgid --conf".split()
)
_FORCE = frozenset({"-f", "--force"})


def _instructions(text):
    """Dockerfile instructions with continuations joined and comment lines dropped."""
    joined, pending = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if pending and line.startswith("#"):
            continue  # a comment line inside a continued instruction
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        joined.append(pending + line)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def _resolve(image, args):
    def sub(match):
        return args.get(match.group(1) or match.group(2), match.group(0))

    return re.sub(r"\$\{(\w+)(?::?-[^}]*)?\}|\$(\w+)", sub, image)


def _debian_run_commands(text):
    """RUN bodies of every stage whose base is Debian-family.

    ARG defaults are resolved in FROM, and a stage built FROM an earlier stage's alias
    inherits that stage's classification (`FROM python:3.12-slim AS base` then `FROM base`).
    """
    args, stages, debian_stage = {}, {}, False
    for instruction in _instructions(text):
        keyword, _, rest = instruction.partition(" ")
        keyword = keyword.upper()
        if keyword == "ARG":
            name, _, default = rest.strip().partition("=")
            if default:
                args.setdefault(name.strip(), default.strip().strip("\"'"))
        elif keyword == "FROM":
            tokens = [t for t in rest.split() if not t.startswith("--")]
            image = _resolve(tokens[0], args) if tokens else ""
            if image.lower() in stages:
                debian_stage = stages[image.lower()]
            else:
                debian_stage = bool(_DEBIAN_FAMILY_IMAGE.match(image)) and "alpine" not in image
            if len(tokens) >= 3 and tokens[1].upper() == "AS":
                stages[tokens[2].lower()] = debian_stage
        elif keyword == "RUN" and debian_stage:
            yield rest


_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})


def _shell_segments(run_body):
    """Split a RUN body into simple commands with shell quoting respected.

    `--gecos "Voice service"` stays one token, so a quoted option value is never
    mistaken for a positional name. An unparsable body falls back to whitespace.
    """
    lexer = shlex.shlex(run_body, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = run_body.split()
    segment = []
    for token in tokens:
        if token in _SEPARATORS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _created_account_names(run_body):
    """Names that groupadd/useradd/addgroup/adduser would create in a RUN body."""
    names = []
    for tokens in _shell_segments(run_body):
        while tokens and tokens[0] in {"sudo", "exec", "command"}:
            tokens = tokens[1:]
        if not tokens or tokens[0].rsplit("/", 1)[-1] not in _ACCOUNT_COMMANDS:
            continue
        command, positional, forced, skip = tokens[0].rsplit("/", 1)[-1], [], False, False
        for token in tokens[1:]:
            if skip:
                skip = False
                continue
            if token in _FORCE:
                forced = True
            elif token in _OPTIONS_WITH_VALUE:
                skip = True
            elif not token.startswith("-"):
                positional.append(token)
        if forced or not positional:
            continue  # an explicit "reuse if present" is a deliberate choice
        if command in {"adduser", "addgroup"} and len(positional) == 2:
            continue  # `adduser USER GROUP` adds an existing user to an existing group
        names.append((command, positional[-1]))
    return names


def _debian_dockerfiles():
    for path in sorted(ROOT.rglob("Dockerfile*")):
        if "node_modules" in path.parts or not path.is_file():
            continue
        yield path, path.read_text(encoding="utf-8", errors="replace")


def test_dockerfile_accounts_do_not_reuse_debian_base_names():
    offenders = []
    for path, text in _debian_dockerfiles():
        for body in _debian_run_commands(text):
            for command, name in _created_account_names(body):
                if name in _DEBIAN_BASE_NAMES:
                    offenders.append(f"{path.relative_to(ROOT)}: {command} {name}")
    assert not offenders, offenders


@pytest.mark.parametrize(
    "dockerfile, expected",
    [
        (
            "FROM python:3.12-slim-bookworm\n"
            "RUN groupadd --gid 10001 voice \\\n"
            "    && useradd --uid 10001 --gid voice --no-create-home voice\n",
            [("groupadd", "voice"), ("useradd", "voice")],
        ),
        (
            "ARG BASE=python:3.12-slim-bookworm\nFROM ${BASE}\nRUN groupadd audio\n",
            [("groupadd", "audio")],
        ),
        (
            "FROM --platform=linux/amd64 debian:bookworm\nRUN useradd -m video\n",
            [("useradd", "video")],
        ),
        ("FROM ubuntu:24.04 AS build\nRUN addgroup --system staff\n", [("addgroup", "staff")]),
        ("FROM python:3.12-slim\n# RUN groupadd voice\nRUN groupadd app\n", [("groupadd", "app")]),
        ("FROM python:3.12-slim\nRUN adduser app audio\n", []),
        ("FROM python:3.12-slim\nRUN groupadd -f voice\n", []),
        ("FROM python:3.12-alpine\nRUN addgroup voice\n", []),
        (
            "FROM node:20-bookworm AS ui\nRUN groupadd voice\nFROM python:3.12-slim\nRUN groupadd app\n",
            [("groupadd", "app")],
        ),
        (
            "FROM python:3.12-slim AS base\nFROM base AS runtime\nRUN groupadd voice\n",
            [("groupadd", "voice")],
        ),
        (
            'FROM python:3.12-slim\nRUN adduser --gecos "Voice service" --disabled-password voice\n',
            [("adduser", "voice")],
        ),
        (
            "FROM python:3.12-slim\nRUN echo 'a; groupadd voice' && groupadd app\n",
            [("groupadd", "app")],
        ),
    ],
    ids=[
        "original-voice-defect",
        "arg-default-base",
        "platform-flag-debian",
        "ubuntu-addgroup",
        "comment-ignored",
        "adduser-membership",
        "forced-reuse",
        "alpine-not-debian",
        "per-stage-base",
        "derived-stage-inherits-debian",
        "quoted-option-value",
        "quoted-separator-is-not-a-command",
    ],
)
def test_the_base_name_scanner(dockerfile, expected):
    found = [
        pair for body in _debian_run_commands(dockerfile) for pair in _created_account_names(body)
    ]
    assert found == expected
