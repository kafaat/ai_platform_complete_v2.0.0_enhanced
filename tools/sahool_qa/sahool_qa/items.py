"""Item construction: options, distractors, abstention, deterministic ids."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field

from .arabic import LETTERS, decimals_for, fmt_range, nice_width, normalize
from .config import ABSTAIN_TEXT, EVIDENCE_KINDS, LEVELS
from .facts import FactStore


@dataclass
class GenContext:
    store: FactStore
    rules: dict
    seed: int = 7
    split_unit: str = "site"
    stats: dict = field(default_factory=dict)  # family -> {"made": n, "skipped": {reason: n}}
    cache: dict = field(default_factory=dict)

    def rng(self, key: str) -> random.Random:
        return random.Random(f"{self.seed}:{key}")

    def skip(self, family: str, reason: str):
        fam = self.stats.setdefault(family, {"made": 0, "skipped": {}})
        fam["skipped"][reason] = fam["skipped"].get(reason, 0) + 1

    def made(self, family: str):
        self.stats.setdefault(family, {"made": 0, "skipped": {}})["made"] += 1


def item_id(family: str, params: dict) -> str:
    blob = json.dumps({"f": family, **params}, sort_keys=True, ensure_ascii=False, default=str)
    return "sq-" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def numeric_bins(
    value: float,
    width: float,
    n: int,
    rng: random.Random,
    floor: float | None = 0.0,
    ceil: float | None = None,
) -> tuple[list[tuple[float, float]], int]:
    """n consecutive bins of `width` with `value` inside one of them.

    The grid offset (0 or width/2) is chosen so the value sits at least a
    quarter-width from any edge, so small disagreements in how the value is
    computed (spheroid vs local frame, rounding) cannot flip the answer.
    """
    import math

    if ceil is not None and value >= ceil:
        value = ceil - width * 1e-6
    if floor is not None and ceil is not None:
        n = max(2, min(n, int((ceil - floor) / width + 1e-9)))
    base = floor if floor is not None else 0.0
    dec_w = decimals_for(width)
    cands = []
    for k in range(5):
        off = round(k * width / 5, 10)
        lo = math.floor((value - base - off) / width) * width + base + off
        if floor is not None and lo < floor - 1e-12:
            continue
        if ceil is not None and lo + width > ceil + 1e-12:
            continue
        margin = min(value - lo, lo + width - value)
        extra = decimals_for(off) > dec_w  # offset would need more display decimals
        cands.append((lo, margin, extra, k))
    if not cands:  # only the floor-aligned grid fits
        cands = [(math.floor((value - base) / width) * width + base, 0.0, False, 0)]
    # natural grid when the value is comfortably inside a bin; otherwise the
    # tidiest offset that keeps the value at least a fifth of a width from an edge
    natural = [c for c in cands if c[3] == 0 and c[1] >= 0.25 * width]
    tidy = [c for c in cands if not c[2] and c[1] >= 0.2 * width]
    best = (
        natural[0]
        if natural
        else max(tidy, key=lambda c: c[1])
        if tidy
        else max(cands, key=lambda c: c[1])
    )
    lo = best[0]
    pos = rng.randrange(n)
    start = lo - pos * width
    if floor is not None and start < floor - 1e-12:
        start += math.ceil((floor - start) / width - 1e-9) * width
    if ceil is not None and start + n * width > ceil + 1e-12:
        start -= math.ceil((start + n * width - ceil) / width - 1e-9) * width
    bins = [(start + i * width, start + (i + 1) * width) for i in range(n)]
    idx = next(i for i, (a, b) in enumerate(bins) if a - 1e-12 <= value < b)
    return bins, idx


def bin_options(
    value: float,
    rel_width: float,
    unit: str,
    rng: random.Random,
    *,
    min_width: float = 0.0,
    floor: float | None = 0.0,
    ceil: float | None = None,
    width: float | None = None,
    n: int = 4,
) -> tuple[str, list[str], dict]:
    w = width or max(nice_width(abs(value) * rel_width), min_width)
    bins, idx = numeric_bins(value, w, n, rng, floor=floor, ceil=ceil)
    d = min(4, max(decimals_for(round(e, 6)) for ab in bins for e in ab))
    texts = [fmt_range(a, b, unit, d) for a, b in bins]
    meta = {"bin_width": w, "bins": [[round(a, 6), round(b, 6)] for a, b in bins]}
    return texts[idx], [t for i, t in enumerate(texts) if i != idx], meta


def make_item(
    ctx: GenContext,
    *,
    family: str,
    level: str,
    question: str,
    correct: str | None,
    distractors: list[str],
    evidence: dict,
    context,
    key: dict,
    field_refs: list[str] | None = None,
    answerable: bool = True,
    allow_abstain: bool = True,
    answer_value=None,
    max_options: int = 4,
) -> dict | None:
    """Assemble one multiple-choice item. Returns None (and records why) when
    there are not enough distinct options.

    Dependencies: the item depends on every field that owns a record shown in
    its context (Cards) or listed in its evidence, plus `field_refs`. The split
    stage drops any item whose dependencies span two splits."""
    # REA defaults an unlabelled finding to "observed". Here there is no default:
    # a computed value silently recorded as a measurement is exactly the error
    # the observed / derived / inferred split exists to prevent.
    if evidence.get("kind") not in EVIDENCE_KINDS:
        raise ValueError(
            f"{family}: evidence['kind'] must be one of {sorted(EVIDENCE_KINDS)}, got {evidence.get('kind')!r}"
        )
    deps = set(field_refs or [])
    if hasattr(context, "keys"):
        deps |= context.keys
        context = context.render()
    deps |= {r["field_key"] for r in evidence.get("records", []) if r.get("field_key")}
    if not deps or any(d not in ctx.store.fields for d in deps):
        ctx.skip(family, "unknown_dependency")
        return None
    iid = item_id(family, key)
    rng = ctx.rng(iid)
    if not answerable:
        correct = ABSTAIN_TEXT
    seen = {normalize(correct)}
    uniq = []
    for d in distractors:
        nd = normalize(d)
        if nd not in seen:
            seen.add(nd)
            uniq.append(d)
    if not 2 <= max_options <= len(LETTERS):
        raise ValueError("max_options exceeds supported answer letters")
    uniq = uniq[: max_options - 1]
    if (
        answerable
        and allow_abstain
        and ABSTAIN_TEXT not in uniq
        and rng.random() < ctx.rules["abstain_option_rate"]
    ):
        uniq = uniq[: max_options - 2] + [ABSTAIN_TEXT]
    if len(uniq) < 1 or (len(uniq) < 2 and answerable):
        ctx.skip(family, "too_few_distinct_options")
        return None
    opts = [correct] + uniq
    rng.shuffle(opts)
    ans = opts.index(correct)
    ctx.made(family)
    return {
        "id": iid,
        "family": family,
        "level": level,
        "level_ar": LEVELS[level],
        "question": question,
        "options": [{"key": LETTERS[i], "text": t} for i, t in enumerate(opts)],
        "answer": LETTERS[ans],
        "answer_text": correct,
        "answer_value": answer_value,
        "answerable": answerable,
        "abstain_offered": ABSTAIN_TEXT in opts,
        "context": context,
        "evidence": evidence,
        "field_refs": sorted(deps),
        "synthetic": ctx.store.synthetic or bool(evidence.get("synthetic_raster")),
    }
