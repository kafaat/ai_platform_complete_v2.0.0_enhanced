from services.ai_agronomist.guardrail_metrics import metrics

def test_metric_increment():
    metrics.increment("guardrail_trigger_total")
    assert metrics.snapshot()["guardrail_trigger_total"] >= 1
