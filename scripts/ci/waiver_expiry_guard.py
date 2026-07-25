#!/usr/bin/env python3
"""WAIVER-EXPIRY-GUARD — fail CI once a governance waiver has expired.

An ``expiry`` date inside a waiver JSON is inert unless CI actually rejects it once
past — otherwise a temporary exemption silently becomes permanent. This guard scans the
governance waiver config(s) and fails when:

- a waiver's ``expiry`` (``YYYY-MM-DD``) is **before today**, or
- a waiver marked ``temporary: true`` carries **no** ``expiry`` (a temporary waiver
  without an expiry is a latent permanent one), or
- an ``expiry`` value is malformed.

Waivers without ``expiry`` and without ``temporary: true`` are ignored (permanent by
design, e.g. admin-ops routes with no user-facing screen). The guard uses the real
current date at CI time, so an expired waiver forces a deliberate renewal or removal of
the underlying gap.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Governance waiver files carrying temporary/expiry semantics. Add new files here as
# other subsystems adopt time-boxed waivers.
WAIVER_FILES = (
    ROOT / "config" / "endpoint_ui_coverage_waivers.json",
    ROOT / "config" / "security_exceptions.json",
)


def _iter_waivers(data: object):
    """Yield waiver dicts from either ``{"waivers": [...]}`` or a bare list."""
    if isinstance(data, dict):
        yield from (w for w in data.get("waivers", []) if isinstance(w, dict))
    elif isinstance(data, list):
        yield from (w for w in data if isinstance(w, dict))


def check_waivers(entries: list, *, today: _dt.date) -> list[str]:
    """Return a list of problems (empty ⇒ OK). Pure/deterministic given ``today``."""
    problems: list[str] = []
    for w in entries:
        if not isinstance(w, dict):
            continue
        label = w.get("endpoint") or w.get("id") or "<unknown-waiver>"
        if w.get("temporary") is True:
            required_fields = ("owner", "reason", "scope") if w.get("id") else ("owner", "reason")
            for field in required_fields:
                if not w.get(field):
                    problems.append(f"{label}: temporary waiver missing required field {field}")
        expiry = w.get("expiry")
        if expiry in (None, ""):
            if w.get("temporary") is True:
                problems.append(f"{label}: temporary waiver has no expiry (would be permanent)")
            continue
        try:
            exp = _dt.date.fromisoformat(str(expiry))
        except ValueError:
            problems.append(f"{label}: malformed expiry {expiry!r} (want YYYY-MM-DD)")
            continue
        if exp < today:
            owner = w.get("owner") or w.get("tracking") or w.get("reason_category") or "?"
            problems.append(
                f"{label}: waiver expired {exp.isoformat()} "
                f"(owner={owner}, today={today.isoformat()}) — "
                "resolve the tracked gap or renew the waiver deliberately"
            )
    return problems


def main() -> int:
    today = _dt.date.today()
    problems: list[str] = []
    scanned = 0
    for f in WAIVER_FILES:
        if not f.exists():
            continue
        scanned += 1
        data = json.loads(f.read_text(encoding="utf-8"))
        for p in check_waivers(list(_iter_waivers(data)), today=today):
            problems.append(f"{f.relative_to(ROOT)}: {p}")
    if problems:
        print("waiver_expiry_guard_failed")
        print("\n".join(problems))
        return 1
    print(f"waiver_expiry_guard_ok (scanned {scanned} waiver file(s); today={today.isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
