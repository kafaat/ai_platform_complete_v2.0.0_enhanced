#!/usr/bin/env python3
"""Prevent reintroduction of deprecated FastAPI ``on_event`` hooks.

The platform bootstrap must use a single lifespan context so startup and
shutdown ordering stay explicit and FastAPI deprecation warnings remain absent.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services" / "sahool-platform" / "api" / "main.py"


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert ".on_event(" not in source, "deprecated FastAPI on_event hook reintroduced"

    tree = ast.parse(source)
    lifespan_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(dec, ast.Name) and dec.id == "asynccontextmanager"
            for dec in node.decorator_list
        )
    }
    assert "_lifespan" in lifespan_names, "FastAPI lifespan context is missing"
    assert "lifespan=_lifespan" in source, "FastAPI app is not wired to _lifespan"

    required_calls = (
        "await _warn_weak_dev_jwt_secret()",
        "await _init_db_pool()",
        "await _start_scheduler()",
        "await _start_outbox_worker()",
        "await _stop_outbox_worker()",
        "await _stop_scheduler()",
        "await _close_db_pool()",
    )
    for call in required_calls:
        assert call in source, f"lifespan operation missing: {call}"

    print("FastAPI lifespan guard: PASS")


if __name__ == "__main__":
    main()
