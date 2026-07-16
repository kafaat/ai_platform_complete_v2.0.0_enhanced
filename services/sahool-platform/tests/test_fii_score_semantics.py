from api.disease_diagnosis import diagnose


def test_rule_diagnosis_exposes_non_calibrated_score_semantics():
    result = diagnose("wheat", ["orange_pustules"]).to_dict()
    candidate = result["candidates"][0]
    assert candidate["score_semantics"] == "rule_match"
    assert candidate["is_calibrated"] is False
    assert candidate["producer_type"] == "rule_engine"
    assert candidate["confidence"] == candidate["score"]
    assert "درجة تطابق أعراض" in result["next_step_ar"]
