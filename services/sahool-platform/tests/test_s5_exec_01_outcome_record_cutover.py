from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'services/sahool-platform/api/routers/decision_record.py'

def _body():
 t=P.read_text(); s=t.index('@router.post("/api/v1/outcome/record")'); e=t.index('\n\n@router.get("/api/v1/decision/{decision_id}/lineage")',s); return t[s:e]

def test_cutover_outcome_branch_is_service_only_and_strict():
 b=_body(); s=b.index('if mode.strict_decision_service_required:'); e=b.index('    try:',s); cut=b[s:e]
 assert 'tenant_connection' not in cut
 assert 'INSERT INTO outcome_record' not in cut
 assert 'await _mirror_outcome_to_service' in cut
 assert 'authoritative' in cut and 'persisted' in cut
 assert 'authoritative_store": "decision-service"' in cut
 assert 'service_result.get("outcome_id")' in cut

def test_pre_cutover_outcome_still_guarded_and_mirrored():
 b=_body(); pre=b[b.index('    try:'):]
 assert 'tenant_connection' in pre
 assert 'INSERT INTO outcome_record' in pre
 assert 'assert_platform_may_write_decision_sor("outcome_record")' in pre
 assert 'await _mirror_to_decision_service' in pre
