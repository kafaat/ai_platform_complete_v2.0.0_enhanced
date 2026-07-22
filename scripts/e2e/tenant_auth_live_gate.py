#!/usr/bin/env python3
"""Live tenant/auth gate for an already-running SAHOOL stack.

Expected env:
  BASE_URL=http://localhost
  SAHOOL_JWT=<valid user JWT>
  SAHOOL_AGENT_TOKEN=<internal agent token>
  TENANT_ID=<trusted tenant>
  OTHER_TENANT_ID=<different tenant>

The script intentionally checks reject paths as well as one internal-token happy path.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.getenv("BASE_URL", "http://localhost").rstrip("/")
JWT = os.getenv("SAHOOL_JWT", "")
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")
TENANT_ID = os.getenv("TENANT_ID", "tenant-live-a")
OTHER_TENANT_ID = os.getenv("OTHER_TENANT_ID", "tenant-live-b")
TIMEOUT = float(os.getenv("CURL_TIMEOUT", "10"))


def request(
    method: str, path: str, body: dict | None = None, headers: dict | None = None
) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json"}
    if JWT:
        hdrs["Authorization"] = f"Bearer {JWT}"
    hdrs.update(headers or {})
    req = urllib.request.Request(BASE_URL + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - user-provided internal URL by design
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def assert_status(label: str, got: int, expected: set[int]) -> bool:
    ok = got in expected
    print(f"{label}: status={got} expected={sorted(expected)} {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    checks: list[bool] = []

    status, _ = request(
        "POST",
        "/api/ai-agronomist/recommend",
        {
            "tenant_id": TENANT_ID,
            "field_id": "field-live",
            "question": "test",
            "current_field_state": {"forged": True},
        },
        {"X-Tenant-Id": TENANT_ID},
    )
    checks.append(
        assert_status("AI rejects client-supplied current_field_state", status, {401, 403})
    )

    status, _ = request(
        "POST",
        "/api/ai-agronomist/recommend",
        {
            "tenant_id": OTHER_TENANT_ID,
            "field_id": "field-live",
            "question": "test",
        },
        {"X-Tenant-Id": TENANT_ID},
    )
    checks.append(assert_status("AI rejects tenant_mismatch", status, {401, 403}))

    status, _ = request(
        "POST",
        "/api/rag/ingest",
        {"chunks": [{"tenant_id": TENANT_ID, "text": "x"}]},
        {"X-Tenant-Id": TENANT_ID},
    )
    checks.append(assert_status("RAG ingest requires service token", status, {401, 403}))

    status, _ = request(
        "POST",
        "/api/rag/search",
        {"tenant_id": OTHER_TENANT_ID, "query": "test", "top_k": 1},
        {"X-Tenant-Id": TENANT_ID},
    )
    checks.append(assert_status("RAG search rejects tenant_mismatch", status, {401, 403}))

    status, _ = request(
        "POST", "/api/knowledge-graph/nodes", {"id": "n1", "label": "x"}, {"X-Tenant-Id": TENANT_ID}
    )
    checks.append(assert_status("KG write requires service token", status, {401, 403}))

    if AGENT_TOKEN:
        status, _ = request(
            "POST",
            "/api/rag/ingest",
            {"chunks": [{"tenant_id": OTHER_TENANT_ID, "text": "x"}]},
            {
                "X-Tenant-Id": TENANT_ID,
                "X-Agent-Token": AGENT_TOKEN,
            },
        )
        checks.append(
            assert_status("RAG ingest rejects service-token tenant mismatch", status, {403})
        )
    else:
        print("RAG service-token mismatch check: SKIP (SAHOOL_AGENT_TOKEN not set)")

    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
