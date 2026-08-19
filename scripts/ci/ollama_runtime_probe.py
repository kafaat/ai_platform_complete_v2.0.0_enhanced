#!/usr/bin/env python3
"""Read-only Ollama runtime certification probe for SAHOOL.

The probe never pulls, creates, copies, or deletes models.  It verifies the
running Ollama version, the expected local model inventory, and optionally runs
one embedding and one OpenAI-compatible chat inference.

Exit codes:
  0  all requested checks passed
  2  runtime reachable but a contract check failed
  3  runtime could not be reached / response was malformed
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_BASE_URL = "http://sahool-ollama:11434"
DEFAULT_EXPECTED_VERSION = "0.32.5"
DEFAULT_CHAT_MODEL = "llama3.2:3b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _request_json(
    base_url: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - configured internal runtime
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw) if raw else {}
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: expected JSON object")
    return parsed


def _canonical_model_id(value: str) -> str:
    value = (value or "").strip()
    return value[:-7] if value.endswith(":latest") else value


def _model_present(model_ids: list[str], expected: str) -> bool:
    target = _canonical_model_id(expected)
    return any(_canonical_model_id(item) == target for item in model_ids)


def probe(
    *,
    base_url: str,
    expected_version: str,
    chat_model: str,
    embed_model: str,
    smoke: bool,
    timeout_s: float,
) -> tuple[list[Check], dict[str, Any]]:
    checks: list[Check] = []
    evidence: dict[str, Any] = {
        "base_url": base_url,
        "expected_version": expected_version,
        "chat_model": chat_model,
        "embed_model": embed_model,
        "smoke": smoke,
    }

    version_data = _request_json(base_url, "/api/version", timeout_s=timeout_s)
    actual_version = str(version_data.get("version") or "")
    evidence["actual_version"] = actual_version
    checks.append(
        Check(
            "version",
            actual_version == expected_version,
            f"expected={expected_version} actual={actual_version or '<missing>'}",
        )
    )

    models_data = _request_json(base_url, "/v1/models", timeout_s=timeout_s)
    rows = models_data.get("data")
    model_ids = (
        [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]
        if isinstance(rows, list)
        else []
    )
    evidence["model_ids"] = sorted(model_ids)
    checks.append(Check("chat_model_present", _model_present(model_ids, chat_model), chat_model))
    checks.append(Check("embed_model_present", _model_present(model_ids, embed_model), embed_model))

    if smoke:
        embed_data = _request_json(
            base_url,
            "/api/embeddings",
            payload={"model": embed_model, "prompt": "SAHOOL runtime probe"},
            timeout_s=timeout_s,
        )
        vector = embed_data.get("embedding")
        embedding_ok = (
            isinstance(vector, list)
            and len(vector) > 0
            and all(isinstance(v, (int, float)) for v in vector)
        )
        evidence["embedding_dimensions"] = len(vector) if isinstance(vector, list) else 0
        checks.append(
            Check("embedding_smoke", embedding_ok, f"dimensions={evidence['embedding_dimensions']}")
        )

        chat_data = _request_json(
            base_url,
            "/v1/chat/completions",
            payload={
                "model": chat_model,
                "messages": [{"role": "user", "content": "Reply with exactly: SAHOOL_OK"}],
                "temperature": 0,
                "max_tokens": 16,
                "stream": False,
            },
            timeout_s=timeout_s,
        )
        choices = chat_data.get("choices")
        content = ""
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "").strip()
        evidence["chat_content"] = content
        checks.append(Check("chat_smoke", bool(content), content[:120] or "<empty>"))

    return checks, evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--expected-version", default=DEFAULT_EXPECTED_VERSION)
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--smoke", action="store_true", help="run one embedding and one chat inference"
    )
    args = parser.parse_args(argv)

    try:
        checks, evidence = probe(
            base_url=args.base_url,
            expected_version=args.expected_version,
            chat_model=args.chat_model,
            embed_model=args.embed_model,
            smoke=args.smoke,
            timeout_s=args.timeout,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "schema": "sahool.ollama-runtime-probe/v1",
                    "status": "UNREACHABLE",
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 3

    ok = all(check.ok for check in checks)
    result = {
        "schema": "sahool.ollama-runtime-probe/v1",
        "status": "PASS" if ok else "FAIL",
        "checks": [asdict(check) for check in checks],
        "evidence": evidence,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
