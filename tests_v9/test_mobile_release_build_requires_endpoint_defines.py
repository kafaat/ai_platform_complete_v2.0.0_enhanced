"""
tests_v9/test_mobile_release_build_requires_endpoint_defines.py

Offline guard (slice of MOBILE-DEFAULT-API-HOST-HAS-NO-DNS-01).

The Flutter app compiles in endpoint defaults
(``mobile/sahool_app/lib/config/app_config.dart:7-8``: ``API_URL`` ->
``https://api.sahool.ye``, ``WS_URL`` -> ``wss://api.sahool.ye``, with
``SAHOOL_ENV`` defaulting to ``prod``). That host does not resolve, so a
binary built without overriding both defines ships an app that cannot reach
any backend -- silently, because nothing fails at build time.

Today the only builds are debug APKs (``.github/workflows/ci.yml`` "Build
Android debug app" step, ``.github/workflows/realtime-mobile.yml`` "Compile
native Android application" step) and release signing is deliberately
unconfigured (``mobile/sahool_app/android/app/build.gradle:38``). This test
keeps it that way unless the endpoint is supplied: every ``flutter build``
invocation found in

* every ``.github/workflows/*.yml`` / ``*.yaml`` (all YAML string values, so
  ``run:`` blocks, folded scalars and action inputs are all seen),
* every tracked file under ``mobile/`` and ``scripts/``,
* ``mobile/sahool_app/BUILDING.md``,

that is not a ``--debug`` build (release/profile ``apk``, ``appbundle``,
``ipa``, ``ios``, ``web``, desktop, or a target held in a variable) must pass
``--dart-define=API_URL=...`` *and* ``--dart-define=WS_URL=...`` with a
non-empty value that is not the compiled-in default, or a
``--dart-define-from-file`` pointing at a git-tracked file that sets both.

It does not change ``app_config.dart`` or app behaviour (the default host is
an owner product decision); it only forbids building a non-debug binary that
relies on it. The scanner is pure text analysis -- no Flutter SDK, no network.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parent.parent
APP_DIR = "mobile/sahool_app"
APP_CONFIG = REPO / APP_DIR / "lib/config/app_config.dart"
BUILDING_MD = f"{APP_DIR}/BUILDING.md"
REQUIRED_KEYS = ("API_URL", "WS_URL")

# `flutter build <target>` subcommands. A first positional token outside this
# set (e.g. "flutter build latency" in a Podfile comment) is prose, not a build.
BUILD_TARGETS = frozenset(
    {
        "aar",
        "apk",
        "appbundle",
        "bundle",
        "ios",
        "ios-framework",
        "ipa",
        "linux",
        "macos",
        "macos-framework",
        "web",
        "windows",
        "xcarchive",
    }
)

# `flutter`, bare or path-qualified (`/opt/flutter/bin/flutter`, `$FLUTTER_ROOT/bin/flutter`,
# `${{ env.FLUTTER_HOME }}/bin/flutter`), optionally followed by global flags, then `build`.
_BUILD_RE = re.compile(
    r"(?<![\w.-])(?:[^\s'\"]*/)?flutter(?:\.bat)?(?:\s+--?[\w-]+(?:=\S+)?)*\s+build\b"
)
_GHA_EXPR_RE = re.compile(r"\$\{\{.*?\}\}")
_STOP_TOKENS = frozenset({";", "&&", "||", "|", "&", ";;"})
_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pmtiles",
        ".jar",
        ".keystore",
        ".jks",
        ".zip",
        ".ttf",
        ".otf",
    }
)


# --------------------------------------------------------------------------- #
# Compiled-in defaults (read, never hard-coded, so the guard tracks the source)
# --------------------------------------------------------------------------- #
def compiled_defaults(text: str | None = None) -> dict[str, str]:
    if text is None:
        text = APP_CONFIG.read_text(encoding="utf-8")
    found = dict(
        re.findall(
            r"String\.fromEnvironment\(\s*'(\w+)'\s*,\s*defaultValue:\s*'([^']*)'\s*\)", text
        )
    )
    return {k: found[k] for k in REQUIRED_KEYS if k in found}


# --------------------------------------------------------------------------- #
# Invocation model
# --------------------------------------------------------------------------- #
@dataclass
class Invocation:
    source: str  # "path[:locator]"
    command: str
    target: str
    debug: bool
    defines: dict[str, str] = field(default_factory=dict)
    define_files: list[str] = field(default_factory=list)
    base_dirs: tuple[str, ...] = ()


def _tokenize(rest: str) -> list[str]:
    lex = shlex.shlex(rest, posix=True, punctuation_chars=";&|")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:  # unterminated quote: fall back to whitespace split
        tokens = rest.split()
    out: list[str] = []
    for tok in tokens:
        if tok in _STOP_TOKENS or (tok and set(tok) <= set(";&|")):
            break
        out.append(tok)
    return out


def _join_continuations(text: str) -> str:
    # POSIX shell line continuations (also inside YAML `run: |` blocks).
    return re.sub(r"\\[ \t]*\r?\n[ \t]*", " ", text)


def extract_invocations(
    text: str, source: str, base_dirs: Iterable[str] = (), *, strip_hash_comments: bool = False
) -> list[Invocation]:
    text = _GHA_EXPR_RE.sub("__GHA_EXPR__", _join_continuations(text))
    found: list[Invocation] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if strip_hash_comments and line.lstrip().startswith("#"):
            continue
        for m in _BUILD_RE.finditer(line):
            rest = line[m.end() :]
            if "`" in rest:  # inline code in Markdown ends at the backtick
                rest = rest.split("`", 1)[0]
            tokens = [t.strip("`") for t in _tokenize(rest)]
            positional = [t for t in tokens if not t.startswith("-")]
            if not positional:
                continue
            target = positional[0]
            if (
                target not in BUILD_TARGETS
                and not target.startswith("$")
                and target != "__GHA_EXPR__"
            ):
                continue  # prose such as "flutter build latency"
            inv = Invocation(
                source=f"{source}:{lineno}",
                command=f"flutter build {rest.strip()}",
                target=target,
                debug=False,
                base_dirs=tuple(base_dirs),
            )
            modes: set[str] = set()
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                nxt = tokens[i + 1] if i + 1 < len(tokens) else None
                if tok in ("--debug", "--release", "--profile"):
                    modes.add(tok)
                elif tok == "--dart-define" and nxt is not None:
                    _add_define(inv, nxt)
                    i += 1
                elif tok.startswith("--dart-define="):
                    _add_define(inv, tok.split("=", 1)[1])
                elif tok == "--dart-define-from-file" and nxt is not None:
                    inv.define_files.append(nxt)
                    i += 1
                elif tok.startswith("--dart-define-from-file="):
                    inv.define_files.append(tok.split("=", 1)[1])
                i += 1
            # Only an explicit --debug with no competing release/profile flag is debug.
            inv.debug = modes == {"--debug"}
            found.append(inv)
    return found


def _add_define(inv: Invocation, kv: str) -> None:
    key, sep, value = kv.partition("=")
    if sep:
        inv.defines[key] = value


def _parse_define_file(text: str) -> dict[str, str]:
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        return {str(k): "" if v is None else str(v) for k, v in data.items()}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'\"")
    return out


def violations(
    inv: Invocation,
    defaults: dict[str, str],
    tracked: frozenset[str],
    read: Callable[[str], str],
) -> list[str]:
    """Return human-readable problems for one invocation (empty == compliant)."""
    if inv.debug:
        return []
    values = dict(inv.defines)
    problems: list[str] = []
    for ref in inv.define_files:
        if "$" in ref or "__GHA_EXPR__" in ref:
            problems.append(
                f"--dart-define-from-file={ref} is not a literal path; cannot verify offline"
            )
            continue
        candidates = [os.path.normpath(os.path.join(b, ref)) for b in (*inv.base_dirs, APP_DIR, "")]
        hit = next((c for c in candidates if c in tracked), None)
        if hit is None:
            problems.append(
                f"--dart-define-from-file={ref} is not a git-tracked file (looked at {candidates})"
            )
            continue
        for k, v in _parse_define_file(read(hit)).items():
            values.setdefault(k, v)
    for key in REQUIRED_KEYS:
        value = values.get(key, "").strip()
        if not value:
            problems.append(f"missing --dart-define={key}=...")
        elif defaults.get(key) and value == defaults[key]:
            problems.append(
                f"{key} is set to the compiled-in default {value!r}, which does not resolve"
            )
    return problems


# --------------------------------------------------------------------------- #
# Repository scan
# --------------------------------------------------------------------------- #
def _tracked_files() -> frozenset[str]:
    try:
        raw = subprocess.run(
            ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
        ).stdout
        # Decode explicitly: the suite also runs under LC_ALL=C (locale-trap gate).
        out = raw.decode("utf-8", errors="surrogateescape")
        return frozenset(p for p in out.split("\0") if p)
    except (OSError, subprocess.CalledProcessError):  # not a git checkout: walk the tree
        return frozenset(
            str(p.relative_to(REPO)).replace(os.sep, "/")
            for top in (".github/workflows", "mobile", "scripts")
            for p in (REPO / top).rglob("*")
            if p.is_file()
        )


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _yaml_strings(node, wd: str | None, locator: str):
    """Yield (string, working_directory, locator) for every string in a workflow."""
    if isinstance(node, dict):
        defaults = node.get("defaults")
        if isinstance(defaults, dict) and isinstance(defaults.get("run"), dict):
            wd = defaults["run"].get("working-directory", wd) or wd
        own_wd = node.get("working-directory")
        if isinstance(own_wd, str):
            wd = own_wd
        for key, value in node.items():
            yield from _yaml_strings(value, wd, f"{locator}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _yaml_strings(value, wd, f"{locator}[{i}]")
    elif isinstance(node, str):
        yield node, wd, locator


def workflow_invocations(text: str, source: str) -> list[Invocation]:
    data = yaml.safe_load(text)
    found: list[Invocation] = []
    for string, wd, locator in _yaml_strings(data, None, ""):
        if "flutter" not in string:
            continue
        base = (wd,) if wd and "$" not in wd else ()
        found.extend(extract_invocations(string, f"{source}#{locator}", base))
    return found


def scan_repository() -> tuple[list[Invocation], list[str]]:
    tracked = _tracked_files()
    invocations: list[Invocation] = []
    scanned: list[str] = []
    for rel in sorted(tracked):
        is_workflow = rel.startswith(".github/workflows/") and rel.endswith((".yml", ".yaml"))
        in_scope = is_workflow or rel == BUILDING_MD or rel.startswith(("mobile/", "scripts/"))
        if not in_scope or Path(rel).suffix.lower() in _BINARY_SUFFIXES:
            continue
        try:
            text = _read(rel)
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        scanned.append(rel)
        if "flutter" not in text:
            continue
        if is_workflow:
            invocations.extend(workflow_invocations(text, rel))
        else:
            invocations.extend(
                extract_invocations(
                    text,
                    rel,
                    (os.path.dirname(rel),),
                    strip_hash_comments=not rel.endswith(".md"),
                )
            )
    return invocations, scanned


# --------------------------------------------------------------------------- #
# Tests against the real tree
# --------------------------------------------------------------------------- #
def test_compiled_defaults_are_read_from_app_config():
    defaults = compiled_defaults()
    assert set(defaults) == set(REQUIRED_KEYS), (
        f"could not read API_URL/WS_URL defaults from {APP_CONFIG}; the guard would compare against nothing"
    )


def test_scanner_sees_the_known_ci_debug_builds():
    """Anti-vacuity: the scan must find the two existing CI debug APK builds."""
    invocations, scanned = scan_repository()
    assert ".github/workflows/ci.yml" in scanned and BUILDING_MD in scanned
    sources = {inv.source.split("#", 1)[0].split(":", 1)[0] for inv in invocations}
    assert {".github/workflows/ci.yml", ".github/workflows/realtime-mobile.yml"} <= sources, sources
    assert any(inv.debug and inv.target == "apk" for inv in invocations)


def test_every_non_debug_flutter_build_overrides_the_unresolvable_endpoint_defaults():
    defaults = compiled_defaults()
    tracked = _tracked_files()
    invocations, _ = scan_repository()
    failures = []
    for inv in invocations:
        problems = violations(inv, defaults, tracked, _read)
        if problems:
            failures.append(f"{inv.source}: `{inv.command}` -> {'; '.join(problems)}")
    assert not failures, (
        "Non-debug `flutter build` without explicit endpoint defines. The compiled-in defaults "
        f"{defaults} do not resolve (MOBILE-DEFAULT-API-HOST-HAS-NO-DNS-01); pass "
        "--dart-define=API_URL=... and --dart-define=WS_URL=... (or a tracked "
        "--dart-define-from-file setting both). See mobile/sahool_app/BUILDING.md.\n"
        + "\n".join(failures)
    )


def test_building_md_documents_the_unresolvable_default_and_a_compliant_release_build():
    text = _read(BUILDING_MD)
    defaults = compiled_defaults()
    host = re.sub(r"^\w+://", "", defaults["API_URL"]).split("/", 1)[0]
    assert host in text, (
        f"{BUILDING_MD} must name the compiled-in default host {host!r} and say it does not resolve"
    )
    assert re.search(r"does not resolve|not (?:a )?resolvable", text), (
        f"{BUILDING_MD} must state that the compiled-in default host is not resolvable"
    )
    release = [inv for inv in extract_invocations(text, BUILDING_MD) if not inv.debug]
    assert release, (
        f"{BUILDING_MD} must show a non-debug build example that passes API_URL and WS_URL"
    )
    for inv in release:
        assert not violations(inv, defaults, _tracked_files(), _read), inv


# --------------------------------------------------------------------------- #
# Falsification: synthetic inputs the guard must flag / accept
# --------------------------------------------------------------------------- #
_DEFAULTS = {"API_URL": "https://api.sahool.ye", "WS_URL": "wss://api.sahool.ye"}


def _check_workflow(
    text: str, tracked: frozenset[str] = frozenset(), files: dict[str, str] | None = None
):
    files = files or {}
    invs = workflow_invocations(text, "synthetic.yml")
    return invs, [violations(inv, _DEFAULTS, tracked, files.__getitem__) for inv in invs]


_RELEASE_WITHOUT_DEFINES = """
name: mobile-release
on: workflow_dispatch
jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile/sahool_app
    steps:
      - run: flutter pub get
      - name: Release bundle
        run: flutter build appbundle --release --no-pub
"""


def test_falsification_release_build_without_defines_is_flagged():
    invs, problems = _check_workflow(_RELEASE_WITHOUT_DEFINES)
    assert [inv.target for inv in invs] == ["appbundle"]
    assert problems == [["missing --dart-define=API_URL=...", "missing --dart-define=WS_URL=..."]]


@pytest.mark.parametrize(
    "command, expected",
    [
        # default mode (no flag) of `flutter build apk` is release
        ("flutter build apk", 2),
        ("flutter build ipa --dart-define=API_URL=https://api.example.org", 1),
        (
            "flutter build web --profile --dart-define WS_URL=wss://x.example --dart-define API_URL=",
            1,
        ),
        ("flutter build apk --debug --release", 2),
        ("flutter -v build $TARGET --release", 2),
        (
            "fvm flutter build apk --split-per-abi && echo --dart-define=API_URL=x --dart-define=WS_URL=y",
            2,
        ),
        # explicitly passing the unresolvable default is the same silent ship
        (
            "flutter build apk --dart-define=API_URL=https://api.sahool.ye --dart-define=WS_URL=wss://h.example",
            1,
        ),
        # a path-qualified SDK binary is the same build (self-hosted / container CI)
        ("/opt/flutter/bin/flutter build appbundle", 2),
        ("$FLUTTER_ROOT/bin/flutter build apk --release", 2),
        ("./flutter/bin/flutter build apk --release", 2),
        ("${{ env.FLUTTER_HOME }}/bin/flutter build ipa", 2),
        ("flutter.bat build apk --release", 2),
        # compliant
        ("flutter build apk --debug --no-pub", 0),
        ("$FLUTTER_ROOT/bin/flutter build apk --debug", 0),
        (
            "flutter build apk --release --dart-define=API_URL=https://h.example --dart-define=WS_URL=wss://h.example",
            0,
        ),
        (
            "flutter build appbundle --dart-define=API_URL=${{ vars.API_URL }} --dart-define=WS_URL=${{ vars.WS_URL }}",
            0,
        ),
    ],
)
def test_falsification_command_matrix(command, expected):
    invs = extract_invocations(command, "synthetic.sh")
    assert len(invs) == 1, invs
    assert len(violations(invs[0], _DEFAULTS, frozenset(), lambda _p: "")) == expected


def test_falsification_multiline_forms_are_seen():
    folded = (
        "jobs:\n  b:\n    steps:\n      - run: >\n          flutter build ipa\n          --release\n"
        "      - run: |\n          flutter build apk \\\n            --release \\\n            --dart-define=API_URL=https://h.example\n"
    )
    invs, problems = _check_workflow(folded)
    assert [inv.target for inv in invs] == ["ipa", "apk"]
    assert [len(p) for p in problems] == [2, 1]


def test_falsification_define_from_file_must_be_tracked_and_set_both_keys():
    base = (
        "jobs:\n  b:\n    steps:\n      - working-directory: mobile/sahool_app\n"
        "        run: flutter build apk --release --dart-define-from-file={}\n"
    )
    good = "mobile/sahool_app/config/release.json"
    half = "mobile/sahool_app/config/half.env"
    files = {
        good: json.dumps({"API_URL": "https://h.example", "WS_URL": "wss://h.example"}),
        half: "API_URL=https://h.example\n",
    }
    tracked = frozenset(files)
    assert _check_workflow(base.format("config/release.json"), tracked, files)[1] == [[]]
    assert _check_workflow(base.format("config/half.env"), tracked, files)[1] == [
        ["missing --dart-define=WS_URL=..."]
    ]
    untracked = _check_workflow(base.format("config/missing.json"), tracked, files)[1]
    assert len(untracked[0]) == 3 and "not a git-tracked file" in untracked[0][0]


def test_falsification_prose_and_comments_are_not_builds():
    assert (
        extract_invocations("# CocoaPods stats affecting flutter build latency.", "Podfile") == []
    )
    assert (
        extract_invocations("# flutter build apk --release", "x.sh", strip_hash_comments=True) == []
    )
    assert extract_invocations("run `flutter build apk --debug` locally", "x.md")[0].debug


def test_falsification_compiled_defaults_parser():
    dart = (
        "static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'https://a.invalid');\n"
        "static const wsUrl = String.fromEnvironment('WS_URL', defaultValue: 'wss://a.invalid');\n"
    )
    assert compiled_defaults(dart) == {"API_URL": "https://a.invalid", "WS_URL": "wss://a.invalid"}
