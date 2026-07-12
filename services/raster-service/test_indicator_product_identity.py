from indicator_product_identity import ProductIdentity, plan_multi_indicator_batch


def test_identity_is_stable_and_version_sensitive():
    a = ProductIdentity("t", "g", "s", "NDVI", "1", "m").key()
    b = ProductIdentity("t", "g", "s", "ndvi", "1", "m").key()
    assert a == b
    assert a != ProductIdentity("t", "g", "s", "ndvi", "2", "m").key()


def test_batch_deduplicates_preserving_order():
    plan = plan_multi_indicator_batch(
        tenant_id="t",
        field_geometry_hash="g",
        scene_id="s",
        indicators=["NDVI", "ndmi", "ndvi", ""],
        algorithm_version="1",
        qa_mask_version="m",
    )
    assert [p.indicator for p in plan] == ["ndvi", "ndmi"]
    assert len({p.key() for p in plan}) == 2
