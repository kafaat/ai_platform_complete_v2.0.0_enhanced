from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_snapshot_payload_is_json_serializable_with_date_values():
    import sys

    sys.path.insert(0, str(ROOT))
    from core.evidence_snapshot import build_snapshot_payload

    analyze = {
        "correlation_id": "corr-1",
        "confidence": Decimal("0.781"),
        "operational_truths": {"effective_status": "good"},
        "policy_decision": {"action_type": "irrigate"},
        "evidence_graph": {
            "summary": {"evidence_count": 1, "has_recommendation": True},
            "generated_at": datetime(2026, 7, 8, 19, 47, tzinfo=UTC),
            "nodes": [
                {
                    "id": "evidence:scene",
                    "source": "raster-service",
                    "acquisition_date": date(2026, 7, 5),
                    "tenant_uuid": UUID("00000000-0000-0000-0000-000000000001"),
                    "api_token": "must-not-persist",
                }
            ],
            "knowledge_gaps": [{"gap": "soil", "seen_on": date(2026, 7, 8)}],
        },
    }

    payload = build_snapshot_payload(analyze)
    assert payload is not None
    encoded = json.dumps(payload["evidence_graph"], ensure_ascii=False)
    assert "2026-07-05" in encoded
    assert "must-not-persist" not in encoded
    assert "api_token" not in encoded
    assert json.dumps(payload["knowledge_gaps"], ensure_ascii=False)


def test_field_intelligence_persist_uses_json_default_str_guard():
    source = (ROOT / "api" / "routers" / "field_intelligence.py").read_text()
    assert 'json.dumps(payload["evidence_graph"], ensure_ascii=False, default=str)' in source
    assert 'json.dumps(payload["evidence_sources"], ensure_ascii=False, default=str)' in source
    assert 'json.dumps(payload["knowledge_gaps"], ensure_ascii=False, default=str)' in source


def test_platform_metrics_endpoint_exists_for_prometheus_scrape_guard():
    main_path = ROOT / "api" / "main.py"
    tree = ast.parse(main_path.read_text())
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if (
                        dec.func.attr == "get"
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                    ):
                        routes.append((dec.args[0].value, node.name))
    assert ("/metrics", "metrics") in routes
    text = main_path.read_text()
    assert "PlainTextResponse" in text
    assert "sahool_platform_up 1" in text
