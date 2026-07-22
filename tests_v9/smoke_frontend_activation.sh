#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://localhost}"
EMAIL="${SAHOOL_E2E_EMAIL:-e2e+$(date +%s)@sahool.local}"
PASSWORD="${SAHOOL_E2E_PASSWORD:-DevPass12345!}"
FULL_NAME="${SAHOOL_E2E_NAME:-SAHOOL E2E Tester}"

need(){ command -v "$1" >/dev/null || { echo "missing command: $1" >&2; exit 2; }; }
need curl
need jq

json_curl(){
  local method="$1" path="$2" data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -fsS -X "$method" "$BASE_URL$path" -H 'Content-Type: application/json' "$@" --data "$data"
  else
    curl -fsS -X "$method" "$BASE_URL$path" "$@"
  fi
}

echo "[1/12] gateway health"
curl -fsS "$BASE_URL/healthz" >/dev/null

echo "[2/12] register"
reg=$(curl -fsS -X POST "$BASE_URL/auth/register" -H 'Content-Type: application/json' \
  --data "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"full_name\":\"$FULL_NAME\"}")
token=$(jq -r '.access_token // .token // empty' <<<"$reg")
tenant=$(jq -r '.tenant_id // .user.tenant_id // empty' <<<"$reg")

if [[ -z "$token" || "$token" == "null" ]]; then
  echo "register did not return token; trying login" >&2
  login=$(curl -fsS -X POST "$BASE_URL/auth/login" -H 'Content-Type: application/json' \
    --data "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
  token=$(jq -r '.access_token // .token // empty' <<<"$login")
  tenant=$(jq -r '.tenant_id // .user.tenant_id // empty' <<<"$login")
fi
[[ -n "$token" && "$token" != "null" ]] || { echo "no access token" >&2; exit 1; }

AUTH=(-H "Authorization: Bearer $token")
if [[ -n "$tenant" && "$tenant" != "null" ]]; then AUTH+=(-H "X-Tenant-ID: $tenant"); fi

echo "[3/12] login"
curl -fsS -X POST "$BASE_URL/auth/login" -H 'Content-Type: application/json' \
  --data "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null

echo "[4/12] farm create"
farm=$(curl -fsS -X POST "$BASE_URL/api/v1/farms" "${AUTH[@]}" -H 'Content-Type: application/json' \
  --data '{"name":"E2E Farm","country":"YE","governorate":"Al Jawf","district":"Al Hazm"}')
farm_id=$(jq -r '.id // .farm_id // empty' <<<"$farm")
[[ -n "$farm_id" && "$farm_id" != "null" ]] || { echo "farm id missing: $farm" >&2; exit 1; }

echo "[5/12] field create"
field=$(curl -fsS -X POST "$BASE_URL/api/v1/fields" "${AUTH[@]}" -H 'Content-Type: application/json' \
  --data "{\"name\":\"E2E Field\",\"farm_id\":\"$farm_id\",\"crop\":\"wheat\",\"area_ha\":1.2,\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[[[44.15,16.16],[44.16,16.16],[44.16,16.17],[44.15,16.17],[44.15,16.16]]]}}")
field_id=$(jq -r '.id // .field_id // empty' <<<"$field")
[[ -n "$field_id" && "$field_id" != "null" ]] || { echo "field id missing: $field" >&2; exit 1; }

echo "[6/12] core lists"
for path in \
  "/api/v1/farms" \
  "/api/v1/fields" \
  "/api/v1/alerts" \
  "/api/v1/devices" \
  "/api/v1/inventory" \
  "/api/v1/indicators/dashboard" \
  "/api/v1/weather/current?lat=16.16&lon=44.15"; do
  code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' "$BASE_URL$path" "${AUTH[@]}")
  [[ "$code" != "404" ]] || { echo "404: $path" >&2; cat /tmp/e2e_body >&2; exit 1; }
  [[ "$code" =~ ^2|3|401|403|422|503$ ]] || { echo "unexpected $code: $path" >&2; cat /tmp/e2e_body >&2; exit 1; }
done

echo "[7/12] feature endpoints non-404"
# These probes validate flags and router registration; they allow 401/403/422/503 because DB/data may be absent.
# GET probes
for path in \
  "/api/v1/fields/$field_id/decision-confidence" \
  "/api/v1/decision/test-decision/explain" \
  "/api/v1/execution/feedback" \
  "/api/v1/evidence/map" \
  "/api/v1/fields/$field_id/agronomic-replay" \
  "/api/v1/operations/summary" \
  "/api/v1/devices/twin" \
  "/api/v1/learning/summary"; do
  code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' "$BASE_URL$path" "${AUTH[@]}")
  [[ "$code" != "404" ]] || { echo "feature still 404: $path" >&2; cat /tmp/e2e_body >&2; exit 1; }
done
# POST probes
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' -X POST "$BASE_URL/api/v1/nl-gis/query" "${AUTH[@]}" -H 'Content-Type: application/json' --data '{"query":"اعرض الحقول"}')
[[ "$code" != "404" ]] || { echo "feature still 404: /api/v1/nl-gis/query" >&2; cat /tmp/e2e_body >&2; exit 1; }
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' -X POST "$BASE_URL/api/v1/irrigation/network/feasibility" "${AUTH[@]}" -H 'Content-Type: application/json' --data "{\"field_id\":\"$field_id\"}")
[[ "$code" != "404" ]] || { echo "feature still 404: /api/v1/irrigation/network/feasibility" >&2; cat /tmp/e2e_body >&2; exit 1; }
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' -X POST "$BASE_URL/api/v1/portfolio/command" "${AUTH[@]}" -H 'Content-Type: application/json' --data '{"scope":"farm"}')
[[ "$code" != "404" ]] || { echo "feature still 404: /api/v1/portfolio/command" >&2; cat /tmp/e2e_body >&2; exit 1; }

echo "[8/12] chatbot agent"
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' -X POST "$BASE_URL/api/agent/query" "${AUTH[@]}" -H 'Content-Type: application/json' \
  --data '{"message":"ما حالة الحقل؟","context":{"field_id":"'$field_id'"}}')
[[ "$code" != "404" ]] || { echo "agent query 404" >&2; cat /tmp/e2e_body >&2; exit 1; }

echo "[9/12] soil gateway non-404"
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' "$BASE_URL/api/soil/soil/wofost_params/$field_id" "${AUTH[@]}")
[[ "$code" != "404" ]] || { echo "soil proxy 404" >&2; cat /tmp/e2e_body >&2; exit 1; }

echo "[10/12] edge gateway non-404"
code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' "$BASE_URL/api/edge/healthz" "${AUTH[@]}")
[[ "$code" != "404" ]] || { echo "edge proxy 404" >&2; cat /tmp/e2e_body >&2; exit 1; }

echo "[11/12] raster/vegetation non-404"
for path in "/api/raster/healthz" "/api/vegetation/healthz"; do
  code=$(curl -sS -o /tmp/e2e_body -w '%{http_code}' "$BASE_URL$path" "${AUTH[@]}")
  [[ "$code" != "404" ]] || { echo "404: $path" >&2; cat /tmp/e2e_body >&2; exit 1; }
done

echo "[12/12] OK: frontend activation smoke passed"
