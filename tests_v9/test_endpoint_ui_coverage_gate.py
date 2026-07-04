"""حارس عقد «backend ⇒ واجهة»: كلّ endpoint جوهريّ يبقى بدليل واجهة/hook.

يستدعي منطق scripts/ci/endpoint_ui_coverage_gate.py نفسه (لا نسخ) — إن أُزيل
استدعاء واجهة لمسار جوهريّ (مثل farm-ledger/profitability أو crop-cards) يفشل
الحارس محليّاً وفي CI قبل أن تصبح القدرة الخلفيّة يتيمة عن المستخدم من جديد.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "ci" / "endpoint_ui_coverage_gate.py"
CONFIG = REPO / "config" / "endpoint_ui_coverage.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("endpoint_ui_coverage_gate_mod", GATE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_config_is_valid_and_nonempty() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["core_endpoints"], "العقد فارغ — يجب أن يلزم مسارات جوهريّة"
    assert cfg["classifications"], "التصنيف فارغ"
    audiences = {"farmer", "agronomist", "manager", "admin", "internal"}
    for entry in cfg["core_endpoints"]:
        assert entry["audience"] in audiences, entry
        assert entry["evidence"].startswith("/"), entry
        # المسارات الداخليّة لا تُطالَب بواجهة مستخدم — لا يجوز إلزامها في العقد.
        assert entry["audience"] != "internal", f"internal endpoint في العقد الملزم: {entry}"
    for rule in cfg["classifications"]:
        assert rule["audience"] in audiences, rule


@pytest.mark.unit
def test_every_core_endpoint_has_frontend_evidence() -> None:
    mod = _load_gate()
    assert mod.run_gate() == 0, "endpoint جوهريّ فقد دليله في الواجهة — راجع مخرجات البوّابة"


@pytest.mark.unit
def test_backend_route_collector_finds_platform_routes() -> None:
    """اكتشاف المسارات يعمل فعلاً (لا بوّابة فارغة تنجح بالصمت)."""
    mod = _load_gate()
    routes = mod.collect_backend_routes()
    assert len(routes) > 300, f"جامع المسارات وجد {len(routes)} فقط — انكسر النمط؟"
    assert any(p.startswith("/api/v1/farm-ledger/") for p in routes)
    assert any(p.startswith("/api/v1/crop-cards") for p in routes)
