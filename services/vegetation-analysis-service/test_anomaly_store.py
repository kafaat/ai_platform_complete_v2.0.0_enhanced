import pytest
from anomaly_store import AnomalyStore, InvalidTransition


def _payload():
    return {
        "anomaly_ref": "urn:sahool:anomaly:anomaly_demo",
        "tenant_id": "88ddb9f8-cf89-4398-a404-fe88ec4d4bb6",
        "field_id": "fld_demo",
        "season_id": "sea_demo",
        "signal_type": "ndvi_decline",
        "severity": "high",
    }


def test_lifecycle_and_optimistic_concurrency(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    detected = store.upsert_detected(_payload())
    assert detected["status"] == "detected"
    requested = store.transition(
        detected["anomaly_ref"],
        "verification_requested",
        expected_version=1,
        task_ref="urn:sahool:task:task_1",
    )
    assert requested["aggregate_version"] == 2
    confirmed = store.transition(detected["anomaly_ref"], "confirmed", expected_version=2)
    assert confirmed["status"] == "confirmed"
    with pytest.raises(InvalidTransition):
        store.transition(detected["anomaly_ref"], "rejected", expected_version=2)


def test_invalid_state_transition_is_blocked(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    detected = store.upsert_detected(_payload())
    with pytest.raises(InvalidTransition):
        store.transition(detected["anomaly_ref"], "confirmed", expected_version=1)


# --- SCOUTING-ANOMALY-VERIFY-RACE-ORPHAN-TASK-01: reserve verification before dispatch ------

KEY = "k" * 64


def test_a_reservation_holds_the_anomaly_until_its_task_is_attached(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    ref = store.upsert_detected(_payload())["anomaly_ref"]
    reserved = store.reserve_verification(ref, expected_version=1, idempotency_key=KEY)
    assert reserved["status"] == "verification_requested", reserved
    assert reserved["aggregate_version"] == 2, reserved
    assert reserved["task_ref"] is None, "no task exists yet"
    reservation = reserved["payload"]["verification_reservation"]
    assert reservation == {
        **reservation,
        "state": "pending",
        "prior_status": "detected",
        "idempotency_key": KEY,
        "reserved_from_version": 1,
    }, reservation
    # Nothing but the reservation's own attach/release may move the aggregate meanwhile.
    for target in ("resolved", "confirmed", "rejected", "inconclusive"):
        with pytest.raises(InvalidTransition, match="verification_reservation_pending"):
            store.transition(ref, target, expected_version=2)
    with pytest.raises(InvalidTransition, match="verification_reservation_key_mismatch"):
        store.attach_verification_task(
            ref, expected_version=2, idempotency_key="other", task_ref="urn:sahool:task:t"
        )
    attached = store.attach_verification_task(
        ref, expected_version=2, idempotency_key=KEY, task_ref="urn:sahool:task:t"
    )
    assert attached["task_ref"] == "urn:sahool:task:t", attached
    assert attached["payload"]["verification_reservation"]["state"] == "attached", attached
    assert attached["aggregate_version"] == 3, attached
    confirmed = store.transition(ref, "confirmed", expected_version=3)
    assert confirmed["status"] == "confirmed", "the normal lifecycle resumes after the attach"


def test_a_reservation_is_taken_against_the_expected_version(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    ref = store.upsert_detected(_payload())["anomaly_ref"]
    store.transition(ref, "triaged", expected_version=1)
    with pytest.raises(InvalidTransition, match="aggregate_version_conflict"):
        store.reserve_verification(ref, expected_version=1, idempotency_key=KEY)
    store.transition(ref, "resolved", expected_version=2)
    with pytest.raises(InvalidTransition, match="invalid_transition:resolved"):
        store.reserve_verification(ref, expected_version=3, idempotency_key=KEY)
    assert store.get(ref)["status"] == "resolved", "a refused reservation writes nothing"


def test_releasing_a_reservation_restores_the_prior_state(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    ref = store.upsert_detected(_payload())["anomaly_ref"]
    store.transition(ref, "triaged", expected_version=1)
    store.reserve_verification(ref, expected_version=2, idempotency_key=KEY)
    released = store.release_verification_reservation(
        ref, expected_version=3, idempotency_key=KEY, reason="task_service_rejected:422"
    )
    assert released["status"] == "triaged", released
    assert released["task_ref"] is None, released
    assert "verification_reservation" not in released["payload"], released["payload"]
    assert released["payload"]["verification_reservation_released"]["reason"] == (
        "task_service_rejected:422"
    ), released["payload"]
    resolved = store.transition(ref, "resolved", expected_version=4)
    assert resolved["status"] == "resolved", "a released anomaly is open again"
    with pytest.raises(InvalidTransition, match="verification_reservation_missing"):
        store.release_verification_reservation(
            ref, expected_version=5, idempotency_key=KEY, reason="again"
        )


def test_concurrent_reservations_have_one_winner(tmp_path):
    import threading

    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    ref = store.upsert_detected(_payload())["anomaly_ref"]
    outcomes, barrier = [], threading.Barrier(5)

    def reserve():
        other = AnomalyStore(store.path)  # a second worker on the same database
        barrier.wait()
        try:
            other.reserve_verification(ref, expected_version=1, idempotency_key=KEY)
            outcomes.append("reserved")
        except InvalidTransition as exc:
            outcomes.append(str(exc))

    threads = [threading.Thread(target=reserve) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["aggregate_version_conflict"] * 4 + ["reserved"], outcomes
    assert store.get(ref)["aggregate_version"] == 2, "exactly one reservation was written"
