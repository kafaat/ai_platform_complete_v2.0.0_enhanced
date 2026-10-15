"""Command line: introspect | generate | score | demo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_rules, load_schema


def _scope(args):
    from .sources.postgis import TenantScope

    chosen = [bool(args.tenant), args.tenant_null, args.all_tenants]
    if sum(chosen) != 1:
        raise SystemExit(
            "choose exactly one tenant scope: --tenant ID | --tenant-null | --all-tenants"
        )
    if args.tenant:
        return TenantScope("tenant", args.tenant)
    return TenantScope("null") if args.tenant_null else TenantScope("all")


def _add_db(p):
    p.add_argument("--dsn", help="PostgreSQL DSN/URI (read-only session is enforced)")
    p.add_argument("--tenant", help="tenant_id to load (compared as text)")
    p.add_argument(
        "--tenant-null", action="store_true", help="load rows whose tenant_id IS NULL (seed data)"
    )
    p.add_argument("--all-tenants", action="store_true", help="load every tenant (explicit opt-in)")
    p.add_argument(
        "--pg-option",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="extra session setting, e.g. app.current_tenant=<uuid> for RLS policies",
    )
    p.add_argument(
        "--schema-map", help="JSON overriding table/column names (see config.DEFAULT_SCHEMA)"
    )


def cmd_introspect(args):
    from .sources.postgis import Db, introspect

    db = Db(args.dsn, args.pg_option)
    scope = _scope(args) if (args.tenant or args.tenant_null or args.all_tenants) else None
    rep = introspect(db, load_schema(args.schema_map), scope)
    text = json.dumps(rep, ensure_ascii=False, indent=2, default=str)
    if args.out:  # keep a schema snapshot next to the generated set
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_generate(args):
    from .pipeline import generate
    from .raster import load_rasters
    from .split import parse_holdout

    rules = load_rules(args.rules)
    extra = {}
    if args.fixture:
        from .sources.fixture import load_fixture

        if sum([bool(args.tenant), args.all_tenants, args.tenant_null]) != 1:
            raise SystemExit(
                "choose exactly one tenant scope: --tenant ID | --tenant-null | --all-tenants"
            )
        store = load_fixture(args.fixture, args.tenant or None, args.all_tenants, args.tenant_null)
    elif args.dsn:
        from .sources.postgis import Db, load

        db = Db(args.dsn, args.pg_option)
        store, report = load(
            db, load_schema(args.schema_map), _scope(args), crosscheck_area=not args.no_crosscheck
        )
        extra["database"] = {
            "driver": report["driver"],
            "postgis": report["postgis"],
            "rls": report["rls"],
            "missing_optional_columns": {
                k: v["missing_optional"] for k, v in report["tables"].items()
            },
        }
        db.close()
    else:
        raise SystemExit("give --dsn or --fixture")
    store.rasters = load_rasters(args.raster_dir)
    ratios = tuple(float(x) for x in args.ratios.split(","))
    if len(ratios) != 3 or abs(sum(ratios) - 1) > 1e-6:
        raise SystemExit("--ratios must be three numbers summing to 1, e.g. 0.8,0.1,0.1")
    try:
        m = generate(
            store,
            rules,
            args.out,
            families=args.families,
            seed=args.seed,
            split_unit=args.split_unit,
            split_mode=args.split,
            ratios=ratios,
            holdout=parse_holdout(args.holdout),
            split_salt=args.split_salt,
            arabic_digits=args.arabic_digits,
            images=not args.no_images,
            max_per_family=args.max_per_family,
            extra_manifest=extra,
            require_well_inventory=getattr(args, "require_well_inventory", False),
        )
    except ValueError as exc:
        if "well inventory" not in str(exc):
            raise
        raise SystemExit(f"error: {exc}") from exc
    c = m["counts"]
    print(
        f"{c['items_total']} items -> {args.out}  splits={c['by_split']}  abstention={c['abstention_correct']}  "
        f"images={c['with_image']}  data_issues={m['data_issues']['total']}  rejected={c['facts']['rejected_records']}"
    )
    for w in m["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    return 3 if m["family_errors"] or m.get("case_errors") else 0


def cmd_score(args):
    from .score import read_jsonl, render, score

    rep = score(read_jsonl(args.gold), read_jsonl([args.pred]))
    print(render(rep))
    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_demo(args):
    from .demo import write_demo

    fx, rasters = write_demo(args.out)
    ns = argparse.Namespace(
        fixture=str(fx),
        dsn=None,
        tenant="demo-tenant",
        all_tenants=False,
        tenant_null=False,
        raster_dir=str(rasters),
        out=str(Path(args.out) / "qa"),
        families=None,
        seed=args.seed,
        split_unit="site",
        split="split",
        ratios="0.8,0.1,0.1",
        holdout=["test:governorate=الحديدة", "val:governorate=مأرب"],
        split_salt="sahool-qa",
        arabic_digits=False,
        no_images=False,
        rules=None,
        pg_option=[],
        schema_map=None,
        no_crosscheck=False,
        max_per_family=None,
        require_well_inventory=True,
    )  # the demo declares every well: prove it
    return cmd_generate(ns)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="sahool_qa", description="Arabic rule-based QA generator for SAHOOL PostGIS data"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("introspect", help="check the schema map against a live database")
    _add_db(p)
    p.add_argument("--out", help="also save the report (schema snapshot) to this JSON file")
    p.set_defaults(fn=cmd_introspect)

    p = sub.add_parser("generate", help="generate QA items")
    _add_db(p)
    p.add_argument("--fixture", help="GeoJSON fixture instead of a database")
    p.add_argument("--raster-dir", help="directory of .npy + .json raster sidecars")
    p.add_argument("--out", required=True)
    p.add_argument(
        "--families",
        default="all",
        help="comma list of families or prefixes ending in '.' (e.g. soil.,spatial.bbox)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=7,
        help="distractor/option-order seed (does not move split units)",
    )
    p.add_argument(
        "--split",
        choices=["split", "none"],
        default="split",
        help="'none' writes everything to eval.jsonl",
    )
    p.add_argument("--split-unit", choices=["field", "site", "governorate"], default="site")
    p.add_argument("--ratios", default="0.8,0.1,0.1")
    p.add_argument(
        "--holdout",
        action="append",
        help="force units into a split: [test:|val:]field=ID | site=TENANT|GOV | governorate=NAME (default test)",
    )
    p.add_argument("--split-salt", default="sahool-qa")
    p.add_argument(
        "--rules", help="JSON overriding agronomic thresholds (see config.DEFAULT_RULES)"
    )
    p.add_argument(
        "--arabic-digits",
        action="store_true",
        help="render digits as ٠١٢٣ in questions and options",
    )
    p.add_argument("--no-images", action="store_true")
    p.add_argument(
        "--max-per-family", type=int, help="cap items per family (deterministic subsample)"
    )
    p.add_argument("--no-crosscheck", action="store_true", help="skip PostGIS ST_Area cross-check")
    p.add_argument(
        "--require-well-inventory",
        action="store_true",
        help="refuse to generate when a field with meter records has no declared well inventory",
    )
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("score", help="score predictions")
    p.add_argument("--gold", nargs="+", required=True)
    p.add_argument("--pred", required=True)
    p.add_argument("--json", help="write the full report here")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser(
        "demo", help="build the synthetic demo fixture + rasters and generate from it"
    )
    p.add_argument("--out", default="demo_out")
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    return args.fn(args)
