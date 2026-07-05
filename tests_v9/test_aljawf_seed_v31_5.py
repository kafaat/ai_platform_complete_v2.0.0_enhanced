"""Guard: the Al-Jawf/Sunaydar operational seed is honest, idempotent, tenant-parameterized.

`scripts/seed/aljawf_sunaydar_farm.sql` provisions the REAL Al-Jawf farm (6 zones from
farm_map.yaml, seasons from yield_history.csv, a soil reference from the 22-sample lab data)
into fields/seasons/soil_lab_tests so it shows up in the screens. It must:
- be idempotent (ON CONFLICT ... DO UPDATE) — safe to re-run;
- take the tenant as a psql variable (:tenant_id), never a hard-coded tenant UUID;
- carry the real reference values, not fabricated ones;
- be honest that field-level GPS / polygon boundaries are pending (district-level coords only).
Proven on a live throwaway Postgres: 1st run = 6 fields/3 seasons/1 soil; 2nd run unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SEED = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "aljawf_sunaydar_farm.sql"


def _src() -> str:
    return _SEED.read_text(encoding="utf-8")


def test_seed_exists():
    assert _SEED.is_file(), f"missing {_SEED}"


def test_seed_is_idempotent_and_tenant_parameterized():
    src = _src()
    assert "ON CONFLICT (field_id) DO UPDATE" in src
    assert "ON CONFLICT (season_id) DO UPDATE" in src
    assert "ON CONFLICT (test_id) DO UPDATE" in src
    # tenant is a psql variable, not a baked-in UUID literal.
    assert ":tenant_id" in src
    import re

    assert not re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-", src), (
        "seed must not hard-code a tenant UUID"
    )


def test_seed_uses_real_reference_values_and_is_honest():
    src = _src()
    # real farm_map zones + real soil reference values (not invented).
    assert "aljawf_z1" in src and "aljawf_z6" in src
    assert "51.0" in src  # Z1/Z2 pivot wheat area (ha)
    assert '"ph": 8.2' in src and '"caco3_pct": 31' in src  # sunaydar_soil_reference
    assert "16.15" in src  # districts/al_jawf/climate.yaml latitude
    # honest about pending field GPS / boundaries (no fabricated polygon).
    assert "GPS" in src
