#!/usr/bin/env python3
"""Fail closed on unsafe or sensitive material inside a release ZIP."""

from __future__ import annotations

import argparse
import re
import stat
import sys
import zipfile
from pathlib import PurePosixPath

FORBIDDEN_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
    "secrets.yml",
    "secrets.yaml",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)  # gitleaks:allow — detection pattern, not a secret
MAX_ENTRY_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()
    errors: list[str] = []
    total = 0
    with zipfile.ZipFile(args.archive) as archive:
        for info in archive.infolist():
            path = PurePosixPath(info.filename)
            parts = path.parts
            total += info.file_size
            if path.is_absolute() or ".." in parts:
                errors.append(f"unsafe path: {info.filename}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                errors.append(f"symbolic link not allowed: {info.filename}")
            lower_name = path.name.lower()
            if lower_name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
                errors.append(f"sensitive filename: {info.filename}")
            if info.file_size > MAX_ENTRY_BYTES:
                errors.append(f"oversized entry: {info.filename}")
            if not info.is_dir() and info.file_size <= MAX_ENTRY_BYTES:
                with archive.open(info) as stream:
                    if PRIVATE_KEY.search(stream.read()):
                        errors.append(f"private-key material: {info.filename}")
    if total > MAX_TOTAL_BYTES:
        errors.append(f"uncompressed archive exceeds limit: {total}")
    if errors:
        print("release archive scan: FAILED", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"release archive scan: PASSED ({total} uncompressed bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
