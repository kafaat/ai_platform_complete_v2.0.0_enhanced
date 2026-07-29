#!/usr/bin/env python3
"""Conservatively link SAHOOL capabilities to repository services, APIs, tests and consumers.

Only deterministic keyword/path matches above a confidence threshold are applied. All candidates,
including rejected/ambiguous ones, are emitted for review.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
ROUTES = ROOT / "route_inventory.csv"
SERVICES = ROOT / "service_inventory.csv"
GENERATED = ROOT / "capabilities/generated"

# Strong domain vocabulary. Tokens intentionally avoid generic words such as data, current, or management.
RULES: dict[str, dict[str, list[str]]] = {
    "FM-001": {
        "tokens": ["tenant", "organization", "auth"],
        "services": ["auth", "field-management-service"],
    },
    "FM-002": {"tokens": ["farm", "farms"], "services": ["field-management-service"]},
    "FM-003": {"tokens": ["field", "fields", "boundary"], "services": ["field-management-service"]},
    "FM-004": {"tokens": ["season", "crop-season"], "services": ["field-management-service"]},
    "FM-005": {
        "tokens": ["crop", "cultivar", "variety"],
        "services": ["crop-intelligence-service"],
    },
    "FM-006": {"tokens": ["economics", "cost", "profit", "budget"], "services": ["billing-core"]},
    "FM-007": {
        "tokens": ["inventory", "procurement", "warehouse"],
        "services": ["inventory-service"],
    },
    "FM-008": {"tokens": ["erp", "accounting", "odoo"], "services": ["odoo-bridge"]},
    "GIS-001": {
        "tokens": ["geometry", "boundary", "polygon", "validity"],
        "services": ["field-management-service"],
    },
    "GIS-002": {"tokens": ["layer", "layers", "map"], "services": ["raster-service"]},
    "GIS-003": {
        "tokens": ["terrain", "dem", "slope", "hillshade", "contour"],
        "services": ["raster-service"],
    },
    "GIS-004": {"tokens": ["spatial", "zonal", "geospatial"], "services": ["raster-service"]},
    "SAT-001": {"tokens": ["scene", "stac", "cdse", "satellite"], "services": ["raster-service"]},
    "SAT-002": {"tokens": ["truecolor", "true-color", "rgb"], "services": ["raster-service"]},
    "SAT-003": {"tokens": ["ndvi"], "services": ["raster-service", "vegetation-analysis-service"]},
    "SAT-004": {"tokens": ["ndmi"], "services": ["raster-service", "vegetation-analysis-service"]},
    "SAT-005": {"tokens": ["cloud", "scl", "qa-mask"], "services": ["raster-service"]},
    "SAT-006": {
        "tokens": ["timeline", "historical", "backfill", "thumbnail"],
        "services": ["raster-service"],
    },
    "SAT-007": {
        "tokens": ["change-detection", "change_detection", "change"],
        "services": ["raster-service"],
    },
    "SAT-008": {
        "tokens": ["stress-zone", "stress_zone", "stress"],
        "services": ["vegetation-analysis-service"],
    },
    "SAT-009": {"tokens": ["cog", "tilejson", "tile", "raster"], "services": ["raster-service"]},
    "WX-001": {
        "tokens": ["weather/current", "current-weather", "current_weather"],
        "services": ["weather-service"],
    },
    "WX-002": {"tokens": ["forecast"], "services": ["weather-service"]},
    "WX-003": {
        "tokens": ["weather/history", "historical-weather", "weather_history"],
        "services": ["weather-service"],
    },
    "WX-004": {"tokens": ["et0", "evapotranspiration"], "services": ["weather-service"]},
    "WX-005": {
        "tokens": ["vpd", "vapour-pressure", "vapor-pressure"],
        "services": ["weather-service"],
    },
    "WX-006": {"tokens": ["gdd", "growing-degree"], "services": ["weather-service"]},
    "WX-007": {"tokens": ["frost", "heat-risk", "heat_risk"], "services": ["weather-service"]},
    "WX-008": {
        "tokens": ["operation-window", "operation_window", "spray-window", "harvest-window"],
        "services": ["weather-service"],
    },
    "WX-009": {
        "tokens": ["disease", "blight", "mildew", "rust"],
        "services": ["weather-service", "crop-intelligence-service"],
    },
    "WX-010": {
        "tokens": ["weather-quality", "weather_quality", "provenance", "canonical-weather"],
        "services": ["weather-service"],
    },
    "SOIL-001": {"tokens": ["soil-profile", "soil_profile"], "services": ["soil-service"]},
    "SOIL-002": {
        "tokens": ["soil-sampling", "soil_sampling", "sampling-plan"],
        "services": ["soil-service"],
    },
    "SOIL-003": {
        "tokens": ["laboratory", "lab-result", "lab_result"],
        "services": ["soil-service"],
    },
    "SOIL-004": {
        "tokens": ["soil-analysis", "soil_analysis", "nutrient", "organic-matter"],
        "services": ["soil-service"],
    },
    "SOIL-005": {
        "tokens": ["field-capacity", "wilting", "taw", "soil-water"],
        "services": ["soil-service", "irrigation-smart"],
    },
    "IRR-001": {
        "tokens": ["water-source", "water_source", "well"],
        "services": ["sahool-platform"],
    },
    "IRR-002": {
        "tokens": ["water-quality", "water_quality", "water-sample"],
        "services": ["sahool-platform"],
    },
    "IRR-003": {
        "tokens": ["field-water-source", "field_water_source", "source-binding"],
        "services": ["sahool-platform"],
    },
    "IRR-004": {
        "tokens": ["water-balance", "water_balance", "depletion"],
        "services": ["sahool-platform"],
    },
    "IRR-005": {
        "tokens": ["irrigation-recommend", "irrigation_recommend", "recommendation"],
        "services": ["sahool-platform"],
    },
    "IRR-006": {
        "tokens": ["irrigation-schedule", "irrigation_schedule", "schedule"],
        "services": ["sahool-platform"],
    },
    "IRR-007": {
        "tokens": ["pump", "valve", "actuator", "command"],
        "services": ["actuator-service", "sahool-platform"],
    },
    "IRR-008": {
        "tokens": ["irrigation-receipt", "execution-verification", "execution_verification"],
        "services": ["sahool-platform", "decision-service"],
    },
    "IRR-009": {
        "tokens": ["sar", "salinity", "sodicity", "water-suitability", "water_suitability"],
        "services": ["sahool-platform"],
    },
    "IRR-010": {"tokens": ["leaching", "drainage"], "services": ["sahool-platform"]},
    "PA-001": {
        "tokens": ["management-zone", "management_zone", "productivity-zone", "productivity_zone"],
        "services": ["vegetation-analysis-service"],
    },
    "PA-002": {
        "tokens": ["vra", "prescription", "variable-rate", "variable_rate"],
        "services": ["vegetation-analysis-service"],
    },
    "PA-003": {"tokens": ["yield-map", "yield_map", "yield-import"], "services": []},
    "PA-004": {"tokens": ["as-applied", "as_applied", "applied-map"], "services": []},
    "PA-005": {"tokens": ["telemetry", "isoxml", "machine-data", "machine_data"], "services": []},
    "OPS-001": {"tokens": ["task", "tasks"], "services": ["sahool-platform"]},
    "OPS-002": {"tokens": ["work-order", "work_order"], "services": ["sahool-platform"]},
    "OPS-003": {"tokens": ["scouting", "scout"], "services": ["field-management-service"]},
    "OPS-004": {
        "tokens": ["field-form", "field_form", "forms"],
        "services": ["field-management-service"],
    },
    "OPS-005": {"tokens": ["offline", "sync-queue", "sync_queue"], "services": []},
    "OPS-006": {"tokens": ["equipment", "machinery"], "services": ["sahool-platform"]},
    "OPS-007": {"tokens": ["maintenance", "service-record"], "services": ["sahool-platform"]},
    "OPS-008": {
        "tokens": ["worker-identity", "worker_identity", "workforce"],
        "services": ["auth"],
    },
    "DEC-001": {
        "tokens": ["decision-evidence", "decision_evidence", "evidence"],
        "services": ["decision-service"],
    },
    "DEC-002": {
        "tokens": ["candidate", "recommendation-candidate"],
        "services": ["decision-service"],
    },
    "DEC-003": {"tokens": ["approval", "approve", "review"], "services": ["decision-service"]},
    "DEC-004": {
        "tokens": ["execution-request", "execution_request"],
        "services": ["decision-service"],
    },
    "DEC-005": {
        "tokens": ["dispatch-authorization", "dispatch_authorization", "dispatch"],
        "services": ["decision-service"],
    },
    "DEC-006": {
        "tokens": ["execution-receipt", "execution_receipt", "delivery-receipt"],
        "services": ["decision-service"],
    },
    "DEC-007": {"tokens": ["outcome", "outcome-record"], "services": ["decision-service"]},
    "DEC-008": {
        "tokens": ["attribution", "learning-attribution", "learning_attribution"],
        "services": ["decision-service"],
    },
    "DEC-009": {"tokens": ["calibration", "evaluation-run"], "services": ["decision-service"]},
    "DEC-010": {
        "tokens": ["model-activation", "model_activation", "promotion", "rollback"],
        "services": ["decision-service"],
    },
    "SEC-001": {
        "tokens": ["rls", "row-level", "tenant-isolation"],
        "services": ["field-management-service"],
    },
    "SEC-002": {
        "tokens": ["tenant-assertion", "tenant_assertion", "signed-tenant"],
        "services": ["field-management-service"],
    },
    "SEC-003": {
        "tokens": ["worker-identity", "worker_identity", "service-identity"],
        "services": ["auth"],
    },
    "SEC-004": {"tokens": ["mfa", "totp", "recovery-code"], "services": ["auth"]},
    "SEC-005": {"tokens": ["audit", "audit-log", "audit_log"], "services": ["auth"]},
    "SEC-006": {
        "tokens": ["service-token", "service_token", "internal-token"],
        "services": ["auth"],
    },
    "SEC-007": {
        "tokens": ["decision-sor", "decision_sor", "platform-sor", "platform_sor"],
        "services": ["decision-service"],
    },
    "SEC-008": {"tokens": ["fail-closed", "secret", "production-guard"], "services": ["auth"]},
    "INT-001": {"tokens": ["openapi", "sdk", "public-api"], "services": ["sahool-platform"]},
    "INT-002": {
        "tokens": ["nats", "jetstream", "event-bus", "event_bus"],
        "services": ["sahool-platform"],
    },
    "INT-003": {"tokens": ["iot", "sensor", "mqtt"], "services": ["actuator-service"]},
    "INT-004": {
        "tokens": ["isoxml", "john-deere", "trimble", "machinery-integration"],
        "services": [],
    },
}

DEPENDENCIES = {
    "FM-003": ["FM-002"],
    "FM-004": ["FM-003", "FM-005"],
    "FM-006": ["FM-002", "FM-004"],
    "FM-008": ["FM-006"],
    "GIS-001": ["FM-003"],
    "GIS-002": ["FM-003"],
    "GIS-003": ["GIS-002"],
    "GIS-004": ["GIS-001", "GIS-002"],
    "SAT-002": ["SAT-001"],
    "SAT-003": ["SAT-001", "SAT-005"],
    "SAT-004": ["SAT-001", "SAT-005"],
    "SAT-005": ["SAT-001"],
    "SAT-006": ["SAT-001", "SAT-009"],
    "SAT-007": ["SAT-003", "SAT-006"],
    "SAT-008": ["SAT-003", "SAT-004"],
    "SAT-009": ["SAT-001"],
    "WX-002": ["WX-010"],
    "WX-003": ["WX-010"],
    "WX-004": ["WX-001", "WX-010"],
    "WX-005": ["WX-001", "WX-010"],
    "WX-006": ["WX-001", "WX-010"],
    "WX-007": ["WX-002"],
    "WX-008": ["WX-002"],
    "WX-009": ["WX-002"],
    "SOIL-002": ["FM-003"],
    "SOIL-003": ["SOIL-002"],
    "SOIL-004": ["SOIL-003"],
    "SOIL-005": ["SOIL-001", "SOIL-004"],
    "IRR-002": ["IRR-001"],
    "IRR-003": ["FM-003", "IRR-001"],
    "IRR-004": ["IRR-003", "SOIL-005", "WX-004"],
    "IRR-005": ["IRR-004"],
    "IRR-006": ["IRR-005"],
    "IRR-007": ["IRR-006", "DEC-005"],
    "IRR-008": ["IRR-007", "DEC-006"],
    "IRR-009": ["IRR-002", "SOIL-004"],
    "IRR-010": ["IRR-009", "SOIL-005"],
    "PA-001": ["SAT-003", "SAT-004", "GIS-004"],
    "PA-002": ["PA-001"],
    "PA-003": ["FM-003"],
    "PA-004": ["PA-002"],
    "PA-005": ["OPS-006"],
    "OPS-002": ["OPS-001"],
    "OPS-003": ["FM-003"],
    "OPS-004": ["FM-003"],
    "OPS-005": ["OPS-003", "OPS-004"],
    "OPS-007": ["OPS-006"],
    "DEC-002": ["DEC-001"],
    "DEC-003": ["DEC-002"],
    "DEC-004": ["DEC-003"],
    "DEC-005": ["DEC-004"],
    "DEC-006": ["DEC-005"],
    "DEC-007": ["DEC-006"],
    "DEC-008": ["DEC-007"],
    "DEC-009": ["DEC-008"],
    "DEC-010": ["DEC-009"],
    "SEC-002": ["SEC-001"],
    "SEC-003": ["SEC-006"],
    "SEC-007": ["SEC-001"],
    "INT-004": ["PA-005"],
}

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
}
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".dart", ".sql", ".yaml", ".yml", ".md"}


def normalize(value: str) -> str:
    return value.lower().replace("_", "-")


def token_match(text: str, token: str) -> bool:
    t = normalize(text)
    tok = normalize(token)
    if "/" in tok or "-" in tok:
        return tok in t
    return re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", t) is not None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def discover_files() -> list[str]:
    results: list[str] = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        results.append(rel.as_posix())
    results.sort()
    return results


def classify_consumer(path: str) -> str | None:
    n = normalize(path)
    if path.endswith(".dart") or "/mobile/" in f"/{n}/" or n.startswith("apps/mobile"):
        return "mobile_consumers"
    if path.endswith((".tsx", ".ts", ".jsx", ".js")) and any(
        x in n for x in ("frontend", "web", "dashboard", "apps/")
    ):
        return "ui_consumers"
    return None


def score_file(path: str, tokens: list[str], cid: str) -> int:
    score = sum(2 if token_match(path, tok) else 0 for tok in tokens)
    if "/test" in normalize(path) or Path(path).name.startswith("test_"):
        score += 1
    if cid.lower().replace("-", "_") in normalize(path).replace("-", "_"):
        score += 5
    return score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when registry links differ from deterministic linker output",
    )
    parser.add_argument("--threshold", type=int, default=2)
    args = parser.parse_args()

    original = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data = json.loads(json.dumps(original))
    routes = read_csv(ROUTES)
    services = read_csv(SERVICES)
    all_files = discover_files()
    service_by_name = {r["service"]: r for r in services}
    candidates: list[dict[str, object]] = []

    for cap in data["capabilities"]:
        cid = cap["id"]
        rule = RULES.get(cid, {"tokens": [], "services": []})
        tokens = rule["tokens"]
        linked_services: list[str] = []
        linked_apis: list[str] = []
        tests: list[str] = []
        ui: list[str] = []
        mobile: list[str] = []

        # Explicit service names are accepted only when present in inventory and main exists.
        for name in rule["services"]:
            row = service_by_name.get(name)
            if row and row.get("main") and (ROOT / row["main"]).exists():
                linked_services.append(row["main"])
                candidates.append(
                    {
                        "capability_id": cid,
                        "kind": "service",
                        "value": row["main"],
                        "score": 10,
                        "decision": "applied",
                    }
                )

        # APIs require token evidence in route path/function/file and matching service when explicit services exist.
        accepted_service_names = set(rule["services"])
        for route in routes:
            haystack = " ".join(
                [route.get("path", ""), route.get("function", ""), route.get("file", "")]
            )
            hits = sum(1 for tok in tokens if token_match(haystack, tok))
            service_bonus = 1 if route.get("service") in accepted_service_names else 0
            score = hits * 2 + service_bonus
            if score >= args.threshold:
                value = f"{route['method']} {route['path']} @ {route['file']}:{route['line']}"
                linked_apis.append(value)
                candidates.append(
                    {
                        "capability_id": cid,
                        "kind": "api",
                        "value": value,
                        "score": score,
                        "decision": "applied",
                    }
                )

        # Repository files: apply only tests and UI/mobile; implementation files become evidence candidates.
        evidence_paths: list[str] = []
        for path in all_files:
            score = score_file(path, tokens, cid)
            if score < args.threshold:
                continue
            n = normalize(path)
            if (
                "/test" in f"/{n}"
                or Path(path).name.startswith("test_")
                or n.endswith("_test.dart")
            ):
                tests.append(path)
                candidates.append(
                    {
                        "capability_id": cid,
                        "kind": "test",
                        "value": path,
                        "score": score,
                        "decision": "applied",
                    }
                )
            else:
                consumer = classify_consumer(path)
                if consumer == "ui_consumers":
                    ui.append(path)
                    candidates.append(
                        {
                            "capability_id": cid,
                            "kind": "ui",
                            "value": path,
                            "score": score,
                            "decision": "applied",
                        }
                    )
                elif consumer == "mobile_consumers":
                    mobile.append(path)
                    candidates.append(
                        {
                            "capability_id": cid,
                            "kind": "mobile",
                            "value": path,
                            "score": score,
                            "decision": "applied",
                        }
                    )
                elif path.startswith(("services/", "apps/services/", "shared/", "migrations/")):
                    evidence_paths.append(path)

        def uniq(values: list[str], limit: int) -> list[str]:
            return sorted(dict.fromkeys(values))[:limit]

        if args.apply or args.check:
            cap["services"] = uniq(linked_services, 8)
            cap["apis"] = uniq(linked_apis, 40)
            cap["tests"] = uniq(tests, 25)
            cap["ui_consumers"] = uniq(ui, 20)
            cap["mobile_consumers"] = uniq(mobile, 20)
            cap["dependencies"] = DEPENDENCIES.get(cid, cap.get("dependencies", []))
            # Add a small deterministic evidence set, preserving existing non-duplicate evidence.
            existing = {(e.get("type"), e.get("path")) for e in cap.get("evidence", [])}
            for path in uniq(evidence_paths, 5):
                if ("repository", path) not in existing:
                    cap.setdefault("evidence", []).append({"type": "repository", "path": path})
            if len(linked_services) == 1:
                cap["owner"] = (
                    Path(linked_services[0]).parts[1]
                    if linked_services[0].startswith("services/")
                    else linked_services[0]
                )
                if cap["owner"] == "odoo-bridge":
                    cap["owner"] = "erp-bridge"
            elif linked_services:
                cap["owner"] = (
                    "+".join(
                        sorted(
                            {Path(p).parts[1] for p in linked_services if p.startswith("services/")}
                        )
                    )
                    or "PLATFORM"
                )
            # Evidence confidence is based on explicit traceability, not maturity inflation.
            linked_surfaces = sum(
                bool(x) for x in (linked_services, linked_apis, tests, ui, mobile)
            )
            if linked_services and linked_apis and tests:
                cap["confidence"] = "high"
            elif linked_surfaces >= 2:
                cap["confidence"] = "medium"
            else:
                cap["confidence"] = "low"
            # Linkage is traceability, not certification. Never promote or downgrade
            # maturity/status/evidence_level from repository-shape matches alone.
            cap["rationale"] = (
                f"Capability linkage generated conservatively from repository inventories: "
                f"services={len(cap['services'])}, apis={len(cap['apis'])}, tests={len(cap['tests'])}, "
                f"ui={len(cap['ui_consumers'])}, mobile={len(cap['mobile_consumers'])}. "
                "Runtime and production certification remain manual evidence gates."
            )

    registry_rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    candidate_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        candidate_buffer,
        fieldnames=["capability_id", "kind", "value", "score", "decision"],
    )
    writer.writeheader()
    candidates.sort(
        key=lambda row: (
            str(row["capability_id"]),
            str(row["kind"]),
            str(row["value"]),
            int(row["score"]),
            str(row["decision"]),
        )
    )
    writer.writerows(candidates)
    candidates_rendered = candidate_buffer.getvalue()
    cand_path = GENERATED / "capability_link_candidates.csv"

    if args.check:
        drift: list[str] = []
        if registry_rendered != REGISTRY.read_text(encoding="utf-8"):
            drift.append(str(REGISTRY.relative_to(ROOT)))
        if cand_path.exists():
            with cand_path.open(encoding="utf-8", newline="") as handle:
                existing_candidates = handle.read()
        else:
            existing_candidates = None
        if candidates_rendered != existing_candidates:
            drift.append(str(cand_path.relative_to(ROOT)))
        if drift:
            print("capability_linkage_drift_detected: " + ", ".join(drift))
            return 1

    if args.apply:
        GENERATED.mkdir(parents=True, exist_ok=True)
        REGISTRY.write_text(registry_rendered, encoding="utf-8")
        cand_path.write_text(candidates_rendered, encoding="utf-8")

    print(
        json.dumps(
            {
                "capabilities": len(data["capabilities"]),
                "candidates": len(candidates),
                "applied": bool(args.apply),
                "checked": bool(args.check),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
