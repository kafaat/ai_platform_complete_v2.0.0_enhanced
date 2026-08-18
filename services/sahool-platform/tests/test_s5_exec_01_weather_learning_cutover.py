from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def test_weather_decision_cutover_has_service_only_authoritative_branch():
    p=ROOT/'services/sahool-platform/api/routers/weather.py'; t=p.read_text(); s=t.index('async def _persist_weather_decision_record'); e=t.index('def _recommendation_payload_from_plan',s); b=t[s:e]
    cs=b.index('if mode.strict_decision_service_required:'); ce=b.index('    assert_platform_may_write_decision_sor',cs); cut=b[cs:ce]
    assert 'conn.execute' not in cut
    assert '_emit_domain_event' not in cut
    assert 'await _mirror_decision_to_service' in cut
    assert 'authoritative' in cut and 'persisted' in cut

def test_learning_update_cutover_has_exactly_one_authoritative_branch():
    p=ROOT/'services/sahool-platform/api/phase_runtime_store.py'; t=p.read_text(); s=t.index('async def persist_phase10_learning_outputs'); e=t.index('        scenario = outputs.get("scenario_result")',s); b=t[s:e]
    cs=b.index('if mode.strict_decision_service_required:'); elsepos=b.index('            else:',cs); cut=b[cs:elsepos]
    assert 'conn.execute' not in cut
    assert 'await _mirror_learning_update_to_service' in cut
    assert 'authoritative' in cut and 'persisted' in cut
    assert 'if not mode.strict_decision_service_required:' in b
    assert 'assert_platform_may_write_decision_sor("online_learning_updates")' in b
