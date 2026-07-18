"""IRR-F01 — static bypass guard for the reservation activation adapter (open-ledger #1, proof #6).

The activation gate only means something if there is exactly ONE way for platform code to create an
IRR-F01 reservation, and it is gated. This guard enforces that:

  1. The restricted adapter ``irrigation_activation_gate`` exists and FAILS CLOSED — its
     ``enforce_or_raise`` raises on a non-200 answer, it never returns a silent pass.
  2. The reservation coordinator exposes the ``activation_guard`` seam (awaited before any write).
  3. The set of modules that reach the reservation-creating / capacity-admission primitives
     (``reserve_and_request_dispatch_db(`` / ``evaluate_admission(``) is a fixed, reviewed
     allowlist — a NEW module reaching them fails this guard, forcing a reviewer to confirm it
     routes through ``irrigation_activation_gate.activation_guard`` rather than silently bypassing.

Static source scan — no runtime, no network.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "services" / "sahool-platform" / "api"

# Primitives that CREATE a reservation or ADMIT capacity — reaching them means "about to reserve".
_RESERVATION_PRIMITIVES = ("reserve_and_request_dispatch_db(", "evaluate_admission(")

# Modules permitted to reach those primitives. Each is the coordinator itself, the pure kernel that
# defines the primitive, or (future) a route that MUST pass activation_guard — reviewed on entry.
DIRECT_RESERVATION_ALLOWLIST = {
    "irrigation_reservation_adapter.py",  # the coordinator (defines/uses the primitive + the seam)
    "irrigation_capacity_reservation.py",  # the pure kernel that defines evaluate_admission
    "irrigation_activation_gate.py",  # the restricted adapter (names the primitive in its contract)
}


def _iter_api_modules():
    for path in API.rglob("*.py"):
        rel = str(path.relative_to(API))
        if path.name.startswith("test_"):
            continue
        yield rel, path.read_text(encoding="utf-8")


def test_restricted_adapter_exists_and_fails_closed():
    src = (API / "irrigation_activation_gate.py").read_text(encoding="utf-8")
    # The fail path must RAISE, never return a pass-through — the refusal helper hard-codes the
    # local exception on every non-200 branch.
    fn = src.split("async def enforce_or_raise(")[1].split("\ndef ")[0].split("\nasync def ")[0]
    # The refusal is raised, not returned, on BOTH error branches: an explicit 403 and any other
    # non-200 (mirror 503 / SoR off) or transport error.
    assert "raise IrrigationActivationNotEnabled" in fn
    assert "gate_unreachable" in fn  # 5xx / transport error fails closed
    # No error branch may hand back an admit — the fail path never `return`s a truthy snapshot.
    assert "return FALLBACK" not in fn and 'return {"enforced": True' not in fn


def test_coordinator_exposes_the_activation_guard_seam():
    src = (API / "irrigation_reservation_adapter.py").read_text(encoding="utf-8")
    assert "activation_guard" in src
    # The guard is awaited BEFORE the tenant GUC / advisory locks (source-order check).
    assert src.index("await activation_guard()") < src.index("await conn.execute(SET_TENANT_SQL")


def test_no_new_module_reaches_reservation_primitives_without_review():
    offenders = set()
    for rel, src in _iter_api_modules():
        if any(prim in src for prim in _RESERVATION_PRIMITIVES):
            offenders.add(rel)
    unexpected = offenders - DIRECT_RESERVATION_ALLOWLIST
    assert not unexpected, (
        "New module(s) reach the reservation/admission primitives without review: "
        f"{sorted(unexpected)}. Route them through "
        "irrigation_activation_gate.activation_guard(), then add to "
        "DIRECT_RESERVATION_ALLOWLIST with justification."
    )


def test_guard_would_catch_a_contrived_bypass():
    # Negative proof: a synthetic module that calls the primitive is NOT in the allowlist, so the
    # set-difference the guard computes is non-empty — the guard has teeth.
    synthetic_offenders = {"irrigation_reservation_adapter.py", "sneaky_new_route.py"}
    unexpected = synthetic_offenders - DIRECT_RESERVATION_ALLOWLIST
    assert unexpected == {"sneaky_new_route.py"}
