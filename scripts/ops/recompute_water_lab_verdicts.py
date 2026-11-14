"""Operator CLI: recompute stored irrigation-water lab verdicts with the current analysis.

Owner decision 2026-11-14. ``analyze_water_sample`` gained the FAO-29 three-tier verdict
(``suitable`` / ``suitable_with_restrictions`` / ``needs_treatment``) after water lab results
were already stored in ``water_lab_result_sets.analysis``. This command recomputes the analysis
of each live stored set from its stored measurement (``payload``) and keeps the old one.

History is a v258 revision, never an overwrite: the recomputed analysis is a new row that names
the row it replaces (``supersedes_result_set_id``), with ``correction_reason`` set to
``RECOMPUTE-FAO29-TIER`` and ``previous_verdict`` / ``previous_result_id`` / ``recomputed_at`` /
``recompute_reason`` inside its analysis. The replaced row becomes ``superseded`` and keeps its
analysis, approval and publication stamps. The measurement is unchanged, so the revision carries
the replaced row's payload, review state, approval and publication stamps, author
(``entered_by``) and ``request_digest`` (a client retry of the original measurement still
returns the current row). It adds no custody event: the reviewers' separation of duties is
unchanged.

Not recomputed (reported, never touched):
- superseded and rejected rows: they are history;
- an unreviewed correction (an unreviewed row that itself supersedes another): rejecting a
  revision of it could not restore the approved set it corrects, so it is recomputed by a re-run
  after its review;
- a row whose stored inputs no longer pass the analysis' input checks.

Safety:
- dry run by default; ``--apply`` writes. A dry run runs in a READ ONLY transaction;
- tenant-scoped: every tenant runs in its own transaction with ``app.current_tenant`` set, as
  ``api.main.tenant_connection`` does, and every statement also filters on ``tenant_id``.
  Connect as the application role (NOBYPASSRLS) so row-level security applies as well;
- the reads and writes are the owner's (``api.lab_store.live_water_sets`` and
  ``append_water_analysis_revision``): each write locks the sample row first (the order
  ``record_water_result`` uses), then re-reads the set, so a concurrent submit or review is not
  overwritten;
- idempotent: a set whose stored analysis already equals the recomputation is left alone, so a
  re-run changes nothing.

Usage (never against a database you were not asked to change)::

    DATABASE_URL=postgresql://app_role@host/db \\
      python scripts/ops/recompute_water_lab_verdicts.py --tenant <uuid> [--tenant <uuid>] [--apply]
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from collections import Counter
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

REASON = "RECOMPUTE-FAO29-TIER"
RECOMPUTE_KEYS = ("previous_verdict", "previous_result_id", "recomputed_at", "recompute_reason")

UNCHANGED = "unchanged"
REVISE = "revise"
SKIP_UNREVIEWED_CORRECTION = "skip:unreviewed_correction"
SKIP_INVALID_INPUTS = "skip:invalid_stored_inputs"
SKIP_CHANGED = "skip:changed_concurrently"

_PLATFORM = Path(__file__).resolve().parents[2] / "services" / "sahool-platform"


def _platform_module(name: str):
    """A module of the platform, which owns water_lab_result_sets and its analysis."""
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    return importlib.import_module(name)


def _json(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value)


def recompute(payload: dict[str, Any], sample_id: str) -> dict[str, Any]:
    """The current analysis of a stored measurement, in its stored (JSON) form."""
    water = _platform_module("core.irrigation_water_analysis")
    names = {f.name for f in fields(water.WaterSample)}
    values = {k: v for k, v in payload.items() if k in names}
    values.setdefault("sample_id", sample_id)
    analysis = water.analyze_water_sample(water.WaterSample(**values))
    return json.loads(json.dumps(analysis, allow_nan=False))


def _derived(analysis: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in analysis.items() if k not in RECOMPUTE_KEYS}


def plan(row: Any) -> dict[str, Any]:
    """What a live stored set needs: unchanged, a revision, or a reported skip."""
    stored = _json(row["analysis"])
    old = stored.get("verdict")
    try:
        fresh = recompute(_json(row["payload"]), row["sample_id"])
    except (TypeError, ValueError) as exc:
        return {"action": SKIP_INVALID_INPUTS, "old": old, "new": None, "error": str(exc)}
    if _derived(stored) == fresh:
        return {"action": UNCHANGED, "old": old, "new": old}
    if row["quality_status"] == "unreviewed" and row["supersedes_result_set_id"] is not None:
        return {"action": SKIP_UNREVIEWED_CORRECTION, "old": old, "new": fresh.get("verdict")}
    return {"action": REVISE, "old": old, "new": fresh.get("verdict"), "analysis": fresh}


async def _revise(conn, tenant: str, row: Any, analysis: dict[str, Any], now: datetime) -> bool:
    lab_store = _platform_module("api.lab_store")
    stored = _json(row["analysis"])
    revision = {
        **analysis,
        "previous_verdict": stored.get("verdict"),
        "previous_result_id": str(row["result_set_id"]),
        "recomputed_at": now.isoformat(),
        "recompute_reason": REASON,
    }
    written = await lab_store.append_water_analysis_revision(
        conn, tenant_id=tenant, seen=row, analysis=revision, reason=REASON
    )
    return written is not None


async def recompute_tenant(
    conn, tenant: str, *, apply: bool, now: datetime | None = None
) -> dict[str, Any]:
    """Plan (and with ``apply`` write) the recomputation of one tenant's live water sets."""
    tenant = str(UUID(tenant))
    now = now or datetime.now(UTC)
    actions: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    skipped: list[dict[str, Any]] = []
    async with conn.transaction(readonly=not apply):
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
        rows = await _platform_module("api.lab_store").live_water_sets(conn, tenant_id=tenant)
        for row in rows:
            step = plan(row)
            action = step["action"]
            if action == REVISE and apply:
                if not await _revise(conn, tenant, row, step["analysis"], now):
                    action = SKIP_CHANGED
            actions[action] += 1
            if action == REVISE:
                transitions[f"{step['old'] or 'none'} -> {step['new'] or 'none'}"] += 1
            elif action.startswith("skip:"):
                skipped.append(
                    {
                        "result_id": str(row["result_set_id"]),
                        "sample_id": row["sample_id"],
                        "reason": action,
                        **({"error": step["error"]} if "error" in step else {}),
                    }
                )
    return {
        "tenant_id": tenant,
        "mode": "apply" if apply else "dry-run",
        "live_sets": len(rows),
        "revised" if apply else "would_revise": actions[REVISE],
        "unchanged": actions[UNCHANGED],
        "verdict_transitions": dict(sorted(transitions.items())),
        "skipped": skipped,
    }


def _print(summary: dict[str, Any]) -> None:
    verb = "revised" if summary["mode"] == "apply" else "would revise"
    count = summary.get("revised", summary.get("would_revise"))
    print(
        f"[{summary['mode']}] tenant {summary['tenant_id']}: {summary['live_sets']} live set(s),"
        f" {verb} {count}, unchanged {summary['unchanged']}, skipped {len(summary['skipped'])}"
    )
    for transition, n in summary["verdict_transitions"].items():
        print(f"  {transition}: {n}")
    for skip in summary["skipped"]:
        print(f"  {skip['reason']}: {skip['result_id']} (sample {skip['sample_id']})")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tenant", action="append", required=True, help="tenant UUID (repeatable)")
    parser.add_argument(
        "--apply", action="store_true", help="write the revisions (default: dry run)"
    )
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="default: $DATABASE_URL")
    parser.add_argument("--json", action="store_true", help="print the summaries as JSON")
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("--dsn or DATABASE_URL is required")
    tenants = [str(UUID(t)) for t in args.tenant]

    import asyncpg

    conn = await asyncpg.connect(args.dsn)
    try:
        summaries = [await recompute_tenant(conn, t, apply=args.apply) for t in tenants]
    finally:
        await conn.close()
    if args.json:
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
    else:
        for summary in summaries:
            _print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
