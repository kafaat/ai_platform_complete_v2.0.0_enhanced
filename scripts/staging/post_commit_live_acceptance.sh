#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# SAHOOL post-commit live acceptance runbook
# Agent execution contract: exact commit + tree pins, clean tracked checkout,
# evidence-only acknowledgement, and a non-authoritative execution identity.
# Baseline: main@fc36d081324dacd97a38abb2e43f101ad1469c42 (PR #965 merged)
# plus exact runtime commit/tree pins supplied to agent mode.
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
  doctor|preflight|rag|s5|c11|c12|verify|check-seal|abort|recover|all|agent) ;;
  *) echo "usage: $0 {doctor|preflight|rag|s5|c11|c12|verify|check-seal|abort|recover|all|agent}" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-python}"
LIVE_TIMEOUT="${LIVE_TIMEOUT:-900}"
ROUND_SCHEMA="sahool.live-acceptance-round/v1"
ROUND_CREATED=0
ROUND_DIR=""

mark_aborted() {
  [[ "$ROUND_CREATED" == "1" && -n "$ROUND_DIR" && -s "$ROUND_DIR/ROUND.json" ]] || return 0
  "$PYTHON" - "$ROUND_DIR/ROUND.json" "${ROUND_FILE:-}" <<'PY' 2>/dev/null || true
import json,os,pathlib,sys,tempfile
paths=[pathlib.Path(raw) for raw in sys.argv[1:] if raw and pathlib.Path(raw).is_file()]
docs=[json.loads(p.read_text(encoding="utf-8")) for p in paths]
if len(docs)==2 and all(d.get("round_state")=="SEALED" for d in docs) and docs[0]==docs[1]:
    raise SystemExit(0)
for p,d in zip(paths,docs):
    d["round_state"]="ABORTED"
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=p.name+".")
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(json.dumps(d,indent=2,sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)
PY
}

fail() { echo "FATAL: $*" >&2; mark_aborted; exit 2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "missing required tool: $1"; }
need_env() { [[ -n "${!1:-}" ]] || fail "missing required environment variable: $1"; }
sha40() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }

need_cmd git
need_cmd curl
need_cmd "$PYTHON"

SUBJECT_SHA="$(git rev-parse HEAD | tr '[:upper:]' '[:lower:]')"
sha40 "$SUBJECT_SHA" || fail "HEAD is not a full 40-char commit SHA: $SUBJECT_SHA"
SUBJECT_TREE="$(git rev-parse 'HEAD^{tree}' | tr '[:upper:]' '[:lower:]')"
sha40 "$SUBJECT_TREE" || fail "HEAD tree is not a full 40-char object ID: $SUBJECT_TREE"

# Optional operator pin. If supplied, it MUST equal HEAD.
if [[ -n "${EXPECTED_SUBJECT_SHA:-}" ]]; then
  EXPECTED_SUBJECT_SHA="$(printf '%s' "$EXPECTED_SUBJECT_SHA" | tr '[:upper:]' '[:lower:]')"
  sha40 "$EXPECTED_SUBJECT_SHA" || fail "EXPECTED_SUBJECT_SHA must be 40 lowercase hex"
  [[ "$EXPECTED_SUBJECT_SHA" == "$SUBJECT_SHA" ]] || fail "subject mismatch: HEAD=$SUBJECT_SHA expected=$EXPECTED_SUBJECT_SHA"
fi
if [[ -n "${EXPECTED_SUBJECT_TREE:-}" ]]; then
  EXPECTED_SUBJECT_TREE="$(printf '%s' "$EXPECTED_SUBJECT_TREE" | tr '[:upper:]' '[:lower:]')"
  sha40 "$EXPECTED_SUBJECT_TREE" || fail "EXPECTED_SUBJECT_TREE must be 40 lowercase hex"
  [[ "$EXPECTED_SUBJECT_TREE" == "$SUBJECT_TREE" ]] \
    || fail "tree mismatch: HEAD tree=$SUBJECT_TREE expected=$EXPECTED_SUBJECT_TREE"
fi
export GITHUB_SHA="$SUBJECT_SHA"

assert_subject_unchanged() {
  local current_sha current_tree
  current_sha="$(git rev-parse HEAD | tr '[:upper:]' '[:lower:]')"
  current_tree="$(git rev-parse 'HEAD^{tree}' | tr '[:upper:]' '[:lower:]')"
  [[ "$current_sha" == "$SUBJECT_SHA" && "$current_tree" == "$SUBJECT_TREE" ]] \
    || fail "checkout changed during acceptance: start=$SUBJECT_SHA/$SUBJECT_TREE current=$current_sha/$current_tree"
}

EXECUTION_ACTOR_KIND="operator"
EXECUTION_ACTOR_ID="${USER:-unknown}"

# Baseline ancestry check: require the full post-PR-965 main commit, never an
# ambiguous abbreviated SHA. A shallow checkout must fetch enough history to
# contain this commit before it can produce live provenance.
BASELINE_SHA="${EXPECTED_BASELINE_SHA:-fc36d081324dacd97a38abb2e43f101ad1469c42}"
sha40 "$BASELINE_SHA" || fail "EXPECTED_BASELINE_SHA must be 40 lowercase hex"
git cat-file -e "${BASELINE_SHA}^{commit}" 2>/dev/null \
  || fail "baseline commit $BASELINE_SHA is absent; fetch sufficient main history before live acceptance"
git merge-base --is-ancestor "$BASELINE_SHA" "$SUBJECT_SHA" || fail "HEAD does not descend from baseline $BASELINE_SHA"

# Agent preconditions are intentionally checked before mkdir, locks, pointer
# files, or evidence writes. A refused agent invocation is side-effect free.
if [[ "$MODE" == "agent" ]]; then
  [[ -n "${EXPECTED_SUBJECT_SHA:-}" ]] \
    || fail "agent mode requires EXPECTED_SUBJECT_SHA=<40-hex>"
  [[ -n "${EXPECTED_SUBJECT_TREE:-}" ]] \
    || fail "agent mode requires EXPECTED_SUBJECT_TREE=<40-hex>"
  [[ "${AGENT_CONFIRM_EVIDENCE_ONLY:-0}" == "1" ]] \
    || fail "agent mode requires AGENT_CONFIRM_EVIDENCE_ONLY=1"
  [[ "${AGENT_EXECUTOR_ID:-}" =~ ^[A-Za-z0-9._:@/-]{3,128}$ ]] \
    || fail "AGENT_EXECUTOR_ID is required and must be a safe 3..128 character identifier"
  [[ -z "$(git status --porcelain --untracked-files=no)" ]] \
    || fail "agent mode requires a clean tracked worktree"
fi

atomic_write() {
  local target="$1" tmp
  tmp="$(mktemp "${target}.XXXXXX")" || fail "cannot allocate temporary file for $target"
  if ! cat > "$tmp"; then rm -f "$tmp"; fail "write failed for $target"; fi
  mv -f "$tmp" "$target"
}

run_live() {
  local rc=0
  timeout --kill-after=30s "$LIVE_TIMEOUT" "$@" || rc=$?
  case "$rc" in
    0) return 0 ;;
    124|137|143) fail "live command timed out or was terminated (rc=$rc): $1" ;;
    125|126|127) fail "live command could not be invoked (rc=$rc): $1" ;;
    *) return "$rc" ;;
  esac
}

finalize_json() {
  local final="$1" tmp="$1.new"
  [[ -s "$tmp" ]] || fail "collector produced no receipt: $tmp"
  "$PYTHON" -c 'import json,sys;json.load(open(sys.argv[1],encoding="utf-8"))' "$tmp" \
    || fail "collector produced invalid JSON: $tmp"
  mv -f "$tmp" "$final"
}

ARTIFACT_BASE="${LIVE_ACCEPTANCE_ARTIFACT_DIR:-artifacts/final-live-acceptance/${SUBJECT_SHA}}"
LOCK_DIR="$ARTIFACT_BASE/locks"
ROUNDS_DIR="$ARTIFACT_BASE/rounds"
ROUND_FILE="$ARTIFACT_BASE/ROUND.json"
RAG_DIR=""; S5_DIR=""; C11_DIR=""; C12_DIR=""; ARTIFACT_ROOT=""

set_round_dirs() {
  ARTIFACT_ROOT="$ROUND_DIR"
  RAG_DIR="$ROUND_DIR/rag"
  S5_DIR="$ROUND_DIR/s5-authority"
  C11_DIR="$ROUND_DIR/c11-lineage"
  C12_DIR="$ROUND_DIR/c12-model-activation"
}

open_round() {
  local requested="${ROUND_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  [[ "$requested" =~ ^[A-Za-z0-9._-]{6,64}$ ]] || fail "unsafe ROUND_ID: $requested"
  ROUND_ID="$requested"; ROUND_DIR="$ROUNDS_DIR/$ROUND_ID"; set_round_dirs
  [[ ! -e "$ROUND_DIR" ]] || fail "round namespace already exists: $ROUND_DIR"
  mkdir -p "$RAG_DIR" "$S5_DIR" "$C11_DIR" "$C12_DIR"
  "$PYTHON" - "$ROUND_DIR/ROUND.json" "$ROUND_SCHEMA" "$ROUND_ID" "$SUBJECT_SHA" "$SUBJECT_TREE" "$BASELINE_SHA" <<'PY'
import json,os,pathlib,sys,tempfile,time
p=pathlib.Path(sys.argv[1])
d={"schema":sys.argv[2],"round_id":sys.argv[3],"round_state":"OPEN",
   "subject_sha":sys.argv[4],"subject_tree":sys.argv[5],"baseline_sha":sys.argv[6],
   "opened_at_epoch":int(time.time())}
p.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY
  ROUND_CREATED=1
  cat "$ROUND_DIR/ROUND.json" | atomic_write "$ROUND_FILE"
  printf '%s\n' "$SUBJECT_SHA" | atomic_write "$ROUND_DIR/SUBJECT_SHA.txt"
  printf '%s\n' "$SUBJECT_TREE" | atomic_write "$ROUND_DIR/SUBJECT_TREE.txt"
  printf '%s\n' "$BASELINE_SHA" | atomic_write "$ROUND_DIR/BASELINE_SHA.txt"
}

load_round() {
  [[ -s "$ROUND_FILE" ]] || fail "no active round; run preflight first"
  ROUND_ID="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["round_id"])' "$ROUND_FILE")"
  [[ "$ROUND_ID" =~ ^[A-Za-z0-9._-]{6,64}$ ]] || fail "pointer contains unsafe round_id"
  ROUND_DIR="$ROUNDS_DIR/$ROUND_ID"; set_round_dirs
  [[ -s "$ROUND_DIR/ROUND.json" ]] || fail "active round namespace is incomplete"
  cmp -s "$ROUND_FILE" "$ROUND_DIR/ROUND.json" || fail "round pointer and namespace disagree; use recover"
  "$PYTHON" - "$ROUND_DIR/ROUND.json" "$ROUND_SCHEMA" "$SUBJECT_SHA" "$SUBJECT_TREE" <<'PY' \
    || fail "round identity/state validation failed"
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if d.get("schema")!=sys.argv[2]: raise SystemExit("round schema mismatch")
if d.get("subject_sha")!=sys.argv[3] or d.get("subject_tree")!=sys.argv[4]:
    raise SystemExit("round subject mismatch")
if d.get("round_state") not in ("OPEN","SEALING","SEALED","ABORTED"):
    raise SystemExit("invalid round state")
PY
  ROUND_CREATED=1
}

load_recovery_round() {
  [[ -s "$ROUND_FILE" ]] || fail "no active round pointer to recover"
  ROUND_ID="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["round_id"])' "$ROUND_FILE")"
  [[ "$ROUND_ID" =~ ^[A-Za-z0-9._-]{6,64}$ ]] || fail "pointer contains unsafe round_id"
  ROUND_DIR="$ROUNDS_DIR/$ROUND_ID"; set_round_dirs
  [[ -s "$ROUND_DIR/ROUND.json" ]] || fail "round pointer names a missing namespace"
  ROUND_CREATED=1
}

set_round_state() {
  local state="$1"
  "$PYTHON" - "$ROUND_DIR/ROUND.json" "$ROUND_FILE" "$state" <<'PY'
import json,os,pathlib,sys,tempfile
for raw in sys.argv[1:3]:
    p=pathlib.Path(raw); d=json.loads(p.read_text(encoding="utf-8")); d["round_state"]=sys.argv[3]
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=p.name+".")
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        f.write(json.dumps(d,indent=2,sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)
PY
}

if [[ "$MODE" != "doctor" ]]; then
  need_cmd flock
  need_cmd timeout
  mkdir -p "$LOCK_DIR" "$ROUNDS_DIR"
  exec 9>"$LOCK_DIR/acceptance.lock"
  flock -n 9 || fail "another acceptance invocation owns this artifact root"
  trap 'mark_aborted; exit 7' INT TERM
  trap 'rc=$?; mark_aborted; exit "$rc"' ERR
  case "$MODE" in
    preflight|all|agent) open_round ;;
    recover) load_recovery_round ;;
    *) load_round ;;
  esac
fi

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

# رخيصٌ ومستقلٌّ عن البيئة الحيّة عمداً: لا يحتاج Decision/Field/KG ولا psql ولا
# قواعد بيانات. يقيس هُويّة مُنتِج S5/C9 (القانونيّ حاضرٌ، والقديم المحظور غائب)
# قبل أن يُنفَق أيّ وقتٍ على تجهيز بيئةٍ حيّة كاملة (PLATFORM-ROUTES-DUAL-S5-PRODUCER-01).
doctor() {
  echo "== Subject =="
  echo "HEAD=$SUBJECT_SHA"
  echo "TREE=$SUBJECT_TREE"
  echo "BASELINE=$BASELINE_SHA"

  static_guards

  echo "== S5/C9 producer identity =="
  "$PYTHON" scripts/staging/s5_live_authority_closure.py doctor
}

preflight() {
  echo "== Subject =="
  echo "HEAD=$SUBJECT_SHA"
  echo "TREE=$SUBJECT_TREE"
  echo "BASELINE=$BASELINE_SHA"

  static_guards

  echo "== Required tools =="
  need_cmd psql

  echo "== S5 live evidence preflight =="
  run_live "$PYTHON" scripts/staging/s5_live_authority_closure.py preflight \
    --subject-sha "$SUBJECT_SHA" \
    --output "$S5_DIR/preflight.json.new"
  finalize_json "$S5_DIR/preflight.json"

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

  run_live "$PYTHON" scripts/architecture/rag_live_parity_probe.py \
    --tenant-id "$RAG_TENANT_ID" \
    --subject-sha "$SUBJECT_SHA" \
    --query "$q1" --query "$q2" --query "$q3" --query "$q4" --query "$q5" \
    --out "$RAG_DIR/rag_live_parity_receipt.json.new"
  finalize_json "$RAG_DIR/rag_live_parity_receipt.json"

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
  run_live "$PYTHON" scripts/staging/s5_live_authority_closure.py preflight \
    --subject-sha "$SUBJECT_SHA" \
    --output "$S5_DIR/preflight.json.new"
  finalize_json "$S5_DIR/preflight.json"

  run_live "$PYTHON" scripts/staging/s5_live_authority_closure.py collect \
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
  run_live "$PYTHON" scripts/ci/c11_closed_loop_lineage_certification.py \
    --live --subject-sha "$SUBJECT_SHA" \
    | tee "$C11_DIR/c11_live_result.json.new"
  finalize_json "$C11_DIR/c11_live_result.json"

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


c12_collect() {
  echo "== C12 governed model activation live evidence =="
  need_env DATABASE_URL
  need_env DECISION_SERVICE_SOR_ENABLED
  need_env C12_TENANT_ID
  need_env C12_MODEL_ID
  need_env C12_TARGET_ENVIRONMENT
  local args=(
    collect
    --subject-sha "$SUBJECT_SHA"
    --tenant-id "$C12_TENANT_ID"
    --model-id "$C12_MODEL_ID"
    --target-environment "$C12_TARGET_ENVIRONMENT"
    --output "$C12_DIR/c12-live-activation-receipt.json.new"
  )
  if [[ -n "${C12_FEATURE_SET_ID:-}" ]]; then
    args+=(--feature-set-id "$C12_FEATURE_SET_ID")
  fi
  run_live "$PYTHON" scripts/staging/c12_live_activation_receipt.py "${args[@]}"
  finalize_json "$C12_DIR/c12-live-activation-receipt.json"
  "$PYTHON" scripts/ci/c12_governed_learning_promotion_certification.py \
    --receipt "$C12_DIR/c12-live-activation-receipt.json" \
    --subject-sha "$SUBJECT_SHA" \
    | tee "$C12_DIR/c12_result.json"
  "$PYTHON" - "$C12_DIR/c12_result.json" <<'PY'
import json,sys
body=json.load(open(sys.argv[1],encoding="utf-8"))
if body.get("status") != "LIVE_EVIDENCE_VERIFIED":
    raise SystemExit(f"C12 live evidence not verified: {body}")
if body.get("promotion_permitted") is not False or body.get("automatic_promotion") is not False:
    raise SystemExit(f"UNSAFE: C12 attempted authority promotion: {body}")
if body.get("ready_for_authority_adjudication") is not True:
    raise SystemExit(f"C12 is not ready for independent adjudication: {body}")
print("c12_live_evidence_verified_without_promotion")
PY
}

verify_manifest() {
  [[ -s "$ARTIFACT_ROOT/SHA256SUMS.txt" ]] || fail "sealed round has no manifest"
  [[ -s "$ARTIFACT_ROOT/SHA256SUMS.txt.sha256" ]] || fail "sealed round has no manifest seal"
  "$PYTHON" - "$ARTIFACT_ROOT" <<'PY' || fail "sealed bundle failed integrity/policy verification"
import hashlib,json,pathlib,sys,unicodedata
root=pathlib.Path(sys.argv[1]); manifest=root/"SHA256SUMS.txt"; seal=root/"SHA256SUMS.txt.sha256"
sealed=seal.read_text(encoding="utf-8").split()
if len(sealed)!=2 or sealed[1]!="SHA256SUMS.txt" or sealed[0]!=hashlib.sha256(manifest.read_bytes()).hexdigest():
    raise SystemExit("manifest self-seal mismatch")
listed=set(); errors=[]
for line in manifest.read_text(encoding="utf-8").splitlines():
    if not line: continue
    try: digest,rel=line.split(None,1)
    except ValueError: errors.append("malformed manifest line"); continue
    segments=rel.split("/")
    if (not rel or rel.startswith("/") or "\\" in rel or "" in segments
            or "." in segments or ".." in segments or unicodedata.normalize("NFC",rel)!=rel):
        errors.append("unsafe manifest path:"+rel); continue
    if rel in listed: errors.append("duplicate manifest path:"+rel); continue
    listed.add(rel); p=root/rel
    if p.is_symlink() or not p.is_file(): errors.append("missing or symlink:"+rel); continue
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest: errors.append("hash mismatch:"+rel)
actual={p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
        and p.name not in ("SHA256SUMS.txt","SHA256SUMS.txt.sha256")}
for p in root.rglob("*"):
    if p.is_symlink(): errors.append("symlink forbidden:"+p.relative_to(root).as_posix())
if actual!=listed: errors.append("manifest file set mismatch")
round_doc=json.loads((root/"ROUND.json").read_text(encoding="utf-8"))
summary=json.loads((root/"SUMMARY.json").read_text(encoding="utf-8"))
if round_doc.get("round_state")!="SEALED": errors.append("round is not SEALED")
if summary.get("runtime_verified") is not False: errors.append("runtime_verified overclaim")
if summary.get("production_certified") is not False: errors.append("production_certified overclaim")
if summary.get("authority_promotion") is not False: errors.append("authority promotion overclaim")
if errors: raise SystemExit("; ".join(errors))
print(f"manifest_integrity_ok files={len(listed)}")
PY
}

verify_all() {
  assert_subject_unchanged
  local current_state
  current_state="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["round_state"])' "$ROUND_DIR/ROUND.json")"
  [[ "$current_state" == "OPEN" ]] || fail "verify requires an OPEN round (found $current_state)"
  echo "== Canonical receipt re-verification =="
  "$PYTHON" scripts/architecture/rag_live_parity_receipt_guard.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" --subject-sha "$SUBJECT_SHA"

  run_live "$PYTHON" scripts/staging/s5_live_authority_closure.py verify \
    --subject-sha "$SUBJECT_SHA" \
    --decision-receipt "$S5_DIR/decision-live-closure.json" \
    --field-receipt "$S5_DIR/field-rls-live-evidence.json" \
    --kg-receipt "$S5_DIR/kg-runtime-parity.json" \
    --output "$S5_DIR/s5-live-authority-verified.json.new"
  finalize_json "$S5_DIR/s5-live-authority-verified.json"

  "$PYTHON" scripts/ci/c8_rag_production_certification.py \
    --receipt "$RAG_DIR/rag_live_parity_receipt.json" --subject-sha "$SUBJECT_SHA"
  "$PYTHON" scripts/ci/c9_decision_authority_certification.py \
    --receipt "$S5_DIR/decision-live-closure.json" --subject-sha "$SUBJECT_SHA"
  "$PYTHON" scripts/ci/c10_field_authority_certification.py \
    --receipt "$S5_DIR/field-rls-live-evidence.json" --subject-sha "$SUBJECT_SHA"

  echo "== C12 subject-bound live evidence re-verification =="
  "$PYTHON" scripts/ci/c12_governed_learning_promotion_certification.py \
    --receipt "$C12_DIR/c12-live-activation-receipt.json" \
    --subject-sha "$SUBJECT_SHA" \
    | tee "$C12_DIR/c12_result.reverified.json"
  "$PYTHON" - "$C12_DIR/c12_result.reverified.json" <<'PY'
import json,sys
body=json.load(open(sys.argv[1],encoding="utf-8"))
if body.get("status") != "LIVE_EVIDENCE_VERIFIED":
    raise SystemExit(f"C12 live evidence re-verification failed: {body}")
if body.get("promotion_permitted") is not False or body.get("automatic_promotion") is not False:
    raise SystemExit(f"UNSAFE: C12 attempted authority promotion: {body}")
print("c12_live_evidence_reverified_without_promotion")
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

  set_round_state SEALING
  "$PYTHON" - "$ARTIFACT_ROOT" "$SUBJECT_SHA" "$SUBJECT_TREE" \
    "$EXECUTION_ACTOR_KIND" "$EXECUTION_ACTOR_ID" "$ROUND_ID" <<'PY'
import hashlib,json,os,pathlib,sys,tempfile
root=pathlib.Path(sys.argv[1]); subject,tree,actor_kind,actor_id,round_id=sys.argv[2:7]
for p in root.rglob("*"):
    if p.is_symlink(): raise SystemExit(f"symlink forbidden in evidence: {p.relative_to(root)}")
    if p.is_file() and p.name.endswith(".new"):
        raise SystemExit(f"partial receipt forbidden at seal: {p.relative_to(root)}")
summary={
  'schema':'sahool.post-commit-live-acceptance-summary/v2',
  'round_id':round_id,
  'subject_sha':subject,
  'subject_tree':tree,
  'execution_actor':{'kind':actor_kind,'id':actor_id},
  'evidence_sealed':True,
  'runtime_verified':False,
  'production_certified':False,
  'gate01_authorized':False,
  'authority_promotion':False,
  'physical_shrink_authorized':False,
  'c12_live_activation_receipt_supported':True,
  'next_action':'independent human adjudication only after reviewing every canonical receipt; no automatic authority promotion',
}
(root/'SUMMARY.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
round_path=root/'ROUND.json'; round_doc=json.loads(round_path.read_text(encoding='utf-8'))
if round_doc.get('round_state')!='SEALING': raise SystemExit('round did not enter SEALING')
round_doc['round_state']='SEALED'
fd,tmp=tempfile.mkstemp(dir=root,prefix='ROUND.json.')
with os.fdopen(fd,'w',encoding='utf-8') as f:
    f.write(json.dumps(round_doc,indent=2,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
os.replace(tmp,round_path)
files=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and not p.is_symlink() and p.name not in ('SHA256SUMS.txt','SHA256SUMS.txt.sha256'):
        files.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}")
(root/'SHA256SUMS.txt').write_text('\n'.join(files)+'\n',encoding='utf-8')
(root/'SHA256SUMS.txt.sha256').write_text(
    hashlib.sha256((root/'SHA256SUMS.txt').read_bytes()).hexdigest()+'  SHA256SUMS.txt\n',encoding='utf-8')
print(json.dumps(summary,sort_keys=True))
PY
  verify_manifest
  cat "$ROUND_DIR/ROUND.json" | atomic_write "$ROUND_FILE"
  cmp -s "$ROUND_FILE" "$ROUND_DIR/ROUND.json" || fail "sealed pointer commit failed"
  echo "round_state=SEALED round_id=$ROUND_ID"
}

agent_all() {
  # An AI agent may collect and seal evidence, but cannot grant authority.
  # Both pins are mandatory: the agent must be told exactly which commit and
  # tree the operator intends to measure; deriving its own target is not an
  # independent provenance check.
  # Preconditions were already enforced before any artifact path was created.
  assert_subject_unchanged
  EXECUTION_ACTOR_KIND="ai-agent"
  EXECUTION_ACTOR_ID="$AGENT_EXECUTOR_ID"
  export EXECUTION_ACTOR_KIND EXECUTION_ACTOR_ID
  doctor
  preflight
  assert_subject_unchanged
  rag_collect
  s5_collect
  c11_collect
  c12_collect
  assert_subject_unchanged
  verify_all
}

case "$MODE" in
  doctor) doctor ;;
  preflight) preflight ;;
  rag) preflight; rag_collect ;;
  s5) preflight; s5_collect ;;
  c11) preflight; c11_collect ;;
  c12) preflight; c12_collect ;;
  verify) verify_all ;;
  check-seal)
    state="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["round_state"])' "$ROUND_DIR/ROUND.json")"
    [[ "$state" == "SEALED" ]] || fail "check-seal requires SEALED state (found $state)"
    verify_manifest
    echo "check-seal: PASS round_id=$ROUND_ID" ;;
  abort)
    state="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["round_state"])' "$ROUND_DIR/ROUND.json")"
    [[ "$state" != "SEALED" ]] || fail "SEALED evidence is final and cannot be aborted"
    mark_aborted
    echo "round_state=ABORTED round_id=$ROUND_ID" ;;
  recover)
    pointer_state="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8")).get("round_state"))' "$ROUND_FILE")"
    round_state="$("$PYTHON" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8")).get("round_state"))' "$ROUND_DIR/ROUND.json")"
    if [[ "$round_state" == "SEALED" ]] && ( verify_manifest ); then
      cat "$ROUND_DIR/ROUND.json" | atomic_write "$ROUND_FILE"
      echo "recover: completed interrupted SEALED pointer commit round_id=$ROUND_ID"
    elif [[ "$pointer_state" == "$round_state" && ( "$round_state" == "OPEN" || "$round_state" == "ABORTED" ) ]]; then
      echo "recover: coherent $round_state round; no repair required"
    else
      mark_aborted
      echo "recover: inconsistent or invalid round moved to ABORTED round_id=$ROUND_ID"
    fi ;;
  all)
    doctor
    preflight
    rag_collect
    s5_collect
    c11_collect
    c12_collect
    verify_all
    ;;
  agent) agent_all ;;
esac
