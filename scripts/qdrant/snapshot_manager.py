#!/usr/bin/env python3
"""Qdrant collection snapshot backup, offline verification, and safe restore drill."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, parse, request

DRILL_PREFIX = "sahool_restore_drill_"


class QdrantError(RuntimeError):
    pass


class Client:
    def __init__(self, url: str, api_key: str, timeout: int = 60):
        self.url = url.rstrip("/")
        self.headers = {"api-key": api_key} if api_key else {}
        self.timeout = timeout

    def call(self, method: str, path: str, body: bytes | None = None,
             headers: dict[str, str] | None = None) -> tuple[dict, bytes]:
        req = request.Request(self.url + path, data=body, method=method,
                              headers={**self.headers, **(headers or {})})
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                content_type = response.headers.get("content-type", "")
        except error.HTTPError as exc:
            raise QdrantError(f"Qdrant {method} {path} failed: HTTP {exc.code}") from exc
        if "json" in content_type:
            payload = json.loads(raw or b"{}")
            if payload.get("status") not in (None, "ok"):
                raise QdrantError(f"Qdrant returned non-ok status for {path}")
            return payload, raw
        return {}, raw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(client: Client, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    payload, _ = client.call("GET", "/collections")
    names = sorted(row["name"] for row in payload.get("result", {}).get("collections", []))
    if not names:
        raise QdrantError("no Qdrant collections found; refusing to create an empty backup")
    rows = []
    for name in names:
        safe_name = parse.quote(name, safe="")
        created, _ = client.call("POST", f"/collections/{safe_name}/snapshots")
        snapshot_name = created["result"]["name"]
        _, content = client.call("GET", f"/collections/{safe_name}/snapshots/{parse.quote(snapshot_name, safe='')}")
        clean_snapshot_name = Path(snapshot_name).name
        if not clean_snapshot_name or clean_snapshot_name != snapshot_name:
            raise QdrantError("Qdrant returned an unsafe snapshot filename")
        collection_ref = hashlib.sha256(name.encode()).hexdigest()[:16]
        output = destination / f"{collection_ref}--{clean_snapshot_name}"
        output.write_bytes(content)
        info, _ = client.call("GET", f"/collections/{safe_name}")
        rows.append({"collection": name, "snapshot_file": output.name, "size_bytes": len(content),
                     "sha256": sha256(output), "points_count": info.get("result", {}).get("points_count")})
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(UTC).isoformat(),
                "qdrant_url_redacted": parse.urlsplit(client.url).hostname, "snapshots": rows}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify(destination)
    return manifest


def verify(directory: Path) -> dict:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise QdrantError("snapshot manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("snapshots") or []
    if not rows:
        raise QdrantError("snapshot manifest is empty")
    for row in rows:
        name = Path(str(row.get("snapshot_file", ""))).name
        if name != row.get("snapshot_file"):
            raise QdrantError("unsafe snapshot filename in manifest")
        path = directory / name
        if not path.is_file() or path.stat().st_size != int(row["size_bytes"]):
            raise QdrantError(f"snapshot size mismatch: {name}")
        if sha256(path) != row["sha256"]:
            raise QdrantError(f"snapshot digest mismatch: {name}")
    return manifest


def _multipart(path: Path) -> tuple[bytes, str]:
    boundary = "----sahool-" + secrets.token_hex(16)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"snapshot\"; "
            f"filename=\"{path.name}\"\r\nContent-Type: {content_type}\r\n\r\n").encode()
    return head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode(), boundary


def restore_drill(client: Client, directory: Path, evidence_path: Path) -> dict:
    manifest = verify(directory)
    evidence_rows = []
    for row in manifest["snapshots"]:
        source = row["collection"]
        target = (DRILL_PREFIX + hashlib.sha256(source.encode()).hexdigest()[:12]
                  + "_" + secrets.token_hex(4))
        if not target.startswith(DRILL_PREFIX):
            raise QdrantError("unsafe restore drill target")
        body, boundary = _multipart(directory / row["snapshot_file"])
        target_path = parse.quote(target, safe="")
        created = False
        try:
            client.call("POST", f"/collections/{target_path}/snapshots/upload?priority=snapshot",
                        body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
            created = True
            restored, _ = client.call("GET", f"/collections/{target_path}")
            restored_count = restored.get("result", {}).get("points_count")
            expected_count = row.get("points_count")
            if expected_count is not None and restored_count != expected_count:
                raise QdrantError(f"restore count mismatch for {source}")
            evidence_rows.append({"source_collection": source, "drill_collection": target,
                                  "snapshot_sha256": row["sha256"], "points_count": restored_count,
                                  "status": "verified"})
        finally:
            # Only a deterministic, reserved drill prefix may ever be deleted.
            if created and target.startswith(DRILL_PREFIX):
                client.call("DELETE", f"/collections/{target_path}")
    evidence = {"schema_version": 1, "status": "verified", "timestamp_utc": datetime.now(UTC).isoformat(),
                "drill_mode": "temporary_collection_non_destructive", "collections": evidence_rows}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "verify", "restore-drill"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--url", default=os.getenv("QDRANT_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("QDRANT_API_KEY", ""))
    parser.add_argument("--evidence", type=Path,
                        default=Path("certification/evidence/qdrant_restore_drill_summary.json"))
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify(args.directory)
        else:
            if not args.url or not args.api_key:
                raise QdrantError("QDRANT_URL and QDRANT_API_KEY are required")
            client = Client(args.url, args.api_key)
            result = backup(client, args.directory) if args.command == "backup" else restore_drill(client, args.directory, args.evidence)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (QdrantError, OSError, ValueError, KeyError) as exc:
        print(f"qdrant snapshot manager: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
