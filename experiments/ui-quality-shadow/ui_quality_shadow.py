"""Read-only shadow audit of four reviewed SAHOOL frontend surfaces.

The detector is run only by a separate, networkless, nonroot CI container.
This module validates report bytes and source provenance; it DOES NOT prove
WCAG, functional correctness, UX quality or acceptance for production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

TARGETS = {
    "field-management": "frontend/src/sections/FieldWorkspaceRouteShell.tsx",
    "maphub": "frontend/src/sections/MapHub.tsx",
    "irrigation": "frontend/src/sections/IrrigationManualOperationsPanel.tsx",
    "remote-sensing": "frontend/src/sections/FieldWorkspaceImageryPanel.tsx",
}
POSITIVE_CONTROL = "experiments/ui-quality-shadow/fixtures/source-positive-control.tsx"
MAX_REPORT = 4 * 1024 * 1024
MAX_SOURCE = 1024 * 1024
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ShadowBlocked(ValueError):
    pass


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _read_regular(path: Path, limit: int) -> bytes:
    """Reject linked input and bound read before materializing the whole file."""
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ShadowBlocked("UNSAFE_INPUT")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if not data or len(data) > limit:
        raise ShadowBlocked("EMPTY_OR_OVERSIZED_INPUT")
    return data


def _source_bytes(root: Path, rel: str) -> bytes:
    """Descriptor-relative walk prevents escaping the checked-out Git root."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ShadowBlocked("SAFE_OPEN_UNAVAILABLE")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    parent = None
    leaf = None
    try:
        parent = os.open(root, flags | os.O_DIRECTORY)
        parts = rel.split("/")
        for name in parts[:-1]:
            next_dir = os.open(name, flags | os.O_DIRECTORY, dir_fd=parent)
            os.close(parent)
            parent = next_dir
        leaf = os.open(parts[-1], flags | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
        before = os.fstat(leaf)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_SOURCE:
            raise ShadowBlocked("UNSAFE_OR_OVERSIZED_SOURCE")
        data = bytearray()
        while len(data) <= MAX_SOURCE:
            chunk = os.read(leaf, min(65536, MAX_SOURCE + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(leaf)
        if (
            len(data) > MAX_SOURCE
            or len(data) != before.st_size
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ShadowBlocked("SOURCE_CHANGED_DURING_READ")
        return bytes(data)
    except OSError as exc:
        raise ShadowBlocked("SOURCE_PATH_UNSAFE_OR_MISSING") from exc
    finally:
        if leaf is not None:
            os.close(leaf)
        if parent is not None:
            os.close(parent)


def _git(root: Path, *args: str) -> bytes:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=True,
        )
        return result.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShadowBlocked("GIT_READ_UNAVAILABLE") from exc


def git_source_identity(root: Path, rel: str, data: bytes) -> str:
    line = _git(root, "ls-tree", "-z", "HEAD", "--", rel)
    rows = [x for x in line.split(b"\0") if x]
    if len(rows) != 1:
        raise ShadowBlocked("SOURCE_NOT_IN_COMMIT")
    try:
        meta, name = rows[0].split(b"\t", 1)
        mode, kind, oid = meta.split(b" ")
    except ValueError as exc:
        raise ShadowBlocked("INVALID_GIT_TREE") from exc
    if name != rel.encode() or mode not in (b"100644", b"100755") or kind != b"blob":
        raise ShadowBlocked("UNSAFE_GIT_ENTRY")
    computed = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if computed != oid.decode("ascii"):
        raise ShadowBlocked("WORKTREE_DIFFERS_FROM_COMMIT")
    return computed


def parse_json(raw: bytes) -> object:
    def unique(pairs):
        doc = {}
        for k, v in pairs:
            if k in doc:
                raise ShadowBlocked("DUPLICATE_JSON_KEY")
            doc[k] = v
        return doc

    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ShadowBlocked("NONFINITE_JSON")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ShadowBlocked("INVALID_JSON") from exc


def findings_count(doc: object) -> int:
    """Bounded recursive extraction; rejects unsupported detector output shapes."""
    if isinstance(doc, list):
        if not all(isinstance(item, dict) for item in doc):
            raise ShadowBlocked("INVALID_FINDINGS")
        return len(doc)
    if not isinstance(doc, dict):
        raise ShadowBlocked("UNSUPPORTED_DETECTOR_JSON")
    for key in ("findings", "issues", "violations"):
        if key in doc:
            value = doc[key]
            if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
                raise ShadowBlocked("INVALID_FINDINGS")
            return len(value)
    for key in ("results", "files", "targets"):
        if key in doc:
            value = doc[key]
            if not isinstance(value, list) or len(value) > 10000:
                raise ShadowBlocked("INVALID_RESULTS")
            return sum(findings_count(x) for x in value)
    raise ShadowBlocked("UNSUPPORTED_DETECTOR_JSON")


def evaluate(root: str | Path, reports: str | Path, image: str) -> dict:
    root = Path(root).resolve(strict=True)
    reports = Path(reports).resolve(strict=True)
    if not isinstance(image, str) or not IMAGE_ID.fullmatch(image):
        raise ShadowBlocked("IMAGE_ID_REQUIRED")
    head = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if not HEX40.fullmatch(head):
        raise ShadowBlocked("INVALID_SOURCE_COMMIT")
    if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise ShadowBlocked("SOURCE_NOT_GIT_ROOT")
    targets = []
    for area, relative in TARGETS.items():
        raw = _source_bytes(root, relative)
        blob_sha = git_source_identity(root, relative, raw)
        path = reports / (area + ".json")
        report_raw = _read_regular(path, MAX_REPORT)
        exit_raw = _read_regular(reports / (area + ".exit"), 12)
        code = exit_raw.decode("ascii", "strict").strip()
        if code not in ("0", "2"):
            raise ShadowBlocked("DETECTOR_DID_NOT_COMPLETE:" + area)
        count = findings_count(parse_json(report_raw))
        if (code == "0" and count != 0) or (code == "2" and count == 0):
            raise ShadowBlocked("DETECTOR_EXIT_MISMATCH:" + area)
        targets.append(
            {
                "area": area,
                "path": relative,
                "git_blob": blob_sha,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "detector_report_sha256": hashlib.sha256(report_raw).hexdigest(),
                "findings_advisory": count,
                "detector_exit": int(code),
            }
        )
    # A zero-finding result is not meaningful unless the same source scanner
    # also detects an intentionally bad TSX fixture under identical flags.
    control_source = _source_bytes(root, POSITIVE_CONTROL)
    control_blob = git_source_identity(root, POSITIVE_CONTROL, control_source)
    control_report = _read_regular(reports / "positive-control.json", MAX_REPORT)
    control_exit = _read_regular(reports / "positive-control.exit", 12)
    if control_exit.decode("ascii", "strict").strip() != "2":
        raise ShadowBlocked("POSITIVE_CONTROL_DETECTOR_NOT_ACTIVE")
    control_count = findings_count(parse_json(control_report))
    if control_count < 1:
        raise ShadowBlocked("POSITIVE_CONTROL_NO_FINDINGS")
    positive_control = {
        "path": POSITIVE_CONTROL,
        "git_blob": control_blob,
        "source_sha256": hashlib.sha256(control_source).hexdigest(),
        "detector_report_sha256": hashlib.sha256(control_report).hexdigest(),
        "findings_detected": control_count,
        "detector_exit": 2,
        "verified": True,
    }
    return {
        "format": "sahool.ui-quality-shadow.v1",
        "source_sha": head,
        "detector": "impeccable",
        "detector_version": "4.8.0",
        "image_id": image,
        "status": "REVIEW_ONLY",
        "target_count": len(targets),
        "targets": targets,
        "positive_control": positive_control,
        "style_findings_block_release": False,
        "wcag_conformance_proven": False,
        "browser_behavior_tested": False,
        "maphub_truecolor_default_changed": False,
        "irrigation_workflow_changed": False,
        "production_accepted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--reports", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--out", required=True)
    opts = parser.parse_args()
    try:
        target = Path(opts.out).resolve(strict=False)
        root = Path(opts.root).resolve(strict=True)
        if target == root or root in target.parents:
            raise ShadowBlocked("OUTPUT_WITHIN_SOURCE")
        result = evaluate(root, opts.reports, opts.image_id)
        payload = canonical(result) + b"\n"
        with target.open("xb") as stream:
            stream.write(payload)
        print(payload.decode("utf-8").strip())
        return 0
    except (ShadowBlocked, OSError, UnicodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc)
                    if isinstance(exc, ShadowBlocked)
                    else "INPUT_OR_EXECUTION_UNAVAILABLE",
                    "production_accepted": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
