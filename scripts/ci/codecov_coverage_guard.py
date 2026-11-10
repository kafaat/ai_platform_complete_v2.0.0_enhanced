#!/usr/bin/env python3
"""Check that uploaded Codecov XML paths refer to measured, tracked Git files.

The coverage database is re-exported from the repository root. That preserves
the full source path when two packages contain files with the same basename.
This checker never changes line hits or removes files.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]


class CoveragePathError(ValueError):
    """Coverage XML does not refer to unique tracked source paths."""


def validate_report(
    report: Path,
    repo_root: Path,
    prefixes: tuple[str, ...],
    required_files: tuple[str, ...],
    forbidden_prefixes: tuple[str, ...] = (),
) -> tuple[int, int, int]:
    repo_root = repo_root.resolve()
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CoveragePathError(f"coverage XML unreadable: {exc}") from exc
    if root.tag != "coverage":
        raise CoveragePathError("not a Cobertura coverage XML report")
    sources = [item.text for item in root.findall("./sources/source")]
    if len(sources) != 1 or not sources[0] or Path(sources[0]).resolve() != repo_root:
        raise CoveragePathError(
            f"expected one Git-root source {repo_root}, got {sources}"
        )
    if not prefixes:
        raise CoveragePathError("no allowed source prefixes")
    tracked = set(
        subprocess.check_output(["git", "ls-files", "-z"], cwd=repo_root)
        .decode("utf-8")
        .strip("\0")
        .split("\0")
    )
    classes = root.findall(".//class")
    if not classes:
        raise CoveragePathError("report has no measured classes")
    seen: dict[str, tuple[int, int]] = {}
    for entry in classes:
        filename = entry.get("filename", "")
        path = PurePosixPath(filename)
        if (
            not filename
            or path.is_absolute()
            or ".." in path.parts
            or chr(92) in filename
        ):
            raise CoveragePathError(f"non-canonical report path: {filename!r}")
        if filename != path.as_posix():
            raise CoveragePathError(f"not a canonical path: {filename!r}")
        if not any(
            filename.startswith(prefix.rstrip("/") + "/") for prefix in prefixes
        ):
            raise CoveragePathError(f"out-of-scope report path: {filename}")
        if filename in seen:
            raise CoveragePathError(f"duplicate coverage class path: {filename}")
        if any(
            filename.startswith(prefix.rstrip("/") + "/")
            for prefix in forbidden_prefixes
        ):
            raise CoveragePathError(f"forbidden test/source path: {filename}")
        if filename not in tracked or not (repo_root / filename).is_file():
            raise CoveragePathError(f"coverage path is not tracked source: {filename}")
        lines = entry.findall("./lines/line")
        try:
            covered = sum(int(line.get("hits", "0")) > 0 for line in lines)
        except ValueError as exc:
            raise CoveragePathError(f"invalid hit count for {filename}") from exc
        seen[filename] = (len(lines), covered)
    for filename in required_files:
        if filename not in seen or seen[filename][1] == 0:
            raise CoveragePathError(f"required source has no measured hits: {filename}")
    total = sum(measured for measured, _ in seen.values())
    covered = sum(hits for _, hits in seen.values())
    if total == 0 or covered == 0:
        raise CoveragePathError("no measurable covered source lines")
    return len(seen), total, covered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prefix", action="append", required=True)
    parser.add_argument("--require-file", action="append", default=[])
    parser.add_argument("--forbid-prefix", action="append", default=[])
    args = parser.parse_args()
    try:
        files, total, covered = validate_report(
            args.report,
            REPO_ROOT,
            tuple(args.prefix),
            tuple(args.require_file),
            tuple(args.forbid_prefix),
        )
    except (CoveragePathError, subprocess.CalledProcessError, OSError) as exc:
        print(f"CODECOV_REPORT_INVALID: {exc}", file=sys.stderr)
        return 1
    print(
        f"CODECOV_REPORT_VALID files={files} measured_lines={total} covered_lines={covered}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
