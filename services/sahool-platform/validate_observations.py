"""
validate_observations.py
========================
Runs BEFORE any recommendation. Reads the observation matrix + a tenant's
available observations, then:

  1. Classifies coverage by criticality (A/B/C).
  2. Enforces the no-fallback rule for strict governing observables.
  3. Computes a QUALITY GRADE (birth certificate) for the recommendation.
  4. Reports which fallbacks would activate.

This is the gate that makes the platform refuse unsafe/blind recommendations
and tell the user exactly how trustworthy the answer is.

Usage:
    python validate_observations.py <tenant_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

CORE = Path(__file__).parent / "core"
MATRIX = CORE / "observation_matrix.yaml"
FALLBACK = Path(__file__).parent / "fallback.yaml"


def load_matrix() -> list[dict]:
    return yaml.safe_load(open(MATRIX, encoding="utf-8"))["observables"]


def load_fallback() -> dict:
    return yaml.safe_load(open(FALLBACK, encoding="utf-8"))


def available_observables(tenant_dir: Path) -> set[str]:
    """Infer which observables a tenant currently provides.
    In production this reads live sensor/data feeds. Here we infer from
    the tenant's files (farm_map, well_specs, yield_history, economics)."""
    available: set[str] = set()
    fm = tenant_dir / "farm_map.yaml"
    if fm.exists():
        # farm map implies: crop variety (O1), area (O5), energy (I6), irrigation
        available |= {"O1", "O5", "I6"}
    if (tenant_dir / "well_specs.yaml").exists():
        available |= {"I5"}              # well depth
    if (tenant_dir / "yield_history.csv").exists():
        available |= {"G1", "O2"}        # actual yield + planting dates
    if (tenant_dir / "economics.yaml").exists():
        available |= {"E2"}              # installed power
    return available


def validate(tenant_dir: Path) -> dict:
    matrix = load_matrix()
    fb = load_fallback()
    avail = available_observables(tenant_dir)

    by_crit = {"A": [], "B": [], "C": []}
    for o in matrix:
        by_crit[o["criticality"]].append(o["id"])

    missing_A = [o for o in by_crit["A"] if o not in avail]
    missing_B = [o for o in by_crit["B"] if o not in avail]

    # enforce no-fallback governing observables
    no_fb = set(fb["no_fallback_allowed"])
    blocking = [o for o in missing_A if o in no_fb]

    # which fallbacks would activate
    activatable = {k: v for k, v in fb["fallbacks"].items() if k not in avail}

    # quality grade
    a_present = len(by_crit["A"]) - len(missing_A)
    if blocking:
        grade = "BLOCKED"
    elif missing_A:
        grade = "LOW"        # missing some A (but not blocking governing)
    elif len(missing_B) > 3:
        grade = "MEDIUM"
    else:
        grade = "HIGH"

    return {
        "tenant": tenant_dir.name,
        "available_count": len(avail),
        "A_present": f"{a_present}/{len(by_crit['A'])}",
        "missing_A": missing_A,
        "missing_B_count": len(missing_B),
        "blocking_observables": blocking,
        "activatable_fallbacks": list(activatable.keys()),
        "quality_grade": grade,
    }


def print_report(r: dict) -> None:
    print("═" * 60)
    print(f"  شهادة جودة التوصية — {r['tenant']}")
    print("═" * 60)
    print(f"  المراصد المتاحة:        {r['available_count']}")
    print(f"  الفئة A (العمود الفقري): {r['A_present']}")
    if r["missing_A"]:
        print(f"  ⚠️ ناقص من A:           {r['missing_A']}")
    print(f"  ناقص من B:              {r['missing_B_count']}")
    if r["blocking_observables"]:
        print(f"  🛑 حاكمات مانعة:        {r['blocking_observables']}")
        print("     → النظام لا يُصدر توصية (حاكم صارم غائب)")
    if r["activatable_fallbacks"]:
        print(f"  🔄 سيناريوهات سقوط:     {r['activatable_fallbacks']}")
    grade_ar = {"HIGH": "عالية ✅", "MEDIUM": "متوسطة 🟡",
                "LOW": "منخفضة 🟠", "BLOCKED": "محجوبة 🛑"}
    print(f"  درجة الجودة:            {grade_ar.get(r['quality_grade'])}")
    print("═" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # default to tenant 001 for demo
        td = Path(__file__).parent / "tenants" / "001-aljawf-142ha"
    else:
        td = Path(sys.argv[1])
    print_report(validate(td))
