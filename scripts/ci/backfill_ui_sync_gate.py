#!/usr/bin/env python3
"""Static contract gate for historical imagery backfill UI/runtime synchronization.

Checks that:
- The platform exposes a tenant-scoped GET status proxy for run_id.
- The frontend API client calls the platform proxy, not raster-service directly.
- MapHub polls run status and refreshes available-dates/timeline after async runs.
- Imagery automation writes set app.current_tenant before RLS-protected INSERT/UPDATE.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        print(f"❌ missing required file: {path}")
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        print(f"❌ missing {label}: {needle}")
        sys.exit(1)


def main() -> int:
    api = read("frontend/src/services/api.ts")
    maphub = read("frontend/src/sections/MapHub.tsx")
    fields = read("services/sahool-platform/api/routers/fields.py")
    auto = read("services/sahool-platform/api/imagery_automation.py")

    require(api, "fetchHistoricalImageryBackfillStatus", "frontend status API")
    require(
        api, "/api/v1/fields/${fieldId}/imagery/backfill/${runId}", "platform status endpoint URL"
    )
    require(api, "isTerminalBackfillStatus", "terminal status helper")

    require(maphub, "fetchHistoricalImageryBackfillStatus", "MapHub polling import/use")
    require(maphub, "refreshImageryTimeline", "MapHub timeline refresh callback")
    require(maphub, "isTerminalBackfillStatus(lastStatus)", "terminal-state polling stop")
    require(maphub, "await refreshImageryTimeline()", "timeline refresh after polling")

    require(
        fields,
        '@router.get("/api/v1/fields/{field_id}/imagery/backfill/{run_id}")',
        "platform GET proxy route",
    )
    require(fields, "X-Agent-Token", "service token injection")
    require(fields, "X-Tenant-Id", "tenant header injection")
    require(fields, "SELECT 1 FROM fields WHERE field_id", "tenant-owned field check")

    require(auto, "_set_tenant_context_if_any", "automation RLS tenant helper")
    require(auto, "set_config('app.current_tenant'", "RLS current tenant setting")
    require(auto, "async with conn.transaction()", "transaction-local tenant setting")

    print("backfill-ui-sync contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
