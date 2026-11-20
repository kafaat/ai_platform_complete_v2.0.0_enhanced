"""Publish an Arabic test document and read its exact revision through RAG."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from urllib import request
from uuid import UUID

FILENAME = "irrigation-ar.txt"
QUERY = "ما علامة المراجعة في سجل حقل السدرة التجريبي؟"


def post(url, body, content_type, tenant):
    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": content_type,
            "X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"],
            "X-Tenant-Id": tenant,
        },
    )
    with request.urlopen(req, timeout=60) as response:
        return json.load(response)


def publish(raw, tenant):
    boundary = "sahool-lab-arabic-fixture"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="tenant_id"\r\n\r\n{tenant}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{FILENAME}"\r\n'
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        ).encode()
        + raw
        + f"\r\n--{boundary}--\r\n".encode()
    )
    result = post(
        "http://sahool-local-ai-rag:8000/v1/ingest",
        body,
        f"multipart/form-data; boundary={boundary}",
        tenant,
    )
    if (result.get("status"), result.get("chunks"), result.get("rejected")) != ("ingested", 1, 0):
        raise ValueError("fixture document was not ingested as one chunk")


def identify(raw, rows, tenant):
    uri = f"tenant-upload://{tenant}/{FILENAME}"
    revision = "sha256:" + hashlib.sha256(raw).hexdigest()
    document_id = hashlib.sha256(f"{tenant}:{FILENAME}".encode()).hexdigest()
    for row in rows:
        text = row.get("text", "")
        if text.strip() != raw.decode().strip():
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        if (
            row.get("source_uri"),
            row.get("source_revision"),
            row.get("document_id"),
            row.get("content_digest"),
        ) == (uri, revision, document_id, digest) and row.get("chunk_id"):
            return {
                key: row[key]
                for key in ("document_id", "chunk_id", "source_revision", "content_digest")
            }
    raise ValueError(
        "the retrieved passage did not match the published Arabic document and revision"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", type=UUID)
    parser.add_argument("fixture_b64")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    raw = base64.b64decode(args.fixture_b64, validate=True)
    tenant = f"lab-georag-{args.run_id.hex}"
    if args.publish:
        publish(raw, tenant)
    result = post(
        "http://sahool-rag-retrieval:8000/v1/search",
        json.dumps(
            {"query": QUERY, "tenant_id": tenant, "source_type": "uploaded_document", "final_k": 8}
        ).encode(),
        "application/json",
        tenant,
    )
    print(json.dumps(identify(raw, result.get("annotations", []), tenant), sort_keys=True))
