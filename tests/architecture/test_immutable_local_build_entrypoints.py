from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_env_example_does_not_supply_a_fake_tested_sha():
    text = (ROOT / ".env.example").read_text()
    assert "TESTED_SHA=local" not in text, "قيمةٌ زائفة جاهزة تجعل البناء يدّعي أنّه مُختبَر على لا شيء"
    assert "# TESTED_SHA=<full-40-character-git-sha>" in text


def test_env_example_declares_tested_sha_but_leaves_it_empty():
    """Declared for the contract gate, empty so the build still refuses.

    compose_env_contract_gate requires every ${VAR} a compose file references to be
    declared here, so the key cannot simply be deleted. But docker-compose.v9.yml uses
    ``${TESTED_SHA:?...}``, and the ``:?`` form treats empty exactly like unset -- so an
    empty declaration satisfies the contract without handing the build an identity. A
    non-empty value here would silently re-create the ``TESTED_SHA=local`` problem under
    a different spelling, which is why this pins the emptiness rather than the absence.
    """
    assignments = [
        line
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line.strip().startswith("TESTED_SHA=")
    ]
    assert assignments == ["TESTED_SHA="], assignments


def test_bash_wrapper_derives_and_exports_full_head_sha():
    text = (ROOT / "scripts/build-immutable.sh").read_text()
    assert "git rev-parse HEAD" in text
    assert "^[0-9a-f]{40}$" in text
    assert 'export TESTED_SHA="$sha"' in text
    assert "docker compose" in text and "config --quiet" in text
    assert "git status --porcelain" in text


def test_powershell_wrapper_derives_full_head_sha_and_validates_compose():
    text = (ROOT / "scripts/build-immutable.ps1").read_text()
    assert "git rev-parse HEAD" in text
    assert "^[0-9a-f]{40}$" in text
    assert "$env:TESTED_SHA = $sha" in text
    assert "config --quiet" in text
    assert "git status --porcelain" in text


def test_makefile_exposes_immutable_build_entrypoints():
    text = (ROOT / "Makefile").read_text()
    assert "build-immutable:" in text
    assert "build-immutable-gpu:" in text
    assert "./scripts/build-immutable.sh --gpu" in text


def test_env_example_declares_build_id_but_leaves_it_empty():
    """`local` is no more a build identity than it was a source SHA.

    Same reasoning as TESTED_SHA: declared so compose_env_contract_gate is satisfied,
    empty so ``${SAHOOL_BUILD_ID:?...}`` still refuses. Leaving `local` here would stamp
    an image with an identity derived from nothing, while the wrapper derives
    ``local-<sha12>`` from HEAD.
    """
    assignments = [
        line
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line.strip().startswith("SAHOOL_BUILD_ID=")
    ]
    assert assignments == ["SAHOOL_BUILD_ID="], assignments
