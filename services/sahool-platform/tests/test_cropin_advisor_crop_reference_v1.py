"""Cropin-style advisor reference: a crop card is never a tenant fact."""

from core.crop_intelligence.advisor_reference import compose_advisor_crop_reference


def test_single_crop_season_selects_governed_card():
    out = compose_advisor_crop_reference({"crop": "wheat"}, {"crops": ["wheat"]})
    assert out["status"] == "reference_only"
    assert out["crop_id"] == "wheat"
    assert out["knowledge_digest"]
    assert out["source_ids"]
    assert out["decision_authority"] == "none"


def test_multi_crop_season_must_not_pick_arbitrary_crop():
    out = compose_advisor_crop_reference({"crop": "wheat"}, {"crops": ["wheat", "maize"]})
    assert out == {"status": "unavailable", "reason": "season_crop_ambiguous_or_missing"}


def test_missing_crop_does_not_fabricate_knowledge():
    out = compose_advisor_crop_reference({}, None)
    assert out["status"] == "unavailable"
    assert "knowledge_digest" not in out


def test_unlisted_variety_does_not_override_crop_card():
    out = compose_advisor_crop_reference({"crop": "wheat"}, {"crops": ["wheat"], "cultivar": "not-a-card"})
    assert out["status"] == "reference_only"
    assert out["variety_id"] is None
    assert "season_variety_not_in_reference_catalog" in out["limitations"]
