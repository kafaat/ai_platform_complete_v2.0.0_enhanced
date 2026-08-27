#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/architecture/authority_cutovers.json"


def _text(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        raise SystemExit(f"authority_cutover_fail missing {rel}")
    return p.read_text(encoding="utf-8")


def findings() -> list[str]:
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    out = []
    if c.get("sequence") != ["decision", "field_management", "knowledge_graph"]:
        out.append("cutover sequence drift")
    a = c.get("authorities") or {}

    # Decision: capability may be declared, authority must remain interim until explicit gates.
    d = a.get("decision") or {}
    mode = _text("services/sahool-platform/api/decision_sor_mode.py")
    if d.get("declared_state") != "INTERIM":
        out.append("decision must remain INTERIM before explicit cutover")
    if d.get("cutover_capability") != "CUTOVER_CAPABLE":
        out.append("decision cutover capability not declared")
    if d.get("authority_state") != "NOT_YET_AUTHORITATIVE":
        out.append("decision prematurely authoritative")
    for token in (
        "decision_service_sor",
        "DECISION_SERVICE_PRODUCTION_CUTOVER_APPROVED",
        "PlatformDecisionWriteForbidden",
        "recommendation_outcomes",
    ):
        if token not in mode:
            out.append(f"decision mode contract missing {token}")
    static = _text("tests_v9/test_decision_sor_platform_revoke_static.py")
    if (
        "INSERT" not in static
        or "UPDATE" not in static
        or "DELETE" not in static
        or "SELECT" not in static
    ):
        out.append("decision revoke static proof incomplete")
    live = _text("services/decision-service/tests/test_decision_sor_db_privilege_cutover.py")
    for token in ("NOBYPASSRLS", "NOSUPERUSER", "SET ROLE", "REVOKE"):
        if token not in live:
            out.append(f"decision live cutover proof missing {token}")
    role_cert = _text("services/decision-service/decision_sor_role_certify.py")
    for token in (
        "WITH RECURSIVE walk",
        "membership_closure",
        "effective_table_privileges",
        "cutover_preflight_safe",
    ):
        if token not in role_cert:
            out.append(f"decision role certification missing {token}")
    revoke = _text("services/decision-service/platform_sor_revoke.py")
    for token in (
        "has_table_privilege",
        "privilege_closure_findings",
        "PrivilegeClosureError",
        "closure_verified",
    ):
        if token not in revoke:
            out.append(f"decision DB revoke postcondition missing {token}")
    decision_collector = _text("scripts/architecture/s5_decision_live_closure_receipt.py")
    decision_receipt_guard = _text("scripts/architecture/s5_decision_live_closure_receipt_guard.py")
    platform_health = _text("services/sahool-platform/api/routers/platform_health.py")
    # المُنتِجُ القانونيّ يشتقّ `SCHEMA` من الحارس (``guard.SCHEMA``) لا يُكرّر
    # حرفيّتَها — تفادياً لانحرافٍ بين نسختين من الاسم نفسِه. فمرساةُ هذا الحارسِ
    # على السلسلة الحرفيّة تُستبدَل بمرساةٍ على الاستيراد نفسِه؛ والحرفيّةُ تبقى
    # مفروضةً على ملفّ الحارس أدناه، وهو مصدرُها الوحيد.
    for token in (
        "guard.SCHEMA",
        "runtime-identity",
        "cutover/readiness",
        "platform_sor_revoke.py",
        "historical_zero_platform_writes_measured",
    ):
        if token not in decision_collector:
            out.append(f"decision live closure collector missing {token}")
    for token in (
        "sahool.s5-decision-live-closure/v1",
        "historical_zero_writes_overclaim",
        "effective_write_not_denied",
        "platform_not_effectively_demoted",
    ):
        if token not in decision_receipt_guard:
            out.append(f"decision live closure receipt guard missing {token}")
    for token in ("get_platform_decision_sor_mode", 'body["decision_sor"]'):
        if token not in platform_health:
            out.append(f"platform readyz decision SoR evidence missing {token}")
    if "SUBJECT_BOUND_LIVE_DECISION_CLOSURE_RECEIPT_REQUIRED" not in (
        d.get("blocking_reasons") or []
    ):
        out.append("decision subject-bound live closure blocker missing")

    # Field: no promotion without restricted-role behavioral RLS proof contract.
    f = a.get("field_management") or {}
    field_test = _text(
        "services/field-management-service/tests/test_field_management_pg_isolation_integration.py"
    )
    if f.get("authority_state") != "NOT_YET_AUTHORITATIVE":
        out.append("field authority promoted without accepted live proof")
    if f.get("cutover_capability") != "NOT_YET_CUTOVER_CAPABLE":
        out.append("field cutover capability must remain blocked until live proof")
    if (
        "NOBYPASSRLS" not in field_test
        or "sahool_app" not in field_test
        or "pytest.skip" not in field_test
    ):
        out.append("field RLS proof does not fail honestly when restricted role is absent")
    field_gate = _text("scripts/staging/field_management_live_gate.sh")
    field_receipt_guard = _text("scripts/architecture/s4_field_rls_receipt_guard.py")
    for token in ("rolsuper", "rolbypassrls", "pg_auth_members", "FIELD_RLS_EVIDENCE_OUT"):
        if token not in field_gate:
            out.append(f"field live gate missing {token}")
    for token in (
        "sahool.s4-field-rls-live-evidence/v2",
        "reachable_privileged_role_count",
        "cross_tenant_http",
    ):
        if token not in field_receipt_guard:
            out.append(f"field receipt guard missing {token}")
    if "LIVE_APPLICATION_ROLE_RLS_PROOF_REQUIRED" not in (f.get("blocking_reasons") or []):
        out.append("field live application-role blocker missing")

    # KG: physical implementation belongs to the KG service, not sahool-platform.
    k = a.get("knowledge_graph") or {}
    canonical = ROOT / str(k.get("canonical_store", ""))
    forbidden = ROOT / str(k.get("forbidden_store", ""))
    if not canonical.is_file():
        out.append("KG canonical store missing from owner service")
    main = _text("services/knowledge-graph/main.py")
    if "from kg_store import" not in main:
        out.append("KG service does not consume its owned store")
    # الملكيّة الفيزيائيّة تشمل الشحن: وحدةٌ يستوردها `main.py` من جذر الصورة ولا
    # ينسخها Dockerfile تنهار عند الإقلاع. مُشتقٌّ من الاستيرادات لا من قائمة يدويّة —
    # قائمةٌ ثانية تُنسى كما نُسي `kg_store` نفسه.
    dockerfile = _text("services/knowledge-graph/Dockerfile")
    service_dir = canonical.parent
    for name in sorted(set(re.findall(r"^(?:from|import)\s+([A-Za-z_]\w*)", main, re.M))):
        if not (service_dir / f"{name}.py").is_file():
            continue
        if f"COPY services/knowledge-graph/{name}.py" not in dockerfile:
            out.append(f"KG image does not ship an imported owned module: {name}.py")
    # End-state S4/S5: even the compatibility tombstone is removed.  Physical ownership
    # is not fully shrunk while the old platform store path remains addressable.
    if forbidden.exists():
        out.append("legacy sahool-platform KG store path still exists")
    kg_collector = _text("scripts/staging/kg_runtime_parity_collector.py")
    kg_receipt_guard = _text("scripts/architecture/s4_kg_runtime_parity_receipt_guard.py")
    for token in (
        "source_identity_match",
        "minimum_evidence_met",
        "consumer_fingerprint_sha256",
        "local_subject_sha",
        "checkout_subject_sha_mismatch",
    ):
        if token not in kg_collector:
            out.append(f"KG live collector missing {token}")
    for token in (
        "sahool.s4-kg-runtime-parity/v2",
        "deployed source identity mismatch",
        "not every parity case produced live evidence",
        "collector checkout subject SHA mismatch",
    ):
        if token not in kg_receipt_guard:
            out.append(f"KG receipt guard missing {token}")
    # repository-wide production imports of the old platform implementation are forbidden.
    # مرتَّبة: ترتيب `rglob` يتبع نظام الملفّات، ورسالة الحارس تحمل مسارات — فبلا فرز
    # يختلف مخرَجه بين آلة وأخرى على الشجرة نفسها.
    for p in sorted((ROOT / "services").rglob("*.py")):
        if p == forbidden:
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "core.knowledge_graph.sqlite_graph" in txt:
            out.append(f"legacy KG implementation import remains: {p.relative_to(ROOT)}")

    return out


def main() -> int:
    f = findings()
    if f:
        print("authority_cutover_fail")
        for x in f:
            print(" -", x)
        return 1
    print("authority_cutover_ok decision=CUTOVER_CAPABLE/INTERIM field=BLOCKED kg=SERVICE_OWNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
