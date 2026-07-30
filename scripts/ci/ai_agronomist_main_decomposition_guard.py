#!/usr/bin/env python3
"""Guard the ai-agronomist main.py decomposition boundary.

The AI agronomist runtime is allowed to keep FastAPI routes and thin compatibility
wrappers in main.py. Evidence assembly, grounding, policy envelope enforcement, and
tool-loop orchestration must live in ai_evidence_runtime.py so main.py does not grow
back into a large monolith.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "ai_agronomist"
MAIN = SERVICE / "main.py"
EVIDENCE_RUNTIME = SERVICE / "ai_evidence_runtime.py"
MAX_MAIN_LOC = 650
REQUIRED_RUNTIME_FUNCS = {
    "_fetch_canonical_field_state",
    "_extract_evidence_ids",
    "_confidence_from_payloads",
    "_record_ai_advice_event",
    "_generation_allowed",
    "_utc_timestamp",
    "_build_agent_tool_fetcher",
    "_extract_ai_context_pack",
    "_source_count",
    "_ai_context_memory_lines",
    "_field_memory_evidence_ids",
    "_evidence_sources",
    "_grounding_context_text",
    "build_evidence_response",
}
MAIN_FORBIDDEN_IMPLEMENTATIONS = {
    "_fetch_canonical_field_state",
    "_build_agent_tool_fetcher",
    "_grounding_context_text",
    "_record_ai_advice_event",
}


def fail(msg: str) -> None:
    print(f"ai_agronomist_decomposition_guard_failed: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _has_function(src: str, name: str) -> bool:
    return bool(re.search(rf"^(async\s+def|def)\s+{re.escape(name)}\b", src, re.M))


def main() -> None:
    main_src = MAIN.read_text(encoding="utf-8")
    runtime_src = EVIDENCE_RUNTIME.read_text(encoding="utf-8") if EVIDENCE_RUNTIME.exists() else ""
    loc = len(main_src.splitlines())
    if loc > MAX_MAIN_LOC:
        fail(
            f"services/ai_agronomist/main.py LOC {loc} exceeds {MAX_MAIN_LOC}; keep evidence runtime decomposed"
        )
    if not EVIDENCE_RUNTIME.exists():
        fail("services/ai_agronomist/ai_evidence_runtime.py missing")
    for name in sorted(REQUIRED_RUNTIME_FUNCS):
        if not _has_function(runtime_src, name):
            fail(f"ai_evidence_runtime.py missing {name}")
    for name in sorted(MAIN_FORBIDDEN_IMPLEMENTATIONS):
        if _has_function(main_src, name):
            fail(f"{name} implementation drifted back into main.py")
    if "build_evidence_response as _build_evidence_response_runtime" not in main_src:
        fail(
            "main.py must delegate query/chat/explain/recommend through ai_evidence_runtime.build_evidence_response"
        )
    if "save_agent_tool_audit=_save_agent_tool_audit" not in main_src:
        fail("main.py wrapper must inject audit store callback into evidence runtime")
    if "save_pending_approval=_save_pending_approval" not in main_src:
        fail("main.py wrapper must inject approval store callback into evidence runtime")
    for route in (
        '@app.post("/v1/query")',
        '@app.post("/v1/chat")',
        '@app.post("/v1/explain")',
        '@app.post("/v1/recommend")',
    ):
        if route not in main_src:
            fail(f"missing route decorator {route}")
    print("✓ ai-agronomist main decomposition guard passed")


if __name__ == "__main__":
    main()
