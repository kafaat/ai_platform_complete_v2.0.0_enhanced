#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# SAHOOL post-commit live acceptance runbook
# Baseline family: 9d58b0dc + accepted C1..C13 + qdrant-seed compatibility hardening
# IMPORTANT: this script MUST run from a real Git checkout after the forward-port is committed.
# It never edits authority_cutovers.json and never promotes authority automatically.

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT}" || ! -d "${ROOT}/.git" ]]; then
  echo "FATAL: real Git checkout required; delivery ZIP is not sufficient for live provenance" >&2
  exit 2
fi
cd "$ROOT"

MODE="${1:-preflight}"
case "$MODE" in
  preflight|rag|s5|c11|verify|all) ;;
  *) echo "usage: $0 {preflight|rag|s5|c11|verify|all}" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-python}"
ARTIFACT_ROOT="${LIVE_ACCEPTANCE_ARTIFACT_DIR:-artifacts/final-live-acceptance}"
RAG_DIR="$ARTIFACT_ROOT/rag"
S5_DIR="$ARTIFACT_ROOT/s5-authority"
C11_DIR="$ARTIFACT_ROOT/c11-lineage"
mkdir -p "$RAG_DIR" "$S5_DIR" "$C11_DIR"

fail() { echo "FATAL: $*" >&2; exit 2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "missing required tool: $1"; }
need_env() { [[ -n "${!1:-}" ]] || fail "missing required environment variable: $1"; }
sha40() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }

need_cmd git
need_cmd curl
need_cmd "$PYTHON"

SUBJECT_SHA="$(git rev-parse HEAD | tr '[:upper:]' '[:lower:]')"
sha40 "$SUBJECT_SHA" || fail "HEAD is not a full 40-char commit SHA: $SUBJECT_SHA"

# Optional operator pin. If supplied, it MUST equal HEAD.
if [[ -n "${EXPECTED_SUBJECT_SHA:-}" ]]; then
  EXPECTED_SUBJECT_SHA="$(printf '%s' "$EXPECTED_SUBJECT_SHA" | tr '[:upper:]' '[:lower:]')"
  sha40 "$EXPECTED_SUBJECT_SHA" || fail "EXPECTED_SUBJECT_SHA must be 40 lowercase hex"
  [[ "$EXPECTED_SUBJECT_SHA" == "$SUBJECT_SHA" ]] || fail "subject mismatch: HEAD=$SUBJECT_SHA expected=$EXPECTED_SUBJECT_SHA"
fi
export GITHUB_SHA="$SUBJECT_SHA"

# Baseline ancestry check: the new forward-port commit must descend from 9d58b0dc.
BASELINE_PREFIX="${EXPECTED_BASELINE_PREFIX:-9d58b0dc}"
BASELINE_SHA="$(git rev-list --all | grep -m1 "^${BASELINE_PREFIX}" || true)"
[[ -n "$BASELINE_SHA" ]] || fail "cannot resolve expected baseline prefix ${BASELINE_PREFIX} in this checkout"
git merge-base --is-ancestor "$BASELINE_SHA" "$SUBJECT_SHA" || fail "HEAD does not descend from baseline $BASELINE_SHA"

printf '%s\n' "$SUBJECT_SHA" > "$ARTIFACT_ROOT/SUBJECT_SHA.txt"
printf '%s\n' "$BASELINE_SHA" > "$ARTIFACT_ROOT/BASELINE_SHA.txt"

static_guards() {
  echo "== Static/authority guard baseline =="
  "$PYTHON" scripts/architecture/platform_shrink_ratchet_guard.py
  "$PYTHON" scripts/architecture/s5_exec_01_edge_freeze.py --check
  "$PYTHON" scripts/ci/s5_exec_01_writer_cutover_guard.py
  "$PYTHON" scripts/architecture/authority_cutover_guard.py
  "$PYTHON" scripts/ci/rag_operational_boundary_guard.py
  "$PYTHON" scripts/architecture/rag_authority_convergence_guard.py
  "$PYTHON" scripts/architecture/rag_direct_qdrant_boundary_guard.py
}

preflight() {
  echo "== Subject =="
  echo "HEAD=$SUBJECT_SHA"
  echo "BASELINE=$BASELINE_SHA"

  static_guards

  echo "== Required tools =="
  need_cmd psql

  echo "== S5 live evidence preflight =="
  "$PYTHON" scripts/staging/s5_live_authority_closure.py preflight \
    --subject-sha "$SUBJECT_SHA" \
    --output "$S5_DIR/preflight.json"

  echo "== RAG live probe required environment =="
  for v in QDRANT_URL QDRANT_COLLECTION OLLAMA_BASE_URL EMBEDDING_MODEL RAG_RETRIEVAL_URL RAG_TENANT_ID; do
    need_env "$v"
  done
  # QDRANT_API_KEY may be empty only when the deployment explicitly has no API key.

  echo "== C11 live lineage required environment =="
  need_env DATABASE_URL

  echo "preflight_ok subject=$SUBJECT_SHA"
}

rag_collect() {
  echo "== RAG live parity collection =="
  for v in QDRANT_URL QDRANT_COLLECTION OLLAMA_BASE_URL EMBEDDING_MODEL RAG_RETRIEVAL_URL RAG_TENANT_ID; do
    need_env "$v"
  done

  # Default five probes; override by setting RAG_QUERY_1..5.
  local q1="${RAG_QUERY_1:-wheat nitrogen deficiency diagnosis}"
  local q2="${RAG_QUERY_2:-irrigation scheduling under heat stress}"
  local q3="${RAG_QUERY_3:-grape powdery mildew management}"
  local q4="${RAG_QUERY_4:-citrus salinity management}"
  local q5="${RAG_QUERY_5:-potato late blight prevention}"

  "$PYTHON" scripts/architecture/rag_live_parity_probe.py \
    --tenant-id "$RAG_TENANT_ID" \
    --subject-sha "$SUBJECT_SHA" \
    --query "$q1" --query "$q2" --query "$q3" --query "$q4" --query "$q5" \
    --out "$RAG_DIR/rag_live_parity_receipt.json"

  "$PYTHON" scripts/architecture/rag_live_parity_receipt_guard.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" \
    --subject-sha "$SUBJECT_SHA"

  "$PYTHON" scripts/ci/c8_rag_production_certification.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" \
    --subject-sha "$SUBJECT_SHA" \
    | tee "$RAG_DIR/c8_result.json"

  # IMPORTANT: parity proof is not revocation approval. The convergence guard must remain
  # fail-closed while direct_qdrant_revocation_ready=false.
  "$PYTHON" scripts/architecture/rag_authority_convergence_guard.py \
    | tee "$RAG_DIR/rag_authority_convergence_guard.txt"
}

s5_collect() {
  echo "== Decision + Field + KG live receipts =="
  # The canonical preflight owns the exact environment list. We call it again here so this
  # phase cannot accidentally run after environment drift.
  "$PYTHON" scripts/staging/s5_live_authority_closure.py preflight \
    --subject-sha "$SUBJECT_SHA" \
    --output "$S5_DIR/preflight.json"

  "$PYTHON" scripts/staging/s5_live_authority_closure.py collect \
    --subject-sha "$SUBJECT_SHA" \
    --out-dir "$S5_DIR" \
    --decision-url "${DECISION_SERVICE_URL:-http://localhost:8097}" \
    --platform-url "${SAHOOL_PLATFORM_URL:-http://localhost:8000}" \
    --bundle-output "$S5_DIR/s5-live-authority-bundle.json"

  "$PYTHON" scripts/ci/c9_decision_authority_certification.py \
    --receipt "$S5_DIR/decision-live-closure.json" \
    --subject-sha "$SUBJECT_SHA" \
    | tee "$S5_DIR/c9_result.json"

  "$PYTHON" scripts/ci/c10_field_authority_certification.py \
    --receipt "$S5_DIR/field-rls-live-evidence.json" \
    --subject-sha "$SUBJECT_SHA" \
    | tee "$S5_DIR/c10_result.json"

  "$PYTHON" scripts/architecture/s4_kg_runtime_parity_receipt_guard.py \
    --receipt "$S5_DIR/kg-runtime-parity.json" \
    --subject-sha "$SUBJECT_SHA"
}

c11_collect() {
  echo "== C11 closed-loop lineage live certification =="
  need_cmd psql
  need_env DATABASE_URL
  "$PYTHON" scripts/ci/c11_closed_loop_lineage_certification.py \
    --live --subject-sha "$SUBJECT_SHA" \
    | tee "$C11_DIR/c11_live_result.json"

  "$PYTHON" - "$C11_DIR/c11_live_result.json" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
if d.get('status') != 'LIVE_EVIDENCE_VERIFIED':
    raise SystemExit(f"C11 not verified: {d}")
if d.get('subject_match') is not True:
    raise SystemExit("C11 subject_match is not true")
print('c11_live_verified')
PY
}

verify_all() {
  echo "== Canonical receipt re-verification =="
  "$PYTHON" scripts/architecture/rag_live_parity_receipt_guard.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" --subject-sha "$SUBJECT_SHA"

  "$PYTHON" scripts/staging/s5_live_authority_closure.py verify \
    --subject-sha "$SUBJECT_SHA" \
    --decision-receipt "$S5_DIR/decision-live-closure.json" \
    --field-receipt "$S5_DIR/field-rls-live-evidence.json" \
    --kg-receipt "$S5_DIR/kg-runtime-parity.json" \
    --output "$S5_DIR/s5-live-authority-verified.json"

  "$PYTHON" scripts/ci/c8_rag_production_certification.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" --subject-sha "$SUBJECT_SHA"
  "$PYTHON" scripts/ci/c9_decision_authority_certification.py \
    --receipt "$S5_DIR/decision-live-closure.json" --subject-sha "$SUBJECT_SHA"
  "$PYTHON" scripts/ci/c10_field_authority_certification.py \
    --receipt "$S5_DIR/field-rls-live-evidence.json" --subject-sha "$SUBJECT_SHA"

  echo "== C12 safety boundary =="
  # This source tree has NO canonical C12 live activation receipt collector/guard.
  # Therefore C12 MUST remain EVIDENCE_REQUIRED. Treat any PASS here as a regression.
  "$PYTHON" scripts/ci/c12_governed_learning_promotion_certification.py \
    | tee "$ARTIFACT_ROOT/c12_result.json"
  "$PYTHON" - "$ARTIFACT_ROOT/c12_result.json" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
if d.get('status') != 'EVIDENCE_REQUIRED':
    raise SystemExit(f"UNSAFE: C12 unexpectedly left EVIDENCE_REQUIRED: {d}")
if d.get('promotion_permitted') is not False or d.get('automatic_promotion') is not False:
    raise SystemExit(f"UNSAFE: C12 promotion flag changed: {d}")
print('c12_fail_closed_ok')
PY

  echo "== C13 safety boundary =="
  "$PYTHON" scripts/ci/c13_physical_shrink_certification.py \
    | tee "$ARTIFACT_ROOT/c13_result.json"
  "$PYTHON" - "$ARTIFACT_ROOT/c13_result.json" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
if d.get('physical_shrink_authorized') is not False:
    raise SystemExit(f"UNSAFE: C13 authorized shrink: {d}")
print('c13_no_new_shrink_ok')
PY

  echo "== Final authority guards (non-promoting) =="
  "$PYTHON" scripts/architecture/authority_cutover_guard.py | tee "$ARTIFACT_ROOT/authority_cutover_guard.txt"
  "$PYTHON" scripts/architecture/platform_shrink_ratchet_guard.py | tee "$ARTIFACT_ROOT/platform_shrink_ratchet_guard.txt"
  "$PYTHON" scripts/architecture/s5_exec_01_edge_freeze.py --check | tee "$ARTIFACT_ROOT/s5_edge_freeze_guard.txt"
  "$PYTHON" scripts/ci/s5_exec_01_writer_cutover_guard.py | tee "$ARTIFACT_ROOT/s5_writer_cutover_guard.txt"

  "$PYTHON" - "$ARTIFACT_ROOT" "$SUBJECT_SHA" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); subject=sys.argv[2]
files=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name != 'SHA256SUMS.txt':
        files.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}")
(root/'SHA256SUMS.txt').write_text('\n'.join(files)+'\n',encoding='utf-8')
summary={
  'schema':'sahool.post-commit-live-acceptance-summary/v1',
  'subject_sha':subject,
  'authority_promotion':False,
  'physical_shrink_authorized':False,
  'c12_live_activation_receipt_supported':False,
  'next_action':'explicit human adjudication only after reviewing canonical receipts; C12 remains blocked pending its own canonical live receipt contract',
}
(root/'SUMMARY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(summary,sort_keys=True))
PY
}

case "$MODE" in
  preflight) preflight ;;
  rag) preflight; rag_collect ;;
  s5) preflight; s5_collect ;;
  c11) preflight; c11_collect ;;
  verify) verify_all ;;
  all)
    preflight
    rag_collect
    s5_collect
    c11_collect
    verify_all
    ;;
esac
