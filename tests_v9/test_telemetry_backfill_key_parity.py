"""Backfill and live bridge give a device reading the same idempotency key (review R01 F10).

``scripts/soil/reconcile_historical.py`` keyed device_telemetry rows as
``device_telemetry:<id>:<prop>`` while the live platform bridge keys the same reading by
(device, property, observed_at). Running the backfill after live ingestion therefore wrote
every forwarded reading a second time. The script mirrors the bridge's key (it must not
import the platform package); this file pins the mirror to the original.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "services/sahool-platform"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))
SCRIPT = ROOT / "scripts/soil/reconcile_historical.py"

pytestmark = pytest.mark.unit


def _mirror():
    """Run the script's own function, extracted from its syntax tree (no asyncpg import)."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "live_bridge_idempotency_key"
    )
    namespace: dict = {"hashlib": hashlib, "UTC": UTC}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SCRIPT), "exec"), namespace)  # noqa: S102
    return namespace["live_bridge_idempotency_key"]


@pytest.mark.parametrize(
    "observed_at",
    [
        datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
        datetime(2026, 11, 8, 12, 0, 0, 123456, tzinfo=UTC),
        datetime(2026, 11, 8, 15, 0, tzinfo=timezone(timedelta(hours=3))),
    ],
)
def test_backfill_key_equals_the_live_bridge_key_for_a_depthless_reading(observed_at):
    from api.soil_evidence_bridge import build_observation, idempotency_key

    mirror = _mirror()
    live = idempotency_key(
        device_id="dev_1", property_name="soil_moisture", observed_at=observed_at
    )
    assert mirror("dev_1", "soil_moisture", observed_at) == live
    body = build_observation(
        tenant_id="t",
        field_id="f",
        device_id="dev_1",
        property_name="soil_moisture",
        value=21.0,
        unit="%",
        observed_at=observed_at,
    )
    assert body["idempotency_key"] == live


def test_the_backfill_insert_uses_the_mirrored_key_not_the_legacy_row_identity():
    src = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_process_telemetry_row"
    )
    body = ast.unparse(func)
    assert "live_bridge_idempotency_key(row['device_id'], prop, row['recorded_at'])" in body
    assert "device_telemetry:{row" not in body
    # A re-run over rows written under the old key must not trip the observation_id key.
    assert "ON CONFLICT DO NOTHING" in " ".join(body.split())


def test_the_mirror_does_not_drift_when_the_bridge_key_changes_shape():
    """Control: different device, property or time give different keys in both."""
    from api.soil_evidence_bridge import idempotency_key

    mirror = _mirror()
    moment = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    variants = [
        ("dev_1", "soil_moisture", moment),
        ("dev_2", "soil_moisture", moment),
        ("dev_1", "soil_temperature", moment),
        ("dev_1", "soil_moisture", moment + timedelta(seconds=1)),
    ]
    keys = {mirror(*v) for v in variants}
    assert len(keys) == len(variants)
    assert keys == {
        idempotency_key(device_id=d, property_name=p, observed_at=t) for d, p, t in variants
    }
