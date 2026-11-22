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
import json
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
# Images whose default variant is Debian or Ubuntu, and tag words that name one.
_DEBIAN_IMAGES = frozenset(
    {"python", "debian", "ubuntu", "node", "buildpack-deps", "pytorch"}
    # Official images whose default variant is Debian or Ubuntu as well; their Alpine
    # variants carry "alpine" in the tag and are excluded before this lookup.
    | {"nginx", "postgres", "redis", "golang", "rust", "ruby", "php", "openjdk"}
    | {"eclipse-temurin", "maven", "gradle", "httpd"}
)
_DEBIAN_TAG = re.compile(r"bookworm|bullseye|buster|trixie|jammy|noble|focal|ubuntu|debian")
_ACCOUNT_COMMANDS = frozenset({"groupadd", "useradd", "addgroup", "adduser"})
# Options whose value is the next token (shadow-utils and Debian adduser). For useradd,
# `-f` is --inactive DAYS; only groupadd/addgroup read it as "force".
_OPTIONS_WITH_VALUE = frozenset(
    "-b --base-dir -c --comment -d --home-dir -e --expiredate -f --inactive -g --gid "
    "-G --groups -k --skel -K --key -p --password -R --root -P --prefix -s --shell "
    "-u --uid -Z --selinux-user --home --ingroup --gecos --firstuid --lastuid "
    "--firstgid --lastgid --conf".split()
)
_FORCE = frozenset({"-f", "--force"})
_FORCE_COMMANDS = frozenset({"groupadd", "addgroup"})
# Docker keywords are case-insensitive. A heredoc body is folded into its instruction
# before this match, so a body line such as `from pathlib import Path` never reaches it.
_INSTRUCTION = re.compile(r"([A-Za-z]+)(?:[ \t]+(.*))?\Z", re.S)
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", ";;"})
# Words that may precede the command itself within one simple command.
_LEADING_WORDS = frozenset(
    {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}", "time"}
    | {"exec", "command", "nohup"}
)
# Wrappers that run the next command, with the options that take a value. `env` also
# takes NAME=VALUE words; `timeout` and `nice -n` take one more word before the command.
_WRAPPERS = {
    "sudo": frozenset(
        "-u --user -g --group -C --close-from -D --chdir -h --host -p --prompt "
        "-r --role -t --type -U --other-user -T --command-timeout".split()
    ),
    "env": frozenset("-u --unset -C --chdir -S --split-string".split()),
    "timeout": frozenset("-s --signal -k --kill-after".split()),
    "nice": frozenset("-n --adjustment".split()),
    "chroot": frozenset("--userspec --groups".split()),
    "stdbuf": frozenset("-i -o -e".split()),
}
_WRAPPER_POSITIONAL = {"timeout": 1, "chroot": 1}  # DURATION, NEWROOT
_SHELLS = frozenset({"sh", "bash", "dash", "ash", "zsh"})
# A redirection: `>`, `2>`, `>>`, `<`, `&>` alone (its target is the next word), or with
# its target attached (`2>/dev/null`, `>out.log`).
_REDIRECT = re.compile(r"\A(?:\d*|&)(?:>>?|<<<|<<-?|<>|>&|<&|>\|)(.*)\Z")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def _instructions(text):
    """(KEYWORD, arguments) pairs for a Dockerfile.

    Continuations are joined and comment lines dropped. A heredoc body
    (`RUN python - <<'PY' ... PY`) is folded into its instruction, and keywords
    are matched in upper case (the repository's convention), so a heredoc line such
    as `from pathlib import Path` is never mistaken for a FROM instruction.
    """
    lines = text.splitlines()
    out, pending, i = [], "", 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        instruction, pending = pending + line, ""
        for _quote, delimiter in _HEREDOC.findall(instruction):
            body = []
            while i < len(lines) and lines[i].strip() != delimiter:
                body.append(lines[i])
                i += 1
            i += 1  # the closing delimiter
            instruction += "\n" + "\n".join(body)
        match = _INSTRUCTION.match(instruction)
        if match:
            out.append((match.group(1), match.group(2) or ""))
    return out


def _resolve(image, args):
    """Expand $X, ${X}, ${X:-default} and ${X-default} with the global ARG values."""

    def sub(match):
        name = match.group(1) or match.group(4)
        value = args.get(name)
        operator = match.group(2) or ""
        if value or (value is not None and operator.startswith("-")):
            return value  # `${X-d}` keeps a set-but-empty X; only `${X:-d}` replaces it
        if match.group(2) is not None:
            return match.group(3)
        return match.group(0)

    return re.sub(r"\$\{(\w+)(:?-([^}]*))?\}|\$(\w+)", sub, image)


def _image_family(image):
    """True for a Debian-family image, False for Alpine, None when the reference doesn't say."""
    ref = image.lower()
    if "alpine" in ref:
        return False
    last = ref.rsplit("/", 1)[-1]
    name = re.split(r"[:@]", last, maxsplit=1)[0]
    tag = last[len(name) :]
    if _DEBIAN_TAG.search(tag):
        return True
    if name in _DEBIAN_IMAGES and not tag.startswith("@"):
        return True  # a digest alone may pin any variant: left to the package manager
    return None


def _run_flags_stripped(body):
    """The RUN body without its leading `--mount=...`-style flags, line breaks kept.

    Keeping the newline after `<<EOF` keeps a heredoc's first command on its own line.
    """
    return re.sub(r"\A(?:[ \t]*--\S+)*[ \t]*", "", body)


def _debian_run_commands(text):
    """RUN bodies of every Debian-family stage.

    Only ARGs before the first FROM resolve FROM, and a later one wins. A stage built
    FROM an earlier stage's alias inherits its family. A digest-pinned or otherwise
    unnamed base is classified by its package manager: apt-get/dpkg is Debian, apk is not.
    """
    args, stages, aliases, seen_from = {}, [], {}, False
    for keyword, rest in _instructions(text):
        keyword = keyword.upper()
        if keyword == "ARG" and not seen_from:
            try:
                words = shlex.split(rest)
            except ValueError:
                words = rest.split()
            for word in words:  # `ARG A=1 B=img` declares two
                name, eq, default = word.partition("=")
                if eq:
                    args[name.strip()] = default.strip()
        elif keyword == "FROM":
            seen_from = True
            tokens = [t for t in rest.split() if not t.startswith("--")]
            image = _resolve(tokens[0], args) if tokens else ""
            stage = {"family": aliases.get(image.lower(), _image_family(image)), "runs": []}
            if stage["family"] is None:
                stage["family"] = "by-package-manager"
            stages.append(stage)
            if len(tokens) >= 3 and tokens[1].upper() == "AS":
                aliases[tokens[2].lower()] = stage
        elif keyword == "RUN" and stages:
            stages[-1]["runs"].append(_run_flags_stripped(rest))
    for stage in stages:
        family = stage["family"]
        while isinstance(family, dict):  # an alias resolves to the earlier stage
            family = family["family"]
        if family == "by-package-manager":
            joined = "\n".join(stage["runs"])
            family = bool(re.search(r"\b(apt-get|apt|dpkg)\b", joined)) and not re.search(
                r"\bapk\b", joined
            )
        stage["family"] = family
        if family:
            yield from stage["runs"]


def _shell_segments(run_body):
    """Simple commands of a RUN body, with shell quoting respected.

    The exec form (`RUN ["groupadd", "voice"]`) is one command, or its `sh -c` string.
    Each line is lexed on its own, so a heredoc line or `#` comment ends at the line.
    A quoted value (`--gecos "Voice service"`) stays one token and a quoted separator
    is not a command boundary. An unlexable line falls back to splitting on separators.
    """
    stripped = run_body.strip()
    if stripped.startswith("["):
        try:
            argv = json.loads(stripped.splitlines()[0])
        except ValueError:
            argv = None
        if isinstance(argv, list) and all(isinstance(a, str) for a in argv):
            if (
                len(argv) >= 3
                and argv[0].rsplit("/", 1)[-1] in _SHELLS
                and re.fullmatch(r"-[a-z]*c[a-z]*", argv[1])
            ):  # `-c`, and combined flags such as `-lc` / `-ec`
                yield from _shell_segments(argv[2])
            elif argv:
                yield argv
            return
    # A backslash continuation inside a shell heredoc body joins its lines here too.
    for line in re.sub(r"\\\n", " ", run_body).splitlines():
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError:
            tokens = re.sub(r"&&|\|\||[;&|()]", " ; ", line).split()
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
        tokens = _command_words(tokens)
        if not tokens:
            continue
        head = tokens[0].rsplit("/", 1)[-1]
        if head in _SHELLS:  # shell-form `sh -c '...'` / `bash -lc '...'`
            for i, token in enumerate(tokens[1:-1], start=1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", token):
                    names.extend(_created_account_names(tokens[i + 1]))
                    break
            continue
        if head not in _ACCOUNT_COMMANDS:
            continue
        command, positional, forced, skip = head, [], False, False
        for token in tokens[1:]:
            if skip:
                skip = False
                continue
            redirect = _REDIRECT.match(token)
            if redirect:
                skip = not redirect.group(1)  # a bare operator: its target is the next word
                continue
            if command in _FORCE_COMMANDS and token in _FORCE:
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


def _command_words(tokens):
    """The words of a simple command from the command name on.

    Drops leading keywords (`then`, `if`, ...), NAME=VALUE assignments and wrappers
    such as `sudo -u root`, `env -i`, `timeout 5` and `nice -n 10` with their options.
    """
    tokens = list(tokens)
    while tokens:
        word = tokens[0]
        base = word.rsplit("/", 1)[-1]
        if word in _LEADING_WORDS or _ASSIGNMENT.match(word):
            tokens = tokens[1:]
            continue
        if base not in _WRAPPERS:
            return tokens
        tokens, takes_value, extra = tokens[1:], _WRAPPERS[base], _WRAPPER_POSITIONAL.get(base, 0)
        while tokens and tokens[0].startswith("-") and tokens[0] != "-":
            option = tokens.pop(0)
            if option == "--":
                break
            if option in takes_value and "=" not in option:
                tokens = tokens[1:]
        if base == "env":
            while tokens and _ASSIGNMENT.match(tokens[0]):
                tokens = tokens[1:]
        tokens = tokens[extra:]
    return tokens


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
    "path",
    [
        "services/auth/Dockerfile",
        "services/decision-service/Dockerfile",
        "services/raster-tiler-service/Dockerfile",
        "services/realtime-session/Dockerfile.xiaozhi",
    ],
)
def test_the_scan_covers_heredoc_and_arg_based_dockerfiles(path):
    """These use heredocs or an ARG base; a parser slip would silently drop them."""
    text = (ROOT / path).read_text(encoding="utf-8")
    assert any(_created_account_names(body) for body in _debian_run_commands(text)), path


@pytest.mark.parametrize(
    "path",
    ["services/auth/Dockerfile", "services/decision-service/Dockerfile"],
)
def test_a_base_name_appended_to_a_real_heredoc_dockerfile_is_caught(path):
    """The review's negative control as a test: these files use RUN heredocs."""
    text = (ROOT / path).read_text(encoding="utf-8") + "\nRUN useradd -m voice\n"
    found = [pair for body in _debian_run_commands(text) for pair in _created_account_names(body)]
    assert ("useradd", "voice") in found


_DIGEST = "@sha256:" + "a" * 64
_SCANNER_CASES = {
    "original-voice-defect": (
        "FROM python:3.12-slim-bookworm\n"
        "RUN groupadd --gid 10001 voice \\\n"
        "    && useradd --uid 10001 --gid voice --no-create-home voice\n",
        [("groupadd", "voice"), ("useradd", "voice")],
    ),
    "arg-default-base": (
        "ARG BASE=python:3.12-slim-bookworm\nFROM ${BASE}\nRUN groupadd audio\n",
        [("groupadd", "audio")],
    ),
    "later-global-arg-wins": (
        "ARG BASE=alpine:3.20\nARG BASE=python:3.12-slim\nFROM $BASE\nRUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "stage-arg-does-not-resolve-from": (
        "FROM python:3.12-slim AS a\nARG IMG=alpine:3.20\nFROM ${IMG:-python:3.12-slim}\n"
        "RUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "platform-flag-debian": (
        "FROM --platform=linux/amd64 debian:bookworm\nRUN useradd -m video\n",
        [("useradd", "video")],
    ),
    "ubuntu-addgroup": (
        "FROM ubuntu:24.04 AS build\nRUN addgroup --system staff\n",
        [("addgroup", "staff")],
    ),
    "comment-ignored": (
        "FROM python:3.12-slim\n# RUN groupadd voice\nRUN groupadd app\n",
        [("groupadd", "app")],
    ),
    "adduser-membership": ("FROM python:3.12-slim\nRUN adduser app audio\n", []),
    "forced-reuse": ("FROM python:3.12-slim\nRUN groupadd -f voice\n", []),
    "useradd-f-is-inactive-days": (
        "FROM python:3.12-slim\nRUN useradd -f 30 voice\n",
        [("useradd", "voice")],
    ),
    "alpine-not-debian": ("FROM python:3.12-alpine\nRUN addgroup voice\n", []),
    "per-stage-base": (
        "FROM node:20-bookworm AS ui\nRUN groupadd voice\nFROM python:3.12-slim\nRUN groupadd app\n",
        [("groupadd", "voice"), ("groupadd", "app")],
    ),
    "alpine-stage-skipped": (
        "FROM node:22-alpine AS ui\nRUN addgroup voice\nFROM python:3.12-slim\nRUN groupadd app\n",
        [("groupadd", "app")],
    ),
    "registry-prefixed-python": (
        "FROM mirror.gcr.io/library/python:3.12-slim\nRUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "ubuntu-tag-on-other-image": (
        "FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04\nRUN groupadd video\n",
        [("groupadd", "video")],
    ),
    "digest-base-with-apt": (
        f"FROM public.ecr.aws/docker/library/nginx{_DIGEST}\nRUN apt-get update && groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "digest-base-with-apk": (
        f"FROM public.ecr.aws/docker/library/nginx{_DIGEST}\nRUN apk add bash && addgroup voice\n",
        [],
    ),
    "derived-stage-inherits-debian": (
        "FROM python:3.12-slim AS base\nFROM base AS runtime\nRUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "quoted-option-value": (
        'FROM python:3.12-slim\nRUN adduser --gecos "Voice service" --disabled-password voice\n',
        [("adduser", "voice")],
    ),
    "quoted-separator-is-not-a-command": (
        "FROM python:3.12-slim\nRUN echo 'a; groupadd voice' && groupadd app\n",
        [("groupadd", "app")],
    ),
    "heredoc-body-is-not-an-instruction": (
        "FROM python:3.12-slim\nRUN python - <<'PY'\nfrom pathlib import Path\nprint(Path('.'))\nPY\n"
        "RUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "shell-heredoc-commands": (
        "FROM python:3.12-slim\nRUN <<EOF\nset -e\ngroupadd audio\nEOF\n",
        [("groupadd", "audio")],
    ),
    "here-string-is-not-a-heredoc": (
        "FROM python:3.12-slim\nRUN cat <<< 'x' && groupadd voice\nRUN groupadd audio\n",
        [("groupadd", "voice"), ("groupadd", "audio")],
    ),
    "run-mount-flag": (
        "FROM python:3.12-slim\nRUN --mount=type=cache,target=/root/.cache groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "if-then-block": (
        "FROM python:3.12-slim\nRUN if true; then groupadd voice; fi\n",
        [("groupadd", "voice")],
    ),
    "subshell-and-env-prefix": (
        "FROM python:3.12-slim\nRUN (LC_ALL=C groupadd voice)\n",
        [("groupadd", "voice")],
    ),
    "exec-form": ('FROM python:3.12-slim\nRUN ["groupadd", "voice"]\n', [("groupadd", "voice")]),
    # Follow-ups from the #1560 delta review (N1-N5).
    "lowercase-keywords": (
        "from python:3.12-slim\nrun groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "wrapper-env-i": (
        "FROM python:3.12-slim\nRUN env -i PATH=/usr/sbin groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "wrapper-sudo-u": (
        "FROM python:3.12-slim\nRUN sudo -u root groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "wrapper-timeout": (
        "FROM python:3.12-slim\nRUN timeout -s KILL 5 groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "wrapper-nice-n": (
        "FROM python:3.12-slim\nRUN nice -n 10 useradd -m audio\n",
        [("useradd", "audio")],
    ),
    "echo-is-not-a-wrapper": ("FROM python:3.12-slim\nRUN echo groupadd voice\n", []),
    "redirect-attached": (
        "FROM python:3.12-slim\nRUN groupadd voice 2>/dev/null\n",
        [("groupadd", "voice")],
    ),
    "here-string-after-the-name": (
        "FROM python:3.12-slim\nRUN groupadd voice <<< x\n",
        [("groupadd", "voice")],
    ),
    "redirect-detached": (
        "FROM python:3.12-slim\nRUN useradd -m voice > /dev/null 2>&1\n",
        [("useradd", "voice")],
    ),
    "exec-form-bash-lc": (
        'FROM python:3.12-slim\nRUN ["bash", "-lc", "groupadd voice"]\n',
        [("groupadd", "voice")],
    ),
    "shell-form-sh-c": (
        "FROM python:3.12-slim\nRUN sh -c 'groupadd voice && echo ok'\n",
        [("groupadd", "voice")],
    ),
    "heredoc-backslash-continuation": (
        "FROM python:3.12-slim\nRUN <<EOF\ngroupadd \\\n  voice\nEOF\n",
        [("groupadd", "voice")],
    ),
    "two-args-on-one-line": (
        "ARG A=1 B=python:3.12-slim\nFROM ${B}\nRUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "dash-default-keeps-empty-value": (
        "ARG IMG=\nFROM python:3.12-slim AS py\nFROM py${IMG-:missing}\nRUN groupadd voice\n",
        [("groupadd", "voice")],
    ),
    "nginx-default-is-debian": ("FROM nginx:1.27\nRUN groupadd voice\n", [("groupadd", "voice")]),
    "nginx-alpine-is-not": ("FROM nginx:1.27-alpine\nRUN addgroup voice\n", []),
    "exec-form-sh-c": (
        'FROM python:3.12-slim\nRUN ["/bin/sh", "-c", "groupadd voice && echo ok"]\n',
        [("groupadd", "voice")],
    ),
}


@pytest.mark.parametrize(
    "dockerfile, expected", list(_SCANNER_CASES.values()), ids=list(_SCANNER_CASES)
)
def test_the_base_name_scanner(dockerfile, expected):
    found = [
        pair for body in _debian_run_commands(dockerfile) for pair in _created_account_names(body)
    ]
    assert found == expected
