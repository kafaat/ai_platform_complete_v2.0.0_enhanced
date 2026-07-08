"""INTERIM decision-loop write-path guard (rescoped from the P4.5 facade-only contract).

Chosen interim architecture (temporary bridge, NOT the final state): sahool-platform is
the temporary Source of Record for the decision loop tables.  Each converted write path
therefore has a DUAL shape:

  1. it performs the AUTHORITATIVE platform DB write (``tenant_connection`` +
     ``INSERT INTO <loop_table>`` [+ ``_emit_domain_event`` where the pre-extraction code
     emitted one]) — this must succeed before the request returns success; and
  2. it BEST-EFFORT mirrors to decision-service via the ``decision_service_client`` facade,
     through a wrapper that never raises into the request path.

decision-service is explicitly NOT yet the system-of-record.  This guard replaces the old
"must not touch tenant_connection / must not INSERT" assertions, which are intentionally
false during the bridge, with the honest interim dual-path invariant.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _body(path: str, marker: str, next_marker: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    start = text.index(marker)
    end = text.index(next_marker, start)
    return text[start:end]


def test_decision_record_write_path_is_authoritative_then_mirrors() -> None:
    body = _body(
        "api/routers/decision_record.py",
        '@router.post("/api/v1/decision/record")',
        "\n\nclass OutcomePlannedIn",
    )
    # Authoritative platform write (temporary SoR).
    assert "tenant_connection" in body
    assert "INSERT INTO decision_record" in body
    assert "_emit_domain_event" in body
    # Best-effort, non-authoritative mirror.
    assert "_mirror_to_decision_service" in body
    assert "_mirror_decision_to_service" in body


def test_outcome_record_write_path_is_authoritative_then_mirrors() -> None:
    body = _body(
        "api/routers/decision_record.py",
        '@router.post("/api/v1/outcome/record")',
        '\n\n@router.get("/api/v1/decision/{decision_id}/lineage")',
    )
    assert "tenant_connection" in body
    assert "INSERT INTO outcome_record" in body
    assert "_emit_domain_event" in body
    assert "_mirror_to_decision_service" in body
    assert "_mirror_outcome_to_service" in body


def test_dispatch_execute_write_path_is_authoritative_then_mirrors() -> None:
    body = _body(
        "api/routers/decision_dispatch.py",
        '@router.post("/api/v1/decision/dispatch/execute")',
        '\n\n@router.post("/api/v1/decision/dispatch/consume")',
    )
    assert "tenant_connection" in body
    assert "INSERT INTO dispatch_decisions" in body
    assert "_emit_domain_event" in body
    assert "_mirror_dispatch_to_service" in body


def test_recommendation_outcomes_write_path_is_authoritative_then_mirrors() -> None:
    body = _body(
        "api/routers/recommendations.py",
        '@router.post("/api/v1/recommendations/outcomes", status_code=201)',
        "\n\n# مُسجَّل أخيراً عمداً:",
    )
    assert "tenant_connection" in body
    assert "INSERT INTO recommendation_outcomes" in body
    assert "_mirror_recommendation_outcome_to_service" in body


def test_mirror_failure_can_never_raise_into_the_request_path() -> None:
    """Every mirror call site swallows exceptions (best-effort); no request fails on mirror."""
    # Shared helper in decision_record.py wraps the facade call in try/except + logger.warning.
    dr = (ROOT / "api/routers/decision_record.py").read_text(encoding="utf-8")
    start = dr.index("async def _mirror_to_decision_service")
    helper = dr[start : start + 900]
    assert "try:" in helper
    assert "except Exception" in helper
    assert "logger.warning" in helper
    # Dispatch / recommendations / phase-runtime / weather mirror at their own call sites,
    # each wrapped in try/except so a mirror failure is logged, never raised.  Anchor on the
    # awaited CALL (not the import) and use a generous window around it.
    for rel, needle in [
        ("api/routers/decision_dispatch.py", "await _mirror_dispatch_to_service("),
        ("api/routers/recommendations.py", "await _mirror_recommendation_outcome_to_service("),
        ("api/phase_runtime_store.py", "await _mirror_learning_update_to_service("),
        ("api/routers/weather.py", "await _mirror_decision_to_service("),
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        idx = text.index(needle)
        window = text[max(0, idx - 1400) : idx + 1400]
        assert "try:" in window and "except Exception" in window, rel


def test_decision_service_client_exposes_mirror_facade_functions() -> None:
    text = (ROOT / "api/decision_service_client.py").read_text(encoding="utf-8")
    for name in [
        "record_decision",
        "record_dispatch_decision",
        "record_outcome",
        "record_recommendation_outcome",
        "record_learning_update",
    ]:
        assert f"async def {name}" in text
    assert "DEFAULT_DECISION_SERVICE_URL" in text
    assert "X-Agent-Token" in text
    assert "X-Tenant-Id" in text
