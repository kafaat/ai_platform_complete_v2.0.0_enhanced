from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from anomaly_store import AnomalyStore, InvalidTransition


def _payload() -> dict:
    return {
        "anomaly_ref": "urn:sahool:anomaly:anm_review",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "field_id": "fld_review",
        "season_id": "sea_review",
        "signal_type": "ndvi_decline",
    }


def test_upsert_is_idempotent_across_connections(tmp_path: Path):
    path = str(tmp_path / "anomalies.db")
    stores = [AnomalyStore(path) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda store: store.upsert_detected(_payload()), stores))
    assert {row["anomaly_ref"] for row in rows} == {"urn:sahool:anomaly:anm_review"}
    assert stores[0].list(_payload()["tenant_id"], "fld_review", "sea_review").__len__() == 1


def test_only_one_competing_transition_wins(tmp_path: Path):
    path = str(tmp_path / "anomalies.db")
    store_a = AnomalyStore(path)
    store_b = AnomalyStore(path)
    store_a.upsert_detected(_payload())

    def move(store: AnomalyStore):
        try:
            return store.transition("urn:sahool:anomaly:anm_review", "triaged", expected_version=1)[
                "aggregate_version"
            ]
        except InvalidTransition:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, (store_a, store_b)))
    assert sorted(map(str, results)) == ["2", "conflict"]
