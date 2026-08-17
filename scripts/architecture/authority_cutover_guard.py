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
    tomb = forbidden.read_text(encoding="utf-8") if forbidden.is_file() else ""
    forbidden_symbols = (
        "class SQLiteAgGraphStore",
        "class GraphNode",
        "class GraphEdge",
        "import sqlite3",
    )
    if any(x in tomb for x in forbidden_symbols):
        out.append("sahool-platform still physically hosts KG store")
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
