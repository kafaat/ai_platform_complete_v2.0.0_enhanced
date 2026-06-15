"""Tests for recommendation_log — the memory of the platform (basis of all learning).
This file was previously untested (coverage gap found in critical review)."""

import tempfile
from pathlib import Path

from core.learning.recommendation_log import (
    RecommendationRecord,
    compute_mape,
    load_log,
    log_recommendation,
    record_outcome,
)


def _csv_path():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        return Path(f.name)


def _rec(rec_id="r1", pred=5.0, actual=None):
    return RecommendationRecord(
        rec_id=rec_id,
        tenant_id="t1",
        district_id="d1",
        zone_id="z1",
        crop="wheat",
        issued_date="2026-01-01",
        recommendation_ar="توصية",
        quality_grade="READY",
        predicted_yield_t_ha=pred,
        confidence="medium",
        actual_yield_t_ha=actual,
    )


class TestRecommendationLog:
    def test_log_and_load_roundtrip(self):
        p = _csv_path()
        log_recommendation(p, _rec("r1"))
        log_recommendation(p, _rec("r2"))
        loaded = load_log(p)
        assert len(loaded) == 2
        assert loaded[0].rec_id == "r1"
        p.unlink()

    def test_record_outcome_links_actual(self):
        p = _csv_path()
        log_recommendation(p, _rec("r1", pred=5.0))
        ok = record_outcome(p, "r1", actual_yield=4.5, outcome_date="2026-06-01")
        assert ok is True
        rec = [r for r in load_log(p) if r.rec_id == "r1"][0]
        assert rec.actual_yield_t_ha == 4.5
        p.unlink()

    def test_record_outcome_missing_id(self):
        p = _csv_path()
        log_recommendation(p, _rec("r1"))
        assert record_outcome(p, "nonexistent", 4.0, "2026-06-01") is False
        p.unlink()

    def test_mape_only_on_completed(self):
        # MAPE must only use records with actual outcomes, never fabricate
        p = _csv_path()
        log_recommendation(p, _rec("r1", pred=5.0))  # no actual yet
        result = compute_mape(p)
        # with no completed records, MAPE should be None/unknown, not 0 or fake
        assert result.get("mape") is None or result.get("n", 0) == 0
        p.unlink()

    def test_mape_computes_with_outcomes(self):
        p = _csv_path()
        log_recommendation(p, _rec("r1", pred=5.0))
        record_outcome(p, "r1", 4.0, "2026-06-01")
        result = compute_mape(p)
        assert result.get("n", 0) >= 1
        p.unlink()

    def test_no_prediction_written_as_zero(self):
        # honesty: predicted_yield None must stay None, not become 0
        p = _csv_path()
        log_recommendation(p, _rec("r1", pred=None))
        rec = load_log(p)[0]
        assert rec.predicted_yield_t_ha is None
        p.unlink()


class TestConcurrencySafety:
    def test_concurrent_outcomes_no_loss(self):
        # FIX: file lock prevents lost updates under concurrent writes
        import threading

        from core.learning.recommendation_log import (
            RecommendationRecord,
            load_log,
            log_recommendation,
            record_outcome,
        )

        p = _csv_path()
        for i in range(5):
            log_recommendation(
                p,
                RecommendationRecord(
                    rec_id=f"r{i}",
                    tenant_id="t",
                    district_id="d",
                    zone_id="z",
                    crop="wheat",
                    issued_date="2026-01-01",
                    recommendation_ar="x",
                    quality_grade="READY",
                    predicted_yield_t_ha=5.0,
                    confidence="medium",
                ),
            )
        threads = [
            threading.Thread(
                target=lambda i=i: record_outcome(p, f"r{i}", 4.0 + i * 0.1, "2026-06-01")
            )
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        updated = sum(1 for r in load_log(p) if r.actual_yield_t_ha is not None)
        assert updated == 5  # no lost updates
        p.unlink()
        Path(str(p) + ".lock").unlink(missing_ok=True)
