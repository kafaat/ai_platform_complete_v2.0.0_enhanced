#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://localhost}"
: "${SAHOOL_JWT:?Set SAHOOL_JWT for authenticated E2E runtime checks}"
: "${TENANT_ID:?Set TENANT_ID}"
: "${FIELD_ID:?Set FIELD_ID for an existing or seeded field}"
AUTH=(-H "Authorization: Bearer ${SAHOOL_JWT}" -H "Content-Type: application/json")

echo "==> field state"
curl -fsS --max-time 15 "${AUTH[@]}" "${BASE_URL}/api/v1/fields/${FIELD_ID}/state" | tee /tmp/sahool_field_state.json >/dev/null

echo "==> available imagery dates"
curl -fsS --max-time 20 "${AUTH[@]}" "${BASE_URL}/api/raster/v1/fields/${FIELD_ID}/available-dates" | tee /tmp/sahool_dates.json >/dev/null
DATE=$(python - <<'PY'
import json
from pathlib import Path
try:
    data=json.loads(Path('/tmp/sahool_dates.json').read_text())
    rows=data.get('dates') or data.get('items') or []
    print((rows[0].get('date') if isinstance(rows[0], dict) else rows[0]) if rows else 'latest')
except Exception:
    print('latest')
PY
)

echo "==> tilejson for NDVI date=${DATE}"
curl -fsS --max-time 20 "${AUTH[@]}" "${BASE_URL}/api/raster/v1/fields/${FIELD_ID}/tilejson?index=ndvi&date=${DATE}&tenant_id=${TENANT_ID}" | tee /tmp/sahool_tilejson.json >/dev/null
python - <<'PY'
import json
from pathlib import Path
j=json.loads(Path('/tmp/sahool_tilejson.json').read_text())
assert 'tiles' in j and j['tiles'], 'tilejson has no tiles'
assert 'cache_version' in j or any('v=' in t for t in j['tiles']), 'tilejson missing cache version'
print('tilejson ok')
PY

echo "==> AI agronomist evidence flow"
curl -fsS --max-time 30 "${AUTH[@]}" -X POST "${BASE_URL}/api/ai-agronomist/chat" \
  -d "{\"tenant_id\":\"${TENANT_ID}\",\"field_id\":\"${FIELD_ID}\",\"question\":\"اشرح حالة هذا الحقل بناء على المؤشرات المتاحة\",\"selected_imagery_date\":\"${DATE}\"}" \
  | tee /tmp/sahool_ai.json >/dev/null
python - <<'PY'
import json
from pathlib import Path
j=json.loads(Path('/tmp/sahool_ai.json').read_text())
assert j.get('mode') == 'evidence_only', 'AI must stay evidence_only'
assert 'annotations' in j, 'AI missing evidence annotations'
assert 'decision_authority' in j and j['decision_authority'] == 'field_intelligence_coordinator'
assert 'audit_event' in j, 'AI response missing audit_event status'
print('ai evidence flow ok')
PY

echo "field imagery AI E2E completed"
