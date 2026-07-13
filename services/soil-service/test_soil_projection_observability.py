import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import projection_observability as mod


def test_readiness_policy_green(monkeypatch):
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_LAG_SECONDS", "300")
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_DEAD_LETTER", "0")
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_EXPIRED_LEASES", "0")
    ok, reasons = mod.readiness_policy(
        {"oldest_ready_age_seconds": 10, "dead_letter": 0, "expired_leases": 0}
    )
    assert ok and reasons == []


def test_readiness_policy_fails_closed(monkeypatch):
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_LAG_SECONDS", "30")
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_DEAD_LETTER", "0")
    monkeypatch.setenv("SOIL_PROJECTION_READY_MAX_EXPIRED_LEASES", "0")
    ok, reasons = mod.readiness_policy(
        {"oldest_ready_age_seconds": 31, "dead_letter": 1, "expired_leases": 1}
    )
    assert not ok
    assert set(reasons) == {
        "projection_queue_lag",
        "projection_dead_letter_present",
        "projection_expired_leases",
    }
