import raster_batch_observability as obs


def test_counters_are_thread_safe_shape_and_resettable():
    obs.reset()
    obs.inc("claims_acquired_total")
    obs.inc("claims_acquired_total", 2)
    assert obs.snapshot()["claims_acquired_total"] == 3
    obs.reset()
    assert obs.snapshot() == {}
