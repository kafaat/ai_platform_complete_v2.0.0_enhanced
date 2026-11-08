"""Device telemetry time and identity — one timestamp, tolerated skew, stable retry keys.

Faults closed here (review R01, 2026-11-08):

* F8 — a device clock ~1 s fast got a raw ``201`` while soil-service refused the forwarded
  observation (``received_at < observed_at`` with no tolerance). The contract now tolerates
  ``OBSERVATION_CLOCK_SKEW_TOLERANCE_S``; the platform edge refuses beyond half of it with
  422 so a reading is never accepted raw and then refused by the owner.
* F9 — without ``recorded_at`` the raw row took the DB ``NOW()`` and the observation took
  Python ``now()``; and every retry minted a new idempotency key. One server timestamp is
  resolved once; an optional device ``message_id`` keys the server-timed reading.
* F12 — any accepted reading, even a backdated one, marked the device online.
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
for path in (CORE, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
DEVICES_ROUTER = os.path.join(CORE, "api/routers/devices.py")


def _common(**over):
    base = dict(
        tenant_id="t",
        field_id="f",
        device_id="d",
        property_name="soil_moisture",
        value=21.5,
        unit="vwc_pct",
        observed_at=NOW,
    )
    base.update(over)
    return base


# ─── F8: tolerated clock skew ─────────────────────────────────────────────


def test_the_contract_tolerates_a_small_device_clock_lead_and_refuses_a_large_one():
    from pydantic import ValidationError

    from shared.contracts.soil import SoilObservation
    from shared.contracts.soil.observation import OBSERVATION_CLOCK_SKEW_TOLERANCE_S

    body = dict(
        tenant_id="t",
        field_id="f",
        property="soil_moisture",
        value=21.5,
        unit="vwc_pct",
        source_type="sensor",
        idempotency_key="k",
        received_at=NOW,
    )
    for lead in (1, OBSERVATION_CLOCK_SKEW_TOLERANCE_S):
        SoilObservation(**body, observed_at=NOW + timedelta(seconds=lead))
    with pytest.raises(ValidationError, match="received_before_observed"):
        SoilObservation(
            **body, observed_at=NOW + timedelta(seconds=OBSERVATION_CLOCK_SKEW_TOLERANCE_S + 1)
        )


def test_the_edge_tolerance_leaves_headroom_inside_the_contract_tolerance():
    from api.device_models import DEVICE_CLOCK_SKEW_TOLERANCE_S

    from shared.contracts.soil.observation import OBSERVATION_CLOCK_SKEW_TOLERANCE_S

    assert 0 < DEVICE_CLOCK_SKEW_TOLERANCE_S < OBSERVATION_CLOCK_SKEW_TOLERANCE_S


def test_a_reading_one_second_ahead_is_accepted_flagged_and_reaches_the_contract():
    from api.device_models import resolve_recorded_at
    from api.soil_evidence_bridge import build_observation

    from shared.contracts.soil import SoilObservation

    ahead = NOW + timedelta(seconds=1)
    recorded, declared, skew_s = resolve_recorded_at(ahead.isoformat(), NOW)
    assert (recorded, declared, skew_s) == (ahead, True, 1.0)
    body = build_observation(**_common(observed_at=recorded), quality_flags=["device_clock_skew"])
    # The owner stamps received_at at (or slightly after) the platform's clock.
    obs = SoilObservation.model_validate({**body, "received_at": NOW})
    assert obs.quality_flags == ["device_clock_skew"]
    assert obs.observed_at == ahead  # declared, not rewritten: retries keep one identity


def test_the_largest_edge_accepted_lead_still_passes_the_contract():
    from api.device_models import DEVICE_CLOCK_SKEW_TOLERANCE_S, resolve_recorded_at
    from api.soil_evidence_bridge import build_observation

    from shared.contracts.soil import SoilObservation

    ahead = NOW + timedelta(seconds=DEVICE_CLOCK_SKEW_TOLERANCE_S)
    recorded, _declared, _skew = resolve_recorded_at(ahead.isoformat(), NOW)
    SoilObservation.model_validate(
        {**build_observation(**_common(observed_at=recorded)), "received_at": NOW}
    )


def test_a_reading_beyond_the_edge_tolerance_is_refused_with_422():
    from api.device_models import (
        DEVICE_CLOCK_SKEW_TOLERANCE_S,
        TelemetryTimeRejected,
        resolve_recorded_at,
    )

    ahead = NOW + timedelta(seconds=DEVICE_CLOCK_SKEW_TOLERANCE_S + 1)
    with pytest.raises(TelemetryTimeRejected) as info:
        resolve_recorded_at(ahead.isoformat(), NOW)
    assert info.value.status_code == 422


def test_invalid_naive_and_zulu_recorded_at_keep_their_previous_handling():
    from api.device_models import TelemetryTimeRejected, resolve_recorded_at

    with pytest.raises(TelemetryTimeRejected) as info:
        resolve_recorded_at("not-a-date", NOW)
    assert info.value.status_code == 400
    past = NOW - timedelta(hours=1)
    assert resolve_recorded_at("2026-11-08T11:00:00", NOW) == (past, True, 0.0)
    assert resolve_recorded_at("2026-11-08T11:00:00Z", NOW) == (past, True, 0.0)


# ─── F9: one server timestamp, stable retry keys ──────────────────────────


def test_an_absent_recorded_at_resolves_to_the_one_server_timestamp():
    from api.device_models import resolve_recorded_at

    assert resolve_recorded_at(None, NOW) == (NOW, False, 0.0)
    assert resolve_recorded_at("", NOW) == (NOW, False, 0.0)


def test_the_router_resolves_time_once_for_the_raw_row_and_the_forwarded_observation():
    """No DB ``NOW()`` for the raw row and no second ``datetime.now`` for the observation."""
    tree = ast.parse(open(DEVICES_ROUTER, encoding="utf-8").read())
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    ingest = ast.get_source_segment(
        open(DEVICES_ROUTER, encoding="utf-8").read(), funcs["ingest_telemetry"]
    )
    forward = ast.unparse(funcs["_forward_agronomic_reading"])
    insert = ingest[ingest.index("INSERT INTO device_telemetry") :]
    insert = insert[: insert.index('"""')]
    assert "NOW()" not in insert, "raw row still takes its own clock"
    assert ingest.count("datetime.now(") == 1
    assert "datetime.now" not in forward, "forwarded observation still takes its own clock"
    assert "resolve_recorded_at(req.recorded_at, now)" in ingest


def test_message_id_keys_a_server_timed_reading_across_retries():
    from api.soil_evidence_bridge import build_observation

    first = build_observation(
        **_common(observed_at=NOW), message_id="m-1", observed_at_declared=False
    )
    retry = build_observation(
        **_common(observed_at=NOW + timedelta(seconds=7)),
        message_id="m-1",
        observed_at_declared=False,
    )
    other = build_observation(
        **_common(observed_at=NOW), message_id="m-2", observed_at_declared=False
    )
    assert first["idempotency_key"] == retry["idempotency_key"]
    assert first["idempotency_key"] != other["idempotency_key"]
    assert first["provenance"]["message_id"] == "m-1"
    assert first["provenance"]["observed_at_source"] == "server_receipt"


def test_without_message_id_the_key_is_unchanged_backward_compatible():
    from api.soil_evidence_bridge import build_observation, idempotency_key

    plain = idempotency_key(device_id="d", property_name="soil_moisture", observed_at=NOW)
    assert build_observation(**_common())["idempotency_key"] == plain
    assert build_observation(**_common(), observed_at_declared=False)["idempotency_key"] == plain


def test_a_declared_time_keeps_the_time_key_even_with_message_id():
    """Backfill parity: ``device_telemetry`` stores the time, never the message id."""
    from api.soil_evidence_bridge import build_observation, idempotency_key

    plain = idempotency_key(device_id="d", property_name="soil_moisture", observed_at=NOW)
    body = build_observation(**_common(), message_id="m-1")
    assert body["idempotency_key"] == plain
    assert body["provenance"]["message_id"] == "m-1"
    assert "observed_at_source" not in body["provenance"]


def test_message_id_is_optional_and_bounded_in_the_request():
    from api.device_models import TelemetryRequest
    from pydantic import ValidationError

    assert TelemetryRequest(sensor_type="soil_moisture", value=1).message_id is None
    assert TelemetryRequest(sensor_type="soil_moisture", value=1, message_id="m").message_id == "m"
    for bad in ("", "x" * 129):
        with pytest.raises(ValidationError):
            TelemetryRequest(sensor_type="soil_moisture", value=1, message_id=bad)


# ─── F12: a backdated reading is not a heartbeat ──────────────────────────


def test_the_online_update_is_gated_by_the_online_window_freshness():
    src = open(DEVICES_ROUTER, encoding="utf-8").read()
    tree = ast.parse(src)
    ingest = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "ingest_telemetry"
    )
    guarded = [
        node
        for node in ast.walk(ingest)
        if isinstance(node, ast.If)
        and "telemetry_freshness(recorded, now, _DEVICE_ONLINE_WINDOW_MIN)"
        in ast.unparse(node.test)
    ]
    assert guarded, "online update is not gated by the freshness window"
    assert "status = 'online'" in ast.unparse(guarded[0])
    # And it is the only place the heartbeat is written.
    assert ast.unparse(ingest).count("status = 'online'") == 1


def test_backdated_stale_and_slightly_future_readings_classify_as_expected():
    from api.device_models import (
        _DEVICE_ONLINE_WINDOW_MIN,
        DEVICE_CLOCK_SKEW_TOLERANCE_S,
        telemetry_freshness,
    )

    window = timedelta(minutes=_DEVICE_ONLINE_WINDOW_MIN)
    assert telemetry_freshness(NOW - 2 * window, NOW)["stale"] is True
    assert telemetry_freshness(NOW - window, NOW)["stale"] is False
    assert telemetry_freshness(NOW, NOW)["stale"] is False
    ahead = NOW + timedelta(seconds=DEVICE_CLOCK_SKEW_TOLERANCE_S)
    assert telemetry_freshness(ahead, NOW)["stale"] is False
