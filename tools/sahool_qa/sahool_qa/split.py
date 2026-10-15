"""Source-level splitting — the fix for AgroOmni's filename-only decontamination.

Splits are assigned to *units* (a field, a site = tenant+governorate, or a
whole governorate), never to individual questions. Every question inherits
the split of the units of all fields it touches; a question touching units in
different splits is dropped. Assignment hashes the unit key only (salted), so
changing the distractor seed never moves a field between splits.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

from .arabic import normalize
from .facts import FactStore

SPLITS = ("train", "val", "test")


def _frac(key: str, salt: str) -> float:
    h = hashlib.sha256(f"{salt}|{key}".encode("utf-8")).hexdigest()
    return int(h[:15], 16) / 16 ** 15


def parse_holdout(specs: list[str] | None) -> list[tuple[str, str, str]]:
    """'[test:|val:]kind=value' -> (split, kind, value). kind: field | site | governorate.
    field accepts a field_id or a composite key 'tenant::field_id'; site is 'tenant|governorate'."""
    out = []
    for s in specs or []:
        split = "test"
        if ":" in s.split("=", 1)[0]:
            split, s = s.split(":", 1)
        if split not in ("test", "val"):
            raise SystemExit(f"--holdout split must be test or val, got {split!r}")
        if "=" not in s:
            raise SystemExit(f"--holdout expects [test:|val:]kind=value, got {s!r}")
        k, v = s.split("=", 1)
        if k not in ("field", "site", "governorate"):
            raise SystemExit(f"--holdout kind must be field, site or governorate, got {k!r}")
        out.append((split, k, v))
    return out


def unit_splits(store: FactStore, unit: str, ratios: tuple[float, float, float], holdout, salt: str) -> dict[str, str]:
    from .facts import tenant_key
    r_train, r_val, _ = ratios
    forced: dict[str, str] = {}
    for f in store.fields.values():
        u = store.unit_key(f, unit)
        for split, k, v in holdout:
            hit = ((k == "field" and v in (f.id, f.key)) or (k == "governorate" and v == (f.governorate or "")) or
                   (k == "site" and v == f"{tenant_key(f.tenant)}|{f.governorate or '?'}"))
            if hit:
                if forced.get(u, split) != split:
                    raise SystemExit(f"unit {u} is held out for both {forced[u]} and {split}")
                forced[u] = split
    out = {}
    for f in store.fields.values():
        u = store.unit_key(f, unit)
        if u in forced:
            out[u] = forced[u]
        elif u not in out:
            x = _frac(u, salt)
            out[u] = "train" if x < r_train else "val" if x < r_train + r_val else "test"
    return out


def assign(items: list[dict], store: FactStore, unit: str, ratios, holdout, salt: str = "sahool-qa",
           mode: str = "split") -> tuple[list[dict], dict]:
    report = {"unit": unit, "mode": mode, "dropped": Counter(), "units": {}}
    # de-duplicate: same id, then same normalised question+answer
    seen_ids, seen_text, uniq = set(), set(), []
    for it in items:
        tkey = normalize(it["question"]) + "||" + normalize(it["answer_text"])
        if it["id"] in seen_ids:
            report["dropped"]["duplicate_id"] += 1
            continue
        if tkey in seen_text:
            report["dropped"]["duplicate_text"] += 1
            continue
        seen_ids.add(it["id"])
        seen_text.add(tkey)
        uniq.append(it)
    if mode == "none":
        for it in uniq:
            it["split"] = "eval"
            it["split_units"] = sorted({store.unit_key(store.fields[f], unit) for f in it["field_refs"] if f in store.fields})
        report["dropped"] = dict(report["dropped"])
        report["counts"] = {"eval": len(uniq)}
        return uniq, report

    usplit = unit_splits(store, unit, ratios, holdout, salt)
    kept = []
    for it in uniq:
        units = sorted({store.unit_key(store.fields[f], unit) for f in it["field_refs"] if f in store.fields})
        splits = {usplit[u] for u in units}
        if len(splits) != 1:
            report["dropped"]["cross_split" if splits else "no_known_unit"] += 1
            examples = report.setdefault("dropped_examples", [])
            if len(examples) < 20:
                examples.append({"id": it["id"], "family": it["family"], "units": units})
            continue
        it["split"] = splits.pop()
        it["split_units"] = units
        kept.append(it)

    # leak audit on the record owners themselves, not only declared units:
    # no field whose records appear in an item may feed two different splits
    owner_to_splits = defaultdict(set)
    for it in kept:
        for fk in it["field_refs"]:
            owner_to_splits[fk].add(it["split"])
    leaks = {u: sorted(s) for u, s in owner_to_splits.items() if len(s) > 1}
    if leaks:
        raise RuntimeError(f"split leak detected: {leaks}")
    report["units"] = {s: sorted(u for u, sp in usplit.items() if sp == s) for s in SPLITS}
    report["counts"] = dict(Counter(it["split"] for it in kept))
    report["dropped"] = dict(report["dropped"])
    n_units = len(usplit)
    report["warnings"] = []
    if n_units < 10:
        report["warnings"].append(
            f"only {n_units} split units: the {ratios} ratios cannot be honoured; use --holdout to choose the test units")
    for s in SPLITS:
        if not report["units"][s]:
            report["warnings"].append(f"split '{s}' has no units")
    return kept, report
