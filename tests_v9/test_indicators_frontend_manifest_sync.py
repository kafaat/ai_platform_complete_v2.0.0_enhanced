"""بوّابة مزامنة: مانيفست الواجهة المُولَّد يطابق المصدر الأوحد (WS-B.2)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_GEN = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "ci"
    / "generate_indicators_frontend_manifest.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_gen_fe_manifest", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frontend_manifest_in_sync():
    mod = _load()
    assert mod._OUT.read_text(encoding="utf-8") == mod.render(), (
        "indicatorsRegistry.generated.ts انحرف عن config — أعِد التوليد: "
        "python scripts/ci/generate_indicators_frontend_manifest.py"
    )


def test_manifest_projection_is_public_only():
    mod = _load()
    _d, _v, public = mod.build()
    assert public
    for row in public:
        assert "formula_ref" not in row and "computation" not in row
        assert "availability" in row and "source_class" in row


@pytest.fixture
def manifest_cli(tmp_path, monkeypatch):
    mod = _load()
    source = tmp_path / "config/indicators_registry.json"
    source.parent.mkdir()
    source.write_bytes(mod._SRC.read_bytes())
    output = tmp_path / "frontend/src/lib/indicatorsRegistry.generated.ts"
    output.parent.mkdir(parents=True)
    monkeypatch.setattr(mod, "_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_SRC", source)
    monkeypatch.setattr(mod, "_OUT", output)
    build, calls = mod.build, []

    def counted_build():
        calls.append("build")
        return build()

    monkeypatch.setattr(mod, "build", counted_build)

    def invoke(arguments):
        monkeypatch.setattr(sys, "argv", [str(_GEN), *arguments])
        try:
            return mod.main()
        except SystemExit as exc:
            return exc.code

    return mod, output, calls, invoke


@pytest.mark.parametrize("present", [False, True], ids=["missing", "stale"])
@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["--help"], 0), (["-h"], 0), (["--chec"], 2), (["--check", "--generate"], 2)],
    ids=["help", "short-help", "unknown-prefix", "conflicting-mode"],
)
def test_manifest_cli_information_and_invalid_args_do_not_read_or_write(
    manifest_cli, present, arguments, expected, capsys
):
    _mod, output, calls, invoke = manifest_cli
    before = b"stale manifest: do not repair during argument admission\n" if present else None
    if present:
        output.write_bytes(before)
    result = invoke(arguments)
    assert (output.read_bytes() if output.exists() else None) == before
    assert calls == [], "argument admission must precede registry reads"
    assert result == expected
    captured = capsys.readouterr()
    assert "usage:" in (captured.out if expected == 0 else captured.err)


def test_manifest_cli_bare_generation_and_readonly_check_are_preserved(manifest_cli):
    mod, output, _calls, invoke = manifest_cli
    assert invoke([]) == 0
    assert output.read_text(encoding="utf-8") == mod.render()
    assert invoke(["--check"]) == 0
    output.write_bytes(b"stale manifest\n")
    assert invoke(["--check"]) == 1
    assert output.read_bytes() == b"stale manifest\n"
    output.unlink()
    assert invoke(["--check"]) == 1
    assert not output.exists()
