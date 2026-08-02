#!/usr/bin/env python3
"""Sub-inventory for services/sahool-platform/api/main.py.

The P1 decomposition removed direct routes from platform main.py. This guard
freezes the remaining bootstrap surface so future changes are reviewed instead
of silently re-growing business routes in main.py.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generated_artifact_contract import (  # noqa: E402
    Artifact,
    enforce,
    render_csv,
    render_json,
    write_all,
)

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services" / "sahool-platform" / "api" / "main.py"
JSON_PATH = ROOT / "platform_main_subinventory.generated.json"
CSV_PATH = ROOT / "platform_main_subinventory.csv"
REPORT_PATH = ROOT / "PLATFORM_MAIN_SUBINVENTORY_20260709.md"

STARTUP_NAMES = {"startup", "on_startup", "_init", "scheduler", "outbox", "pool", "db"}
SHUTDOWN_NAMES = {"shutdown", "close", "stop"}
MIDDLEWARE_NAMES = {"middleware", "rate_limit", "cors", "correlation"}
AUTH_NAMES = {"token", "jwt", "user", "permission", "role", "auth", "denylist", "hs256", "rs256"}
DB_NAMES = {"db", "pool", "tenant", "conn", "rls", "guc"}
EVENT_NAMES = {"event", "outbox", "domain", "idempotent", "idem", "scheduler"}
MAPPER_NAMES = {"row_to", "summary", "prefs", "parse", "normalize", "centroid", "geocode"}
ALERT_NAMES = {"alert", "walk", "issue", "activity", "soil", "task", "field"}
WORKFLOW_NAMES = {"workflow", "pydantic", "model", "rebuild"}

CATEGORY_CLASSIFICATION = {
    "idempotency_outbox_events": "embedded_business_logic",
    "field_task_alert_helpers": "embedded_business_logic",
    "auth_jwt_permissions": "security_runtime",
    "parsers_mappers_serializers": "compatibility_runtime",
    "db_tenant_rls_bootstrap": "bootstrap_runtime",
    "misc_bootstrap_compatibility": "bootstrap_compatibility",
    "middleware_and_rate_limit": "middleware_runtime",
    "workflow_compatibility": "compatibility_runtime",
    "startup_hooks": "bootstrap_runtime",
    "shutdown_hooks": "bootstrap_runtime",
    "imports_and_module_header": "module_header",
}


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}".strip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _category(name: str, lineno: int, decorators: list[str]) -> str:
    lname = name.lower()
    decos = " ".join(decorators).lower()
    if lineno <= 75:
        return "imports_and_module_header"
    if "on_event" in decos and "startup" in decos:
        return "startup_hooks"
    if "on_event" in decos and "shutdown" in decos:
        return "shutdown_hooks"
    if "middleware" in decos or any(k in lname for k in MIDDLEWARE_NAMES):
        return "middleware_and_rate_limit"
    if any(k in lname for k in EVENT_NAMES):
        return "idempotency_outbox_events"
    if any(k in lname for k in AUTH_NAMES):
        return "auth_jwt_permissions"
    if any(k in lname for k in DB_NAMES):
        return "db_tenant_rls_bootstrap"
    if any(k in lname for k in MAPPER_NAMES):
        return "parsers_mappers_serializers"
    if any(k in lname for k in ALERT_NAMES):
        return "field_task_alert_helpers"
    if any(k in lname for k in WORKFLOW_NAMES):
        return "workflow_compatibility"
    if any(k in lname for k in STARTUP_NAMES):
        return "startup_hooks"
    if any(k in lname for k in SHUTDOWN_NAMES):
        return "shutdown_hooks"
    return "misc_bootstrap_compatibility"


def _route_decorators(decorators: list[str]) -> list[str]:
    methods = ("app.get", "app.post", "app.put", "app.patch", "app.delete", "app.api_route")
    return [d for d in decorators if d.startswith(methods)]


def inventory() -> dict:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    items = []
    direct_routes = []
    imports = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += getattr(node, "end_lineno", node.lineno) - node.lineno + 1
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decorators = [_decorator_name(d) for d in getattr(node, "decorator_list", [])]
            end = getattr(node, "end_lineno", node.lineno)
            loc = end - node.lineno + 1
            cat = _category(node.name, node.lineno, decorators)
            route_decos = _route_decorators(decorators)
            if route_decos:
                direct_routes.append(
                    {"name": node.name, "line": node.lineno, "decorators": route_decos}
                )
            items.append(
                {
                    "name": node.name,
                    "kind": type(node).__name__,
                    "line_start": node.lineno,
                    "line_end": end,
                    "loc": loc,
                    "category": cat,
                    "decorators": decorators,
                }
            )
    category_totals: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = category_totals.setdefault(item["category"], {"symbols": 0, "loc": 0})
        bucket["symbols"] += 1
        bucket["loc"] += int(item["loc"])
    result = {
        "schema_version": 1,
        "file": str(MAIN.relative_to(ROOT)),
        "total_lines": len(lines),
        "import_lines": imports,
        "top_level_symbols": len(items),
        "direct_route_decorators": len(direct_routes),
        "category_totals": category_totals,
        "category_classification": {
            cat: CATEGORY_CLASSIFICATION.get(cat, "unclassified_runtime") for cat in category_totals
        },
        "embedded_business_logic_loc": sum(
            totals["loc"]
            for cat, totals in category_totals.items()
            if CATEGORY_CLASSIFICATION.get(cat) == "embedded_business_logic"
        ),
        "categorized_symbol_loc": sum(totals["loc"] for totals in category_totals.values()),
        "uncategorized_residual_loc_estimate": max(
            0,
            len(lines) - imports - sum(totals["loc"] for totals in category_totals.values()),
        ),
        "items": items,
        "direct_routes": direct_routes,
        "recommendation": _recommendation(len(lines), category_totals, len(direct_routes)),
    }
    return result


def _recommendation(
    total_lines: int, categories: dict[str, dict[str, int]], route_count: int
) -> dict:
    recs = []
    if route_count:
        recs.append(
            "Route decorators returned to platform main.py; move them to routers before production certification."
        )
    if total_lines > 1000:
        recs.append(
            "Extract remaining bootstrap/runtime helpers into api/platform_bootstrap_runtime.py and api/platform_auth_runtime.py."
        )
    for cat, threshold in {
        "auth_jwt_permissions": 120,
        "db_tenant_rls_bootstrap": 160,
        "idempotency_outbox_events": 140,
        "field_task_alert_helpers": 220,
        "middleware_and_rate_limit": 120,
    }.items():
        if categories.get(cat, {}).get("loc", 0) > threshold:
            recs.append(
                f"Category {cat} exceeds {threshold} LOC; extract a dedicated runtime module."
            )
    embedded_business_logic = sum(
        totals["loc"]
        for cat, totals in categories.items()
        if CATEGORY_CLASSIFICATION.get(cat) == "embedded_business_logic"
    )
    status = "route_regression"
    if route_count == 0:
        status = (
            "route_free_with_embedded_business_logic"
            if embedded_business_logic
            else "bootstrap_large_but_route_free"
        )
    return {
        "status": status,
        "next_action": "P3 business-runtime extraction after production certification blockers"
        if route_count == 0
        else "P0 fix before release",
        "recommendations": recs,
    }


def _csv_rows(data: dict) -> list[dict]:
    rows = []
    for item in data["items"]:
        row = dict(item)
        row["decorators"] = " | ".join(row["decorators"])
        rows.append(row)
    return rows


_CSV_FIELDS = ["category", "name", "kind", "line_start", "line_end", "loc", "decorators"]


def artifacts(data: dict) -> list[Artifact]:
    """المصنوعات الثلاث التي يملكها هذا الحارس — كلّها، لا الـJSON وحدها."""
    return [
        Artifact(JSON_PATH, render_json(data)),
        Artifact(CSV_PATH, render_csv(_csv_rows(data), _CSV_FIELDS)),
        Artifact(REPORT_PATH, _report(data)),
    ]


def write_files() -> None:
    write_all(artifacts(inventory()))


def _report(data: dict) -> str:
    lines = [
        "# sahool-platform/api/main.py Sub-Inventory",
        "",
        "## Summary",
        "",
        f"- File: `{data['file']}`",
        f"- Total lines: `{data['total_lines']}`",
        f"- Import lines: `{data['import_lines']}`",
        f"- Top-level symbols: `{data['top_level_symbols']}`",
        f"- Direct route decorators: `{data['direct_route_decorators']}`",
        f"- Status: `{data['recommendation']['status']}`",
        "",
        "## Category totals",
        "",
        "| Category | Classification | Symbols | LOC |",
        "|---|---|---:|---:|",
    ]
    for cat, totals in sorted(
        data["category_totals"].items(), key=lambda kv: kv[1]["loc"], reverse=True
    ):
        cls = data.get("category_classification", {}).get(cat, "unclassified_runtime")
        lines.append(f"| `{cat}` | `{cls}` | {totals['symbols']} | {totals['loc']} |")
    lines.extend(
        [
            "",
            "## Business-logic note",
            "",
            f"- Embedded business logic still present in platform main: `{data.get('embedded_business_logic_loc', 0)}` LOC.",
            "- This does not reopen P1 because direct routes remain zero, but it makes P3 a real runtime extraction, not a cosmetic cleanup.",
            f"- Uncategorized/residual line estimate after imports and categorized symbols: `{data.get('uncategorized_residual_loc_estimate', 0)}` LOC. This must be reviewed before any P3 extraction plan is finalized.",
            "",
            "## Largest top-level symbols",
            "",
            "| Symbol | Category | Classification | LOC | Lines |",
            "|---|---|---|---:|---|",
        ]
    )
    for item in sorted(data["items"], key=lambda x: x["loc"], reverse=True)[:20]:
        cls = data.get("category_classification", {}).get(item["category"], "unclassified_runtime")
        lines.append(
            f"| `{item['name']}` | `{item['category']}` | `{cls}` | {item['loc']} | {item['line_start']}-{item['line_end']} |"
        )
    lines.extend(["", "## Recommendations", ""])
    for rec in data["recommendation"]["recommendations"]:
        lines.append(f"- {rec}")
    if not data["recommendation"]["recommendations"]:
        lines.append("- No extraction recommendation from current thresholds.")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "The platform main file is route-free after P1, but it still embeds event/outbox and field-alert business runtime. Treat further extraction as P3 business-runtime extraction, not as bootstrap cleanup, and do not begin it until the production certification blockers are closed.",
            "",
        ]
    )
    return "\n".join(lines)


def check_files() -> None:
    # كان يقارن الـJSON وحده، ويكتفي بـ`exists()` للـCSV والتقرير — أي أنّ إفساد
    # محتواهما يمرّ أخضر. الثلاثة تُقارَن الآن بمحتواها.
    data = inventory()
    enforce(artifacts(data), write=False, label="platform main subinventory")
    if data["direct_route_decorators"] != 0:
        raise SystemExit("platform main.py has direct route decorators after P1")
    if (
        data.get("category_classification", {}).get("idempotency_outbox_events")
        != "embedded_business_logic"
    ):
        raise SystemExit("idempotency_outbox_events must be classified as embedded_business_logic")
    if (
        data.get("category_classification", {}).get("field_task_alert_helpers")
        != "embedded_business_logic"
    ):
        raise SystemExit("field_task_alert_helpers must be classified as embedded_business_logic")
    print("platform_main_subinventory_check_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_files()
    if args.check or not args.write:
        check_files()


if __name__ == "__main__":
    main()
