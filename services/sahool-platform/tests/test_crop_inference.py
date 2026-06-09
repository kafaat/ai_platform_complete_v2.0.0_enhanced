"""Tests for crop suitability inference: produces a shortlist NOT a decision,
trees get lower ceiling (blocked without lab soil), trial recommendations (20%/50%)."""
from core.crop_inference import infer_suitable_crops


def _scores():
    return [
        {"crop_id":"wheat","climate":0.90,"soil":0.60,"water":0.70,"market":0.80,"is_tree":False},
        {"crop_id":"maize","climate":0.50,"soil":0.45,"water":0.40,"market":0.50,"is_tree":False},
        {"crop_id":"mango","climate":0.40,"soil":0.30,"water":0.30,"market":0.50,"is_tree":True},
    ]


class TestInference:
    def test_returns_sorted_shortlist(self):
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=False)
        scores = [c.score for c in out]
        assert scores == sorted(scores, reverse=True)

    def test_tree_blocked_without_lab_soil(self):
        # CRITICAL: شجرة بلا تربة مختبرية → محظورة (none)
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=False)
        mango = [c for c in out if c.crop_id == "mango"][0]
        assert mango.confidence == "none"

    def test_tree_low_even_with_lab_soil(self):
        # شجرة مع تربة → سقف low أقصى (لا medium)
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=True)
        mango = [c for c in out if c.crop_id == "mango"][0]
        assert mango.confidence in ("none", "low")

    def test_ceiling_low_without_lab_soil(self):
        # CRITICAL: بلا تربة مختبرية → السقف LOW للمحاصيل أيضاً
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=False)
        wheat = [c for c in out if c.crop_id == "wheat"][0]
        assert wheat.confidence == "low"

    def test_recommendation_is_trial_not_decision(self):
        # CRITICAL: التوصية تجريب لا قرار (20% بلا تربة)
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=False)
        wheat = [c for c in out if c.crop_id == "wheat"][0]
        assert "جرّب" in wheat.recommendation_ar or "20%" in wheat.recommendation_ar

    def test_low_score_crop_rejected(self):
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=False)
        maize = [c for c in out if c.crop_id == "maize"][0]
        assert maize.confidence == "none"

    def test_trial_50pct_with_lab_soil(self):
        out = infer_suitable_crops(crop_scores=_scores(), has_lab_soil=True)
        wheat = [c for c in out if c.crop_id == "wheat"][0]
        assert "50%" in wheat.recommendation_ar
