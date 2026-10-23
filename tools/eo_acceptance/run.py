"""Run with python -m tools.eo_acceptance.run; reports distinguish unmeasured work."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("experiment", choices=["stac", "raster", "spatial"])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    report = {
        "experiment": args.experiment,
        "status": "ERROR",
        "python": platform.python_version(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    try:
        manifest = json.loads(args.manifest.read_text()) if args.manifest else None
        if manifest is not None:
            report["manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        if args.experiment == "stac":
            import httpx

            from .spatial import percentile
            from .stac import Limiter, compare, crawl

            if args.repeats < 20:
                raise ValueError("at least 20 repeats for P95")
            token = os.environ.get("CDSE_STAC_TOKEN")
            limiter = Limiter(bool(token))
            results = []
            with httpx.Client(timeout=60) as client:
                for query in manifest["queries"]:
                    timings = {"old": [], "new": []}
                    diffs = []
                    for sample in range(args.repeats):
                        crawls = {}
                        for name in ["old", "new"] if sample % 2 == 0 else ["new", "old"]:
                            items, metrics = crawl(
                                client, manifest[name], query["payload"], limiter, token
                            )
                            crawls[name] = items
                            timings[name].append(metrics)
                        diffs.append(compare(crawls["old"], crawls["new"]))
                    p95 = {
                        name: percentile([x["seconds"] for x in rows], 0.95)
                        for name, rows in timings.items()
                    }
                    p50 = {
                        name: percentile([x["seconds"] for x in rows], 0.5)
                        for name, rows in timings.items()
                    }
                    results.append(
                        {
                            "query": query["name"],
                            "comparisons": diffs,
                            "samples": timings,
                            "p95": p95,
                            "p50": p50,
                            "adoption_pass": p95["new"] <= 0.8 * p95["old"],
                            "correctness_pass": all(d["correctness_pass"] for d in diffs),
                        }
                    )
            report.update(
                results=results,
                asset_pixel_read_status="NOT_MEASURED",
                correctness_pass=all(x["correctness_pass"] for x in results) and bool(results),
            )
        elif args.experiment == "raster":
            import tempfile

            from .raster import benchmark_windows, compare_window

            for key in ("scenes", "fields"):
                ids = [entry["id"] for entry in manifest[key]]
                if not ids or len(ids) != len(set(ids)):
                    raise ValueError("matrix identities must be nonempty and unique")
            fingerprints = {}
            for scene in manifest["scenes"]:
                fingerprints[scene["id"]] = {}
                for band, path in scene["paths"].items():
                    if Path(path).is_file():
                        with Path(path).open("rb") as handle:
                            fingerprints[scene["id"]][band] = hashlib.file_digest(
                                handle, "sha256"
                            ).hexdigest()
                    else:
                        fingerprints[scene["id"]][band] = "REMOTE_CONTENT_NOT_HASHED"
            results = []
            for scene in manifest["scenes"]:
                for field in manifest["fields"]:
                    with tempfile.TemporaryDirectory() as directory:
                        results.append(
                            {
                                "scene": scene["id"],
                                "field": field["id"],
                                **compare_window(scene["paths"], field["geometry"], directory),
                            }
                        )
            benchmarks = [
                {
                    "scene": scene["id"],
                    **benchmark_windows(
                        scene["paths"], [f["geometry"] for f in manifest["fields"]], args.repeats
                    ),
                }
                for scene in manifest["scenes"]
            ]
            report.update(
                results=results,
                source_sha256=fingerprints,
                benchmarks=benchmarks,
                correctness_pass=bool(results),
                performance_status="HELPER_STRATEGIES_ONLY",
                requested_12_scene_100_field_matrix=(
                    len(manifest["scenes"]) == 12 and len(manifest["fields"]) == 100
                ),
            )
        else:
            import psycopg

            from .spatial import run

            dsn = os.environ.get("EO_TEST_DATABASE_URL")
            if not dsn:
                raise ValueError("EO_TEST_DATABASE_URL required (isolated database)")
            with psycopg.connect(dsn) as conn:
                report.update(run(conn, args.repeats))
        report["status"] = "PASS" if report["correctness_pass"] else "FAIL"
    except Exception as exc:
        # Exception messages from HTTP/DB clients may contain tokens, URLs or DSNs.
        report["error_type"] = type(exc).__name__
        print(f"Experiment failed: {type(exc).__name__}; see report status", file=sys.stderr)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
