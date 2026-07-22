#!/usr/bin/env python3
"""Static guard for internal S2S routes and GraphQL read facade security."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_MAIN = ROOT / "services/sahool-platform/api/main.py"
PLATFORM_INTERNAL = ROOT / "services/sahool-platform/api/routers/internal_service.py"
KG_MAIN = ROOT / "services/knowledge-graph/main.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _decorated_function_source(path: Path, route: str) -> str:
    txt = _text(path)
    tree = ast.parse(txt, filename=str(path))
    lines = txt.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
                and dec.args[0].value == route
            ):
                start = min(
                    [getattr(d, "lineno", node.lineno) for d in node.decorator_list] + [node.lineno]
                )
                end = getattr(node, "end_lineno", node.lineno)
                return "\n".join(lines[start - 1 : end])
    raise SystemExit(f"route not found: {path}:{route}")


def main() -> int:
    for route in ["/internal/fields/{field_id}/state", "/internal/events/ai-advice"]:
        src = _decorated_function_source(PLATFORM_INTERNAL, route)
        if "Depends(_require_service_token)" not in src:
            raise SystemExit(f"internal route missing service-token dependency: {route}")
        service_guard = _text(ROOT / "services/sahool-platform/api/service_token_auth.py")
        if (
            'Header(None, alias="X-Agent-Token")' not in service_guard
            and "X-Agent-Token" not in service_guard
        ):
            raise SystemExit("platform service-token guard does not reference X-Agent-Token")
    kg = _text(KG_MAIN)
    graphql_src = _decorated_function_source(KG_MAIN, "/graphql")
    required = [
        "Depends(require_trusted_tenant)",
        "_assert_graphql_query_budget(req.query)",
        "MAX_GRAPHQL_DEPTH",
        "MAX_GRAPHQL_TOKENS",
        "MAX_GRAPHQL_QUERY_BYTES",
        "graphql_introspection_disabled",
    ]
    for needle in required:
        if needle not in kg and needle not in graphql_src:
            raise SystemExit(f"GraphQL security control missing: {needle}")
    print("internal_graphql_security_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
