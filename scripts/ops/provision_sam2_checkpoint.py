#!/usr/bin/env python3
"""Provision the pinned July 2024 SAM2 Hiera Large bytes, without loading Torch.

Source/digest evidence: certification/evidence/chatgpt_w5_20261017/sam2/.
An incomplete or untrusted download never replaces the installed checkpoint.
This operator command does not configure a service or start a deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

URL = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt"
SHA256 = "7442e4e9b732a508f80e141e7c2913437a3610ee0c77381a66658c3a445df87b"
SIZE = 897952466
FILENAME = "sam2_hiera_large.pt"
CHUNK_SIZE = 1024 * 1024


def verify_checkpoint(path: Path) -> dict:
    """Verify stored bytes against the publisher pin, not a caller-supplied hash."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            size += len(chunk)
            if size > SIZE:
                raise ValueError("checkpoint_size_mismatch")
            digest.update(chunk)
    if size != SIZE:
        raise ValueError("checkpoint_size_mismatch")
    actual = digest.hexdigest()
    if actual != SHA256:
        raise ValueError("checkpoint_digest_mismatch")
    return {"sha256": actual, "bytes": size, "source_url": URL}


def provision(output_dir: Path) -> dict:
    """Download into a private temporary file, verify, then atomically publish it."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / FILENAME
    temporary = None
    try:
        with urllib.request.urlopen(URL, timeout=60) as source:
            with tempfile.NamedTemporaryFile(
                dir=output_dir, prefix=".sam2-", suffix=".part", delete=False
            ) as target:
                temporary = Path(target.name)
                size = 0
                while chunk := source.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > SIZE:
                        raise ValueError("checkpoint_size_mismatch")
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
        receipt = verify_checkpoint(temporary)
        # The inference container can run as a different, unprivileged user.
        temporary.chmod(0o644)
        os.replace(temporary, destination)
        return {**receipt, "path": str(destination.resolve()), "status": "provisioned"}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("sam2-models"))
    parser.add_argument("--check", action="store_true", help="Verify existing bytes; no download")
    args = parser.parse_args(argv)
    try:
        if args.check:
            path = args.output_dir / FILENAME
            receipt = {**verify_checkpoint(path), "path": str(path.resolve()), "status": "verified"}
        else:
            receipt = provision(args.output_dir)
    except (OSError, ValueError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=True), file=sys.stderr
        )
        return 1
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
