"""Regression guard: every tenant-scoped fields query passes BOTH bind args.

The bug (found live via a 503 on the field PATCH / edit-geometry path): three `fetchrow`
calls in the version-conflict branch used the SQL
``... WHERE field_id = $1 AND tenant_id = $2::uuid`` but passed only ``field_id`` — asyncpg
then raises "the server expects 2 arguments for this query, 1 was passed", which the handler maps
to a 503. A tenant-scoped query that silently drops its tenant bind is both a crash AND a
tenant-isolation hazard, so this guard fails CI the moment any such call omits the second arg.

Static (no DB, no network): parses fields.py, and for every call whose SQL references
``tenant_id = $2`` asserts the argument list also passes a ``tenant_id`` value before the call
closes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FIELDS = (
    Path(__file__).resolve().parents[1] / "api" / "routers" / "fields.py"
).read_text(encoding="utf-8")


def test_every_tenant_scoped_query_passes_the_tenant_arg():
    lines = FIELDS.splitlines()
    offenders: list[int] = []
    for i, line in enumerate(lines):
        if "tenant_id = $2" not in line:
            continue
        # scan the argument lines up to the call's closing paren
        args_before_close = []
        for nxt in lines[i + 1 : i + 8]:
            head = nxt.split(")")[0]
            args_before_close.append(head)
            if ")" in nxt:
                break
        seg = "\n".join(args_before_close)
        # the call must bind a tenant value ($2), not just field_id ($1)
        if "field_id" in seg and "tenant_id" not in seg:
            offenders.append(i + 1)  # 1-indexed line of the SQL
    assert not offenders, (
        f"tenant-scoped fields.py queries drop the $2 tenant bind at line(s) {offenders}: "
        "the SQL references `tenant_id = $2` but the call passes only field_id — asyncpg raises "
        "(→ 503) and tenant isolation is bypassed. Pass str(user.tenant_id) as the second arg."
    )
