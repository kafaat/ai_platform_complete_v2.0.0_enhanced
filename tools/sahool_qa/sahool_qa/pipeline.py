"""Generation pipeline:

  prepare facts (QC, geometry quarantine, canonical order)
  → audit (written even if generation later fails)
  → generate per family (a failing family is isolated and reported)
  → source-level split (dependencies from every record shown)
  → render + verify images
  → write into a staging directory → publish it as one unit.

Publishing replaces the whole output directory (F06): stale files from an
earlier run can never sit next to new ones, and a failed run leaves the
previous output untouched. A directory not produced by sahool-qa is never
overwritten.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import traceback
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from . import GENERATOR_ID
from .arabic import LETTERS, to_arabic_digits
from .audit import audit
from .config import LEVELS, validate_water_rules
from .facts import FactStore
from .generators import select
from .items import GenContext
from .split import assign
from .waterbal import inventory_report

PUBLIC_KEYS = (
    "id",
    "revision",
    "level",
    "level_ar",
    "family",
    "question",
    "options",
    "context",
    "image",
    "related_group",
)


def fingerprint(store: FactStore) -> str:
    """Hash of a canonical, order-independent representation of every input
    that can influence an item: all field/record attributes, QC raw values,
    raster metadata and pixels."""

    def g(geom):
        return geom.to_geojson(9) if geom is not None else None

    doc = {
        "fields": sorted(
            (
                [
                    f.key,
                    f.id,
                    f.name,
                    f.tenant,
                    f.governorate,
                    f.crop,
                    f.soil_type,
                    f.area_ha_stored,
                    f.lat,
                    f.lon,
                    g(f.geom_raw or f.geom),
                ]
                for f in store.fields.values()
            ),
            key=lambda r: r[0],
        ),
        "soil": sorted(
            (
                [
                    s.key,
                    s.sample_id,
                    s.field_id,
                    s.tenant,
                    s.record_id,
                    s.recorded_ts.isoformat() if s.recorded_ts else None,
                    s.point,
                    s.source,
                    {a: getattr(s, a) for a in s.MEASURES},
                    s.qc,
                ]
                for s in store.soil
            ),
            key=lambda r: r[0],
        ),
        "indicators": sorted(
            (
                [
                    i.key,
                    i.indicator_id,
                    i.field_id,
                    i.tenant,
                    i.record_id,
                    i.recorded_ts.isoformat() if i.recorded_ts else None,
                    i.value,
                    i.unit,
                    i.category,
                    i.status,
                    i.source,
                    i.point,
                    i.qc,
                ]
                for i in store.indicators
            ),
            key=lambda r: r[0],
        ),
        "rasters": sorted(
            (
                [
                    r.index_name,
                    str(r.date),
                    r.crs,
                    list(r.transform),
                    r.nodata,
                    r.scene_id,
                    r.synthetic,
                    r.role,
                    r.product_version,
                    r.pixel_sha256() if Path(r.path).exists() else r.path,
                ]
                for r in store.rasters
            ),
            key=lambda r: json.dumps(r, default=str),
        ),
        "scope": store.tenant_scope,
        "water_well_inventory": store.provenance.get("water_well_inventory", {}),
    }
    blob = json.dumps(doc, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


IDENTIFIER_OPTIONS = {"spatial.point_in_field", "soil.max_ec", "reasoning.highest_mean_ec"}


def _pixel_digest(store: FactStore, raster_key: str) -> str:
    layer = next(ln for ln in store.rasters if ln.key == raster_key)
    return layer.pixel_sha256()


def _digits(it: dict):
    it["question"] = to_arabic_digits(it["question"])
    if it["family"] in IDENTIFIER_OPTIONS:  # options are sample ids / field names: keep as stored
        return
    it["answer_text"] = to_arabic_digits(it["answer_text"])
    for o in it["options"]:
        o["text"] = to_arabic_digits(o["text"])


def _owned(out: Path) -> bool:
    mf = out / "manifest.json"
    try:
        return (
            json.loads(mf.read_text(encoding="utf-8")).get("generator", "").startswith("sahool-qa/")
        )
    except (OSError, ValueError):
        return False


def _publish(stage: Path, out: Path):
    if out.exists():
        if not out.is_dir():
            raise RuntimeError(f"{out} exists and is not a directory")
        if any(out.iterdir()) and not _owned(out):
            raise RuntimeError(
                f"{out} exists and was not produced by sahool-qa; refusing to replace it"
            )
        backup = out.with_name(f".{out.name}.old-{uuid.uuid4().hex[:8]}")
        os.replace(out, backup)
        try:
            os.replace(stage, out)
        except BaseException:
            os.replace(backup, out)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    else:
        os.replace(stage, out)


def _coverage(items: list[dict]) -> dict:
    cov = defaultdict(
        lambda: defaultdict(lambda: {"items": 0, "units": set(), "abstention": 0, "with_image": 0})
    )
    for it in items:
        c = cov[it["split"]][it["family"]]
        c["items"] += 1
        c["units"].update(it["split_units"])
        c["abstention"] += int(not it["answerable"])
        c["with_image"] += int("image" in it)
    return {
        s: {f: {**v, "units": len(v["units"])} for f, v in sorted(fams.items())}
        for s, fams in sorted(cov.items())
    }


def generate(
    store: FactStore,
    rules: dict,
    out_dir: str,
    *,
    families: str | None = None,
    seed: int = 7,
    split_unit: str = "site",
    split_mode: str = "split",
    ratios=(0.8, 0.1, 0.1),
    holdout=None,
    split_salt: str = "sahool-qa",
    arabic_digits: bool = False,
    images: bool = True,
    max_per_family: int | None = None,
    extra_manifest: dict | None = None,
    require_well_inventory: bool = False,
) -> dict:
    validate_water_rules(rules)
    inventory = {
        **store.provenance.get("water_well_inventory", {}),
        **rules["water"].get("well_inventory", {}),
    }
    validate_water_rules({**rules, "water": {**rules["water"], "well_inventory": inventory}})
    if require_well_inventory:
        store.prepare(rules)
        missing = inventory_report(store, rules)["without_inventory"]
        if missing:
            raise ValueError(
                f"{len(missing)} metered fields have no declared well inventory: {missing[:10]}"
                + (" …" if len(missing) > 10 else "")
            )
    out = Path(out_dir).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not _owned(out))):
        raise RuntimeError(
            f"{out} exists and was not produced by sahool-qa; refusing to replace it"
        )
    stage = out.with_name(f".{out.name}.staging-{uuid.uuid4().hex[:8]}")
    stage.mkdir()
    try:
        manifest = _generate_into(
            stage,
            store,
            rules,
            families=families,
            seed=seed,
            split_unit=split_unit,
            split_mode=split_mode,
            ratios=ratios,
            holdout=holdout,
            split_salt=split_salt,
            arabic_digits=arabic_digits,
            images=images,
            max_per_family=max_per_family,
            extra_manifest=extra_manifest,
        )
        _publish(stage, out)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return manifest


def _generate_into(
    out: Path,
    store: FactStore,
    rules: dict,
    *,
    families,
    seed,
    split_unit,
    split_mode,
    ratios,
    holdout,
    split_salt,
    arabic_digits,
    images,
    max_per_family,
    extra_manifest,
) -> dict:
    store.prepare(rules)
    issues = audit(store, rules)
    with open(out / "data_issues.jsonl", "w", encoding="utf-8") as fh:
        for iss in issues:
            fh.write(json.dumps(iss, ensure_ascii=False) + "\n")

    ctx = GenContext(store=store, rules=rules, seed=seed, split_unit=split_unit)
    fams = select(families)
    items, family_errors = [], {}
    for name, (_, fn) in fams.items():
        ctx.stats.setdefault(name, {"made": 0, "skipped": {}})
        try:
            made = list(fn(ctx))
        except Exception as e:  # isolate: one family's bug must not hide the rest or the audit
            family_errors[name] = {
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(limit=6),
            }
            continue
        if max_per_family and len(made) > max_per_family:
            made.sort(key=lambda it: hashlib.sha256(f"{seed}|{it['id']}".encode()).hexdigest())
            ctx.stats[name]["capped_from"] = len(made)
            made = made[:max_per_family]
        items.extend(made)

    kept, split_report = assign(
        items, store, split_unit, ratios, holdout or [], split_salt, split_mode
    )

    image_report, image_drops = Counter(), []
    if images:
        from .raster import render_threshold_png

        verified = []
        for it in kept:
            ref = it.get("image_ref")
            if not ref:
                verified.append(it)
                continue
            layer = next(ln for ln in store.rasters if ln.key == ref["raster_key"])
            res = render_threshold_png(
                layer,
                store.fields[ref["field_key"]].geom,
                ref["threshold"],
                str(out / "images" / f"{it['id']}.png"),
            )
            ok = res is not None
            if ok and it["family"] == "scene.vegetation_fraction":
                pct = 100 * res["decoded"]["frac_above"]
                bins = it["evidence"]["values"]["bins"]

                # percentages are capped like numeric_bins does: 100 % belongs to the top bin
                def in_bin(v, bins=bins):
                    return next(
                        (i for i, (a, b) in enumerate(bins) if a - 1e-9 <= min(v, 100 - 1e-6) < b),
                        None,
                    )

                want = in_bin(it["answer_value"])
                ok = (
                    abs(pct - it["answer_value"]) < 0.006
                    and want is not None
                    and in_bin(pct) == want
                )
            elif ok and it["family"] == "reasoning.pivot_anomaly_pattern":
                from .generators.investigation import classify_pattern

                cls_dec, det = classify_pattern(res["decoded_polar"], rules)
                ok = (
                    det.get("reason") == "too_little_valid_data"
                    if it["answer_value"] == "insufficient_valid"
                    else cls_dec == it["answer_value"]
                )
            elif ok and it["family"] == "reasoning.pivot_weak_quadrant":
                q = res["decoded"]["quadrants"]
                ok = min(q, key=lambda k: (q[k]["frac_above"], k)) == it["answer_value"]
            if ok:
                it["image"] = f"images/{it['id']}.png"
                it["image_meta"] = {
                    k: res[k] for k in ("width", "height", "scale", "scale_bar_m", "pixel_size_m")
                }
                image_report["verified"] += 1
                verified.append(it)
            else:
                image_report["dropped_not_reproducible_from_png"] += 1
                image_drops.append(
                    {
                        "id": it["id"],
                        "family": it["family"],
                        "answer_value": it["answer_value"],
                        "decoded": None if res is None else res["decoded"],
                    }
                )
                (out / "images" / f"{it['id']}.png").unlink(missing_ok=True)
        kept = verified
    else:  # an image question without its image cannot be answered: drop, and say so
        image_report["dropped_images_disabled"] = sum(bool(it.get("image_ref")) for it in kept)
        kept = [it for it in kept if not it.get("image_ref")]
    for it in kept:
        it["generator"] = GENERATOR_ID
        if arabic_digits:
            _digits(it)
        # `id` names the question (family + subject) and stays stable across runs; `revision`
        # changes whenever what the question shows or expects changes (corrected lab value,
        # reprocessed scene, new rule) — same id + different revision = the item changed.
        blob = json.dumps(
            [
                it["question"],
                it["options"],
                it["answer"],
                it["context"],
                it["evidence"],
                it.get("image_ref") and _pixel_digest(store, it["image_ref"]["raster_key"]),
            ],
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        it["revision"] = "rv-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]

    by_split = defaultdict(list)
    for it in kept:
        by_split[it["split"]].append(it)
    outputs = ["data_issues.jsonl"]
    for split, rows in sorted(by_split.items()):
        rows.sort(key=lambda r: (r["family"], r["id"]))
        with open(out / f"{split}.jsonl", "w", encoding="utf-8") as fh:
            for it in rows:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        with open(out / f"{split}.public.jsonl", "w", encoding="utf-8") as fh:
            for it in rows:  # model-facing: no answer, answer_value, evidence or answerable flag
                fh.write(
                    json.dumps({k: it[k] for k in PUBLIC_KEYS if k in it}, ensure_ascii=False)
                    + "\n"
                )
        outputs += [f"{split}.jsonl", f"{split}.public.jsonl"]
    if (out / "images").exists():
        outputs += sorted(f"images/{p.name}" for p in (out / "images").iterdir())

    letters = Counter(it["answer"] for it in kept)
    n = len(kept)
    coverage = _coverage(kept)
    warnings = list(split_report.get("warnings", []))
    if n >= 40 and letters and max(letters.values()) / n > 0.40:
        warnings.append(f"answer-letter imbalance: {dict(letters)}")
    if split_mode == "split":
        train_f = set(coverage.get("train", {}))
        for s in ("val", "test"):
            missing = sorted(train_f - set(coverage.get(s, {})))
            if missing:
                warnings.append(f"{s} lacks families present in train: {missing}")
    if family_errors:
        warnings.append(f"families failed and were skipped: {sorted(family_errors)}")
    if ctx.cache.get("case_errors"):
        warnings.append(f"water cases failed and were skipped: {len(ctx.cache['case_errors'])}")
    water_inventory = inventory_report(store, rules)
    if water_inventory["without_inventory"]:
        warnings.append(
            f"{len(water_inventory['without_inventory'])} of {water_inventory['metered_fields']} metered "
            "fields have no declared well inventory: their irrigation, plan, balance and refill questions "
            "are all abstentions (pass the inventory with --rules, or use --require-well-inventory)"
        )
    if store.synthetic or any(r.synthetic for r in store.rasters):
        warnings.append(
            "SYNTHETIC inputs: items are for testing the pipeline, not for evaluating agronomy"
        )
    manifest = {
        "generator": GENERATOR_ID,
        "created_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "source": store.source,
        "tenant_scope": store.tenant_scope,
        "synthetic": store.synthetic,
        "synthetic_rasters": [r.key for r in store.rasters if r.synthetic],
        "provenance": store.provenance,
        "input_fingerprint": fingerprint(store),
        "seed": seed,
        "families": list(fams),
        "rules_sha256": hashlib.sha256(
            json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16],
        "counts": {
            "facts": {
                "fields": len(store.fields),
                "drawn_fields": len(store.drawn_fields()),
                "soil_samples": len(store.soil),
                "indicators": len(store.indicators),
                "rasters": len(store.rasters),
                "rejected_records": dict(store.rejected),
            },
            "items_total": n,
            "by_split": dict(Counter(it["split"] for it in kept)),
            "by_level": {LEVELS[k]: v for k, v in Counter(it["level"] for it in kept).items()},
            "by_family": dict(sorted(Counter(it["family"] for it in kept).items())),
            "answerable": sum(it["answerable"] for it in kept),
            "abstention_correct": sum(not it["answerable"] for it in kept),
            "abstain_offered": sum(it["abstain_offered"] for it in kept),
            "with_image": sum("image" in it for it in kept),
            "answer_letters": {k: letters.get(k, 0) for k in LETTERS if letters.get(k, 0)},
            "by_evidence_kind": dict(Counter(it["evidence"]["kind"] for it in kept)),
        },
        "coverage": coverage,
        "images": {**dict(image_report), "dropped": image_drops},
        "chance_accuracy": {
            s: round(sum(1 / len(it["options"]) for it in rows) / len(rows), 4)
            for s, rows in by_split.items()
        },
        # a model that always picks the abstain option when it is offered: a second floor to beat
        "always_abstain_accuracy": {
            s: round(sum(not it["answerable"] for it in rows) / len(rows), 4)
            for s, rows in by_split.items()
        },
        "split": split_report,
        "family_stats": ctx.stats,
        "family_errors": family_errors,
        "case_errors": ctx.cache.get("case_errors", []),
        "water_inventory": water_inventory,
        "data_issues": {
            "total": len(issues),
            "by_code": dict(Counter(i["code"] for i in issues)),
            "by_severity": dict(Counter(i["severity"] for i in issues)),
        },
        "warnings": warnings,
        "outputs": sorted(outputs + ["preview.html"]),
        **(extra_manifest or {}),
    }
    from .preview import render_preview

    (out / "preview.html").write_text(render_preview(kept, manifest, out), encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
