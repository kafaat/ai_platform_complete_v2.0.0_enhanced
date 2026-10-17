"""C-LOCALE-GUARD-SWEEPS-A-NAMING-CONVENTION-NOT-A-CLASS-01 — the class, not the name.

``guard_locale_survival_guard`` executes ``scripts/ci/*_guard.py`` under ``LC_ALL=C``;
everything else a blocking CI step runs sat outside its sight because of its name. Two
of those scripts (``capability_parity_investment_engine.py --check`` and
``tools/sahool_inspector.py``) died with ``UnicodeEncodeError`` on their **success**
path on ``0e5281614``. ``ci_invoked_locale_preamble_guard`` covers the class statically:
the inventory is what the workflows execute, the rule is read off the AST.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/ci/{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


guard = _load("ci_invoked_locale_preamble_guard")
catalogue = _load("guard_catalogue")

_PREAMBLE = """\
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
"""


def _violation(tmp_path: Path, body: str) -> str | None:
    path = tmp_path / "script.py"
    path.write_text(body, encoding="utf-8")
    return guard.violation(path)


# ── the witness: the real tree ───────────────────────────────────────────────


def test_every_script_a_blocking_ci_step_runs_survives_the_c_locale() -> None:
    """Red on ``0e5281614``: fifteen CI-invoked scripts printed non-ASCII bare."""
    files, unresolved = guard.inventory()
    findings = guard.evaluate(files, unresolved, guard.behaviourally_measured())
    assert findings == [], "\n".join(findings)


def test_the_inventory_is_the_class_not_the_naming_convention() -> None:
    """The heaviest tools in the repository are not named ``*_guard.py``.

    ``verify_all_generated`` is launched as ``python -m scripts.ci.verify_all_generated``
    and ``sahool_inspector`` lives under ``tools/`` — a ``_guard`` glob sees neither.
    """
    files, _ = guard.inventory()
    for expected in (
        "scripts/ci/guard_catalogue.py",
        "scripts/ci/verify_all_generated.py",
        "tools/sahool_inspector.py",
        "scripts/ci/capability_parity_investment_engine.py",
    ):
        assert expected in files, f"{expected} runs in a blocking step but is not inventoried"
    beyond = [f for f in files if not f.endswith("_guard.py")]
    assert len(beyond) > 100, f"only {len(beyond)} non-guard scripts inventoried"


def test_scripts_the_behavioural_sweep_executes_are_not_double_counted() -> None:
    measured = guard.behaviourally_measured()
    assert "scripts/ci/claim_base_guard.py" in measured
    assert "scripts/ci/guard_catalogue.py" not in measured, (
        "the behavioural sweep executes *_guard.py only; the catalogue must stay static"
    )


# ── the rule ──────────────────────────────────────────────────────────────────


def test_a_bare_non_ascii_print_is_flagged(tmp_path: Path) -> None:
    assert _violation(tmp_path, 'print("✓ مرّ")\n')


def test_escaped_text_is_text(tmp_path: Path) -> None:
    """``"\\u2550" * 64`` is how ``sahool_inspector`` died: ASCII source, non-ASCII output."""
    assert _violation(tmp_path, 'print("\\u2550" * 64)\n')


def test_a_name_bound_to_non_ascii_text_is_followed(tmp_path: Path) -> None:
    body = 'MARK = "✗"\nLINE = MARK + " failed"\n\ndef main():\n    print(LINE)\n'
    assert _violation(tmp_path, body)


@pytest.mark.parametrize(
    "emission",
    [
        'sys.stderr.write("✗\\n")',
        'sys.exit("✗ failed")',
        'raise SystemExit("✗ failed")',
        'print(f"{1} — done")',
    ],
)
def test_every_emission_form_counts(tmp_path: Path, emission: str) -> None:
    assert _violation(tmp_path, f"import sys\n\ndef main():\n    {emission}\n")


def test_ascii_only_output_needs_no_preamble(tmp_path: Path) -> None:
    assert _violation(tmp_path, 'import sys\nprint("ok")\nsys.exit("failed")\n') is None


def test_non_ascii_outside_an_emission_is_not_output(tmp_path: Path) -> None:
    """Docstrings and data are not stream output; only what reaches an emission counts."""
    body = '"""وثيقة."""\nimport json\nDATA = json.dumps({"ar": "نصّ"})\nprint("n")\n'
    assert _violation(tmp_path, body) is None


def test_the_preamble_makes_it_pass(tmp_path: Path) -> None:
    assert _violation(tmp_path, _PREAMBLE + 'print("✓ مرّ")\n') is None


def test_explicit_per_stream_calls_count(tmp_path: Path) -> None:
    body = (
        "import sys\n"
        'sys.stdout.reconfigure(encoding="utf-8")\n'
        'sys.stderr.reconfigure(encoding="UTF-8")\n'
        'print("✓")\n'
    )
    assert _violation(tmp_path, body) is None


def test_a_preamble_after_the_first_print_is_too_late(tmp_path: Path) -> None:
    body = 'import sys\nprint("✓")\n' + _PREAMBLE.replace("import sys\n", "")
    assert _violation(tmp_path, body)


def test_a_preamble_after_the_main_guard_is_too_late(tmp_path: Path) -> None:
    body = (
        'import sys\n\ndef main():\n    print("✓")\n\nif __name__ == "__main__":\n    main()\n'
        + _PREAMBLE.replace("import sys\n", "")
    )
    assert _violation(tmp_path, body)


def test_stdout_alone_is_half_a_preamble(tmp_path: Path) -> None:
    body = 'import sys\nsys.stdout.reconfigure(encoding="utf-8")\nprint("✗", file=sys.stderr)\n'
    assert _violation(tmp_path, body)


def test_a_preamble_inside_main_is_not_module_level(tmp_path: Path) -> None:
    body = (
        "import sys\n\ndef main():\n"
        "    for s in (sys.stdout, sys.stderr):\n"
        '        s.reconfigure(encoding="utf-8")\n'
        '    print("✓")\n'
    )
    assert _violation(tmp_path, body)


def test_an_unparseable_script_is_not_a_pass(tmp_path: Path) -> None:
    assert "unreadable" in (_violation(tmp_path, "def (:\n") or "")


# ── the inventory parser ──────────────────────────────────────────────────────


def _scan(text: str, directory: Path = ROOT, script: Path | None = None) -> list[dict]:
    return catalogue._scan_shell(text, directory, script)[0]


def test_an_unresolvable_launch_fails_closed() -> None:
    rows = _scan('python3 "$SCRIPT" --check\n')
    assert [r["status"] for r in rows] == ["unresolved"]
    findings = guard.evaluate([], [{"workflow": "w", "job": "j", "token": "$SCRIPT"}], set())
    assert findings and "unresolved" in findings[0]


def test_a_missing_file_fails_closed() -> None:
    assert [r["status"] for r in _scan("python scripts/ci/no_such_script.py\n")] == ["unresolved"]


def test_module_launches_resolve_to_files_or_known_externals() -> None:
    rows = _scan("python -m scripts.ci.verify_all_generated --check && python -m pytest -q\n")
    assert [(r["status"], r["script"]) for r in rows] == [
        ("file", "scripts/ci/verify_all_generated.py"),
        ("external", None),
    ]
    assert [r["status"] for r in _scan("python -m some_unknown_module\n")] == ["unresolved"]


def test_working_directory_and_literal_cd_are_followed() -> None:
    rows = _scan("cd evidence\npython ../scripts/ci/guard_catalogue.py --check\n")
    assert rows[0]["script"] == "scripts/ci/guard_catalogue.py"
    rows = _scan("python ../scripts/ci/guard_catalogue.py\n", ROOT / "frontend")
    assert rows[0]["script"] == "scripts/ci/guard_catalogue.py"


def test_inline_programs_and_heredoc_bodies_are_not_launches() -> None:
    text = "python3 - <<'PY'\nimport os\nos.system('python3 scripts/ci/x.py')\nPY\n"
    text += 'python -c "print(1)"\n# python scripts/ci/commented_out.py\n'
    assert _scan(text) == []


def test_a_shell_hop_is_followed_with_its_self_root_idiom() -> None:
    hop = ROOT / "scripts/ci/raster_quality_gate.sh"
    rows = _scan(hop.read_text(encoding="utf-8"), ROOT / ".github", hop)
    scripts = {r["script"] for r in rows if r["status"] == "file"}
    assert "scripts/ci/raster_import_graph_gate.py" in scripts
    assert all(r["status"] != "unresolved" for r in rows)


def test_the_catalogue_and_the_inventory_share_one_walker() -> None:
    """One parse, two views: a step the catalogue attributes must be walked here too."""
    source = (ROOT / "scripts/ci/guard_catalogue.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "_run_steps"
            for sub in ast.walk(node)
        )
    }
    assert {"discover_invocation_sites", "discover_script_invocations"} <= callers
