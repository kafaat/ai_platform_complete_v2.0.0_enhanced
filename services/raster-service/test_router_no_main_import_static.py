"""Static contract: APIRouter modules must not depend on main.py.

main.py is now the application/bootstrap facade. Routers should consume extracted
runtime/model/helper modules directly so future changes are localized and testable.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_raster_routers_do_not_import_or_use_main_module():
    root = Path(__file__).resolve().parent / "routers"
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "main" for alias in node.names):
                offenders.append(f"{path.name}:{node.lineno}: import main")
            elif isinstance(node, ast.ImportFrom) and node.module == "main":
                offenders.append(f"{path.name}:{node.lineno}: from main import ...")
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "main"
            ):
                offenders.append(f"{path.name}:{node.lineno}: main.{node.attr}")
    assert not offenders, "routers must not depend on main.py: " + "; ".join(offenders)


def _main_dependency_offenders(paths):
    offenders: list[str] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "main" for alias in node.names):
                offenders.append(f"{path.name}:{node.lineno}: import main")
            elif isinstance(node, ast.ImportFrom) and node.module == "main":
                offenders.append(f"{path.name}:{node.lineno}: from main import ...")
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "main"
            ):
                offenders.append(f"{path.name}:{node.lineno}: main.{node.attr}")
    return offenders


def test_raster_workers_do_not_import_or_use_main_module():
    root = Path(__file__).resolve().parent
    workers = [root / "backfill_scan_worker.py", root / "cache_invalidation_worker.py"]
    offenders = _main_dependency_offenders(workers)
    assert not offenders, "raster workers must not depend on main.py: " + "; ".join(offenders)


def test_raster_production_modules_do_not_import_or_use_main_module():
    """Production modules must not import main.py outside the app bootstrap itself.

    Tests may still import ``main`` to exercise the FastAPI app and legacy
    compatibility surface, but runtime modules should depend on extracted
    modules directly. This keeps ``main.py`` as a thin application facade.
    """
    root = Path(__file__).resolve().parent
    production_files = []
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if path.name == "main.py" or path.name.startswith("test_"):
            continue
        if "__pycache__" in rel_parts:
            continue
        production_files.append(path)
    offenders = _main_dependency_offenders(production_files)
    assert not offenders, "production raster modules must not depend on main.py: " + "; ".join(
        offenders
    )
