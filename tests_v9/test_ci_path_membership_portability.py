"""Path membership in CI scripts must not depend on the OS path separator.

Three scripts asked "is this file under a ``tests/`` (or ``.venv/``, ``node_modules/``)
directory?" with a POSIX substring on ``str(path)``:

- ``generate_service_inventory.py``: ``"/tests/" in str(p)``
- ``health_readiness_schema_guard.py``: ``"/.venv/" in str(path)``
- ``tenant_guc_scope_guard.py``: ``"/tests/"``, ``"/tests_v9/"``, ``"/node_modules/"``, ``"/.git/"``

On Windows ``str(path)`` uses backslashes, so neither substring ever matched there:
the same tree produced different answers locally and in Linux CI (measured by the
owner: ``auth`` had 2 test files in CI and 1 on Windows, so ``--check`` reported
false drift). The fix decides on path components below the service dir / repo root.

These tests feed the same logical paths as ``PurePosixPath`` and ``PureWindowsPath``
and require identical classification, then show the old predicate disagrees with
itself across the two flavours (the falsification: revert the fix and the
cross-flavour tests go red). No filesystem access is needed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FLAVOURS = (PurePosixPath, PureWindowsPath)
POSIX_REPO = "/work/repo"
WINDOWS_REPO = "C:\\work\\repo"


def _load(name: str):
    path = ROOT / "scripts" / "ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_under_portability_test", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inventory():
    return _load("generate_service_inventory")


@pytest.fixture(scope="module")
def health():
    return _load("health_readiness_schema_guard")


@pytest.fixture(scope="module")
def tenant_guc():
    return _load("tenant_guc_scope_guard")


def _repo(flavour):
    return flavour(POSIX_REPO if flavour is PurePosixPath else WINDOWS_REPO)


def _old_inventory_predicate(path: PurePath) -> bool:
    """The predicate as it was before the fix, kept verbatim for falsification."""
    return path.name.startswith("test_") or "/tests/" in str(path)


def _old_venv_predicate(path: PurePath) -> bool:
    """The predicate as it was before the fix, kept verbatim for falsification."""
    return "/.venv/" in str(path)


# (path relative to the service dir, expected "is a test file")
INVENTORY_CASES = [
    (("tests", "conftest.py"), True),  # the auth 2-vs-1 case: not named test_*
    (("tests", "helpers", "factory.py"), True),
    (("app", "tests", "fixtures.py"), True),
    (("test_api.py",), True),
    (("app", "test_routes.py"), True),
    (("app", "main.py"), False),
    (("testsuite", "runner.py"), False),  # component match, not a prefix match
    (("app", "tests.py"), False),  # a file named tests.py is not a tests/ dir
]


@pytest.mark.parametrize("flavour", FLAVOURS, ids=lambda f: f.__name__)
@pytest.mark.parametrize(("parts", "expected"), INVENTORY_CASES)
def test_inventory_classifies_test_files_by_component(inventory, flavour, parts, expected):
    service_dir = _repo(flavour) / "services" / "auth"
    assert inventory.is_test_file(service_dir.joinpath(*parts), service_dir) is expected


@pytest.mark.parametrize(("parts", "expected"), INVENTORY_CASES)
def test_inventory_answer_is_identical_on_posix_and_windows(inventory, parts, expected):
    answers = {
        flavour.__name__: inventory.is_test_file(
            (_repo(flavour) / "services" / "auth").joinpath(*parts),
            _repo(flavour) / "services" / "auth",
        )
        for flavour in FLAVOURS
    }
    assert set(answers.values()) == {expected}, answers


def test_old_inventory_predicate_disagrees_across_flavours():
    """Falsification: the pre-fix predicate counts tests/conftest.py only on POSIX."""
    posix = PurePosixPath(POSIX_REPO, "services", "auth", "tests", "conftest.py")
    windows = PureWindowsPath(WINDOWS_REPO, "services", "auth", "tests", "conftest.py")
    assert _old_inventory_predicate(posix) is True
    assert _old_inventory_predicate(windows) is False


def test_inventory_ignores_a_tests_directory_above_the_service(inventory):
    """Only components inside the service count: a checkout under ``/tmp/tests/``
    must not turn every service file into a test (the old substring did)."""
    service_dir = PurePosixPath("/tmp/tests/repo/services/auth")
    main = service_dir / "app" / "main.py"
    assert _old_inventory_predicate(main) is True
    assert inventory.is_test_file(main, service_dir) is False


# (path relative to the repo root, expected "inside a .venv")
VENV_CASES = [
    ((".venv", "lib", "site-packages", "pkg", "main.py"), True),
    (("services", "auth", ".venv", "lib", "main.py"), True),
    (("services", "auth", "main.py"), False),
    (("services", "venv_tools", "main.py"), False),
]


@pytest.mark.parametrize("flavour", FLAVOURS, ids=lambda f: f.__name__)
@pytest.mark.parametrize(("parts", "expected"), VENV_CASES)
def test_health_guard_skips_virtualenvs_by_component(health, flavour, parts, expected):
    root = _repo(flavour)
    assert health._is_in_virtualenv(root.joinpath(*parts), root) is expected


def test_old_venv_predicate_disagrees_across_flavours():
    """Falsification: the pre-fix predicate skips a .venv only on POSIX."""
    posix = PurePosixPath(POSIX_REPO, ".venv", "lib", "main.py")
    windows = PureWindowsPath(WINDOWS_REPO, ".venv", "lib", "main.py")
    assert _old_venv_predicate(posix) is True
    assert _old_venv_predicate(windows) is False


def test_health_guard_ignores_a_venv_above_the_repo_root(health):
    root = PurePosixPath("/home/me/.venv/src/repo")
    main = root / "services" / "auth" / "main.py"
    assert _old_venv_predicate(main) is True
    assert health._is_in_virtualenv(main, root) is False


def _old_tenant_guc_excluded(path: PurePath) -> bool:
    """The tenant GUC guard's exclusion as it was before the fix, kept verbatim."""
    s = str(path)
    if "/node_modules/" in s or "/.git/" in s:
        return True
    return path.name.startswith("test_") or "/tests/" in s or "/tests_v9/" in s


# (path relative to the repo root, expected "excluded from the scan")
TENANT_GUC_CASES = [
    (("services", "auth", "tests", "conftest.py"), True),
    (("tests_v9", "helpers.py"), True),
    (("services", "auth", "test_login.py"), True),
    (("frontend", "node_modules", "pkg", "x.py"), True),
    ((".git", "hooks", "x.py"), True),
    (("services", "auth", "db.py"), False),
    (("services", "testsuite", "db.py"), False),
]


@pytest.mark.parametrize("flavour", FLAVOURS, ids=lambda f: f.__name__)
@pytest.mark.parametrize(("parts", "expected"), TENANT_GUC_CASES)
def test_tenant_guc_guard_excludes_by_component(tenant_guc, flavour, parts, expected):
    root = _repo(flavour)
    assert tenant_guc._is_excluded(root.joinpath(*parts), root) is expected


def test_old_tenant_guc_exclusion_disagrees_across_flavours():
    """Falsification: the pre-fix exclusion skipped tests/ only on POSIX."""
    posix = PurePosixPath(POSIX_REPO, "services", "auth", "tests", "conftest.py")
    windows = PureWindowsPath(WINDOWS_REPO, "services", "auth", "tests", "conftest.py")
    assert _old_tenant_guc_excluded(posix) is True
    assert _old_tenant_guc_excluded(windows) is False


def test_tenant_guc_guard_ignores_a_tests_directory_above_the_root(tenant_guc):
    root = PurePosixPath("/srv/tests/repo")
    source = root / "services" / "auth" / "db.py"
    assert _old_tenant_guc_excluded(source) is True
    assert tenant_guc._is_excluded(source, root) is False
