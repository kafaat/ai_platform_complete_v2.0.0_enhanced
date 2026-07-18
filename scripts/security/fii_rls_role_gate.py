#!/usr/bin/env python3
"""Static ratchet for the FII runtime DB-role boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPLY = ROOT / "migrations" / "apply_in_compose.sh"
BOOTSTRAP = ROOT / "migrations" / "bootstrap_postgres.sh"


def main() -> int:
    failures: list[str] = []
    apply = APPLY.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    for name, text in (("apply_in_compose.sh", apply), ("bootstrap_postgres.sh", bootstrap)):
        if "NOBYPASSRLS" not in text:
            failures.append(f"{name}: sahool_app is not pinned to NOBYPASSRLS")
        if "NOCREATEROLE" not in text:
            failures.append(f"{name}: sahool_app is not pinned to NOCREATEROLE")
    if 'REVOKE CREATE ON SCHEMA public FROM :"app_role";' not in apply:
        failures.append("apply_in_compose.sh: runtime CREATE is not revoked by default")
    if 'APP_ALLOW_SCHEMA_CREATE="${APP_ALLOW_SCHEMA_CREATE:-false}"' not in apply:
        failures.append("apply_in_compose.sh: legacy CREATE exception is not explicit/default-off")
    if "APP_ALLOW_SCHEMA_CREATE=true" not in apply:
        failures.append("apply_in_compose.sh: legacy CREATE exception lacks an audit warning")
    if failures:
        print("FII DB role gate FAILED")
        print("\n".join(f"- {x}" for x in failures))
        return 1
    print("FII DB role gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
