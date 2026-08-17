#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/architecture/platform_shrink_ratchet.json"
OWNERSHIP = ROOT / "docs/architecture/db_ownership.yml"
CATEGORIES = (
    "platform_domain_table_ownership",
    "platform_domain_compute",
    "platform_provider_clients",
    "platform_authority_exceptions",
)


def _load_policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def observe(policy=None):
    policy = policy or _load_policy()
    tables = yaml.safe_load(OWNERSHIP.read_text(encoding="utf-8"))["tables"]
    table_ids = {
        k for k, v in tables.items() if isinstance(v, dict) and v.get("owner") == "sahool-platform"
    }
    keywords = tuple(policy["measurement"]["domain_compute_keywords"])
    compute = set()
    providers = set()
    # الجذر من السياسة لا مثبَّتاً هنا: العقد يُعلنه، فتثبيتُه في الكود يخلق مصدرين
    # يفترقان بصمت — وهو صنف «المُعلَن ≠ المُطبَّق» الذي يقيسه هذا الراتشِت أصلاً.
    platform_root = policy["measurement"]["platform_root"]
    for p in sorted((ROOT / platform_root).rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if (
            "/tests/" not in rel
            and not rel.endswith("/__init__.py")
            and "/migrations/" not in rel
            and any(seg in rel for seg in ("/core/", "/api/", "/workers/"))
            and any(k in rel.lower() for k in keywords)
        ):
            compute.add(rel)
        low = rel.lower()
        if "/tests/" not in rel and (
            "/connectors/" in low
            or low.endswith("/ai_provider_config.py")
            or low.endswith("/weather_sources.py")
        ):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\b(httpx|aiohttp|requests)\b|https?://|Client\(", txt):
                providers.add(rel)
    auth = {
        f"{k}:mirror:{v['mirror']}"
        for k, v in tables.items()
        if isinstance(v, dict) and v.get("owner") == "sahool-platform" and v.get("mirror")
    }
    return {
        "platform_domain_table_ownership": table_ids,
        "platform_domain_compute": compute,
        "platform_provider_clients": providers,
        "platform_authority_exceptions": auth,
    }


def _valid_exceptions(policy, today):
    out = {}
    f = []
    max_days = int(policy["exception_contract"].get("max_target_days", 180))
    for i, e in enumerate(policy.get("exceptions") or []):
        missing = [k for k in policy["exception_contract"]["required_fields"] if not e.get(k)]
        if missing:
            f.append(f"exception[{i}] missing fields: {','.join(missing)}")
            continue
        cat, ident = e["category"], e["identity"]
        if cat not in CATEGORIES:
            f.append(f"exception[{i}] unknown category {cat}")
            continue
        try:
            close = dt.date.fromisoformat(e["target_close_by"])
        except ValueError:
            f.append(f"exception[{i}] invalid target_close_by")
            continue
        if close < today:
            f.append(f"exception expired: {cat}:{ident}")
            continue
        if (close - today).days > max_days:
            f.append(f"exception target too far: {cat}:{ident}")
            continue
        if (cat, ident) in out:
            # تُبلَّغ **وتُستبعَد**: قبولها يجعل «آخر مَن كتب يفوز»، فيختفي اختلاف
            # المالك والسبب بين نسختين بلا أثر. الأولى تبقى، والثانية لا تدهسها.
            f.append(f"duplicate exception identity: {cat}:{ident}")
            continue
        out[(cat, ident)] = e
    return out, f


def findings(today=None):
    policy = _load_policy()
    observed = observe(policy)
    today = today or dt.date.today()
    exceptions, out = _valid_exceptions(policy, today)
    base = {k: set(policy["baseline"].get(k) or []) for k in CATEGORIES}
    for cat in CATEGORIES:
        obs = observed[cat]
        b = base[cat]
        new = sorted(obs - b)
        stale = sorted(b - obs)
        for ident in new:
            if (cat, ident) not in exceptions:
                out.append(f"NEW {cat}: {ident}")
        for ident in stale:
            out.append(f"STALE {cat}: {ident} — lower baseline")
    for (cat, ident), _e in exceptions.items():
        if ident not in observed[cat] - base[cat]:
            out.append(f"stale/unnecessary exception: {cat}:{ident}")
    return out


def main():
    f = findings()
    if f:
        print("platform_shrink_ratchet_fail")
        for x in f:
            print(" -", x)
        return 1
    o = observe()
    print("platform_shrink_ratchet_ok " + " ".join(f"{k}={len(o[k])}" for k in CATEGORIES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
