"""Read-only four-surface SAHOOL Impeccable observation, never a release gate.

The Docker detector and its version-pinned npm package are executed only in CI.
No product code, routes, forms, user data or production services are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

TARGETS = {
    "maphub": "frontend/src/sections/maphub/MapHubShell.tsx",
    "field-workspace": "frontend/src/sections/FieldWorkspaceRouteShell.tsx",
    "irrigation": "frontend/src/sections/FieldWorkspaceIrrigationPanel.tsx",
    "remote-sensing": "frontend/src/sections/SatellitePage.tsx",
}
MAX_REPORT = 2 * 1024 * 1024
MAX_SOURCE = 512 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ObservationBlocked(ValueError):
    pass


def bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ObservationBlocked("UNSAFE_INPUT")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ObservationBlocked("OVERSIZED_INPUT")
    if not data:
        raise ObservationBlocked("EMPTY_INPUT")
    return data


def strict_json(raw: bytes):
    def unique(items):
        value = {}
        for key, entry in items:
            if key in value:
                raise ObservationBlocked("DUPLICATE_JSON")
            value[key] = entry
        return value
    try:
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ObservationBlocked("NONFINITE_JSON")))
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ObservationBlocked):
            raise
        raise ObservationBlocked("INVALID_JSON") from exc


def primary_count(doc: object) -> int:
    if isinstance(doc, list):
        if not all(isinstance(x, dict) for x in doc):
            raise ObservationBlocked("INVALID_FINDINGS")
        return len(doc)
    if not isinstance(doc, dict):
        raise ObservationBlocked("INVALID_RESULT")
    for key in ("findings", "issues", "violations"):
        if key in doc:
            items = doc[key]
            if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
                raise ObservationBlocked("INVALID_FINDINGS")
            return len(items)
    for key in ("files", "results", "targets"):
        if key in doc and isinstance(doc[key], list):
            return sum(primary_count(x) for x in doc[key])
    raise ObservationBlocked("UNSUPPORTED_DETECTOR_RESULT")


def observe(root: Path, reports: Path, source_sha: str, image_sha256: str) -> dict:
    if (not isinstance(source_sha, str) or not SHA.fullmatch(source_sha)
            or not isinstance(image_sha256, str) or not IMAGE.fullmatch(image_sha256)):
        raise ObservationBlocked("INVALID_SOURCE_OR_IMAGE_IDENTITY")
    items = []
    for short, relative in TARGETS.items():
        source = bounded(root / relative, MAX_SOURCE)
        analysis = bounded(reports / (short + ".json"), MAX_REPORT)
        result = strict_json(analysis)
        findings = primary_count(result)
        code_raw = bounded(reports / (short + ".exit"), 4)
        try:
            code = int(code_raw.strip())
        except ValueError as exc:
            raise ObservationBlocked("INVALID_EXIT_CODE") from exc
        if (code not in (0, 2) or (code == 0 and findings != 0)
                or (code == 2 and findings == 0)):
            raise ObservationBlocked("DETECTOR_EXIT_OR_FINDINGS_MISMATCH")
        items.append({
            "surface": short,
            "file": relative,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "detector_json_sha256": hashlib.sha256(analysis).hexdigest(),
            "primary_findings": findings,
            "detector_exit": code,
        })
    return {
        "schema": "sahool.ui-static-observation.v1",
        "status": "OBSERVED_FOR_REVIEW",
        "source_sha": source_sha,
        "detector_image_sha256": image_sha256,
        "detector_package": "impeccable@4.8.0",
        "surfaces_checked": len(items),
        "items": items,
        "total_primary_findings": sum(x["primary_findings"] for x in items),
        "style_findings_block_release": False,
        "browser_acceptance_executed": False,
        "end_to_end_product_flow_tested": False,
        "license_and_supply_chain_approved": False,
        "production_accepted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--reports", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        result = observe(Path(args.root), Path(args.reports),
                         args.source_sha, args.image_sha256)
        with Path(args.out).open("xb") as stream:
            stream.write((json.dumps(result, sort_keys=True) + "\n").encode())
        print(json.dumps({"status": result["status"], "source_sha": result["source_sha"],
                          "surfaces_checked": result["surfaces_checked"],
                          "primary_findings": result["total_primary_findings"],
                          "production_accepted": False}, sort_keys=True))
        return 0
    except (ObservationBlocked, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc) if
                          isinstance(exc, ObservationBlocked) else "INPUT_UNAVAILABLE",
                          "production_accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
