"""جردُ TLS الداخليّ لـv9 (``docs/architecture/v9_internal_tls_inventory.json``) يُطابِق compose في الاتّجاهين.

الجردُ **مقيسٌ** (مُسجَّلٌ ``measured`` في ``claim_base_registry.json``) لا مكتوبٌ باليد: عميلٌ جديدٌ
لـNATS أو Postgres يظهر في compose بلا سطرٍ هنا يُسقِط الاختبار، وسطرٌ هنا بلا خدمةٍ يُسقِطه —
فلا يبقى جردٌ يشهد على مكدّسٍ لم يعد قائماً. والتحقّقُ الفعليّ لكلّ عميل (``verify-full`` · CA ·
هويّة) في ``test_postgres_tls.py`` و``test_nats_least_privilege.py``؛ هنا التطابقُ والصدقُ عن الحدود.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "architecture" / "v9_internal_tls_inventory.json"
CLAIMS = ROOT / "docs" / "architecture" / "claim_base_registry.json"
COMPOSE = ROOT / "docker-compose.v9.yml"
GAPS = {
    "NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01",
    "POSTGRES-V9-HAS-NO-TLS-SO-EVERY-CLIENT-IS-PLAINTEXT-01",
}
_DSN_KEYS = re.compile(r"(^|_)DATABASE_URL$|^PGHOST$|^DATA_SOURCE_URI$")

pytestmark = [pytest.mark.unit]


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _postgres_clients() -> set[str]:
    out = set()
    for name, svc in _services().items():
        if name in {"sahool-postgres", "sahool-postgres-tls-init"}:
            continue
        env = svc.get("environment") or {}
        if not isinstance(env, dict):
            continue
        if any(
            _DSN_KEYS.search(str(k)) or "sahool-postgres" in str(v) for k, v in env.items()
        ) or "sahool-postgres" in (svc.get("depends_on") or {}):
            out.add(name)
    return out


def _nats_clients() -> dict[str, dict]:
    out = {}
    for name, svc in _services().items():
        env = svc.get("environment") or {}
        if not isinstance(env, dict) or "NATS_URL" not in env:
            continue
        m = re.match(r"^tls://([a-z0-9-]+):\$\{([A-Z0-9_]+):\?", str(env["NATS_URL"]))
        assert m, f"{name}: NATS_URL ليس tls://<هويّة>:${{VAR:?…}}@… — {env['NATS_URL']}"
        out[name] = {"identity": m[1], "password_env": m[2]}
    return out


def test_the_inventory_is_a_registered_measurement_naming_both_gaps():
    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    assert INVENTORY.name in claims["measured"], (
        "الجردُ قياسٌ — يلزمه تسجيلٌ measured وختمُ measured_on"
    )
    inv = _inventory()
    assert inv.get("measured_on"), "قياسٌ بلا ختمِ شجرة"
    assert set(inv["gaps"]) == GAPS


def test_postgres_clients_match_compose_both_ways():
    listed = set(_inventory()["postgres"]["clients"])
    derived = _postgres_clients()
    assert listed == derived, (
        f"في compose لا في الجرد: {sorted(derived - listed)}\n"
        f"في الجرد لا في compose: {sorted(listed - derived)}"
    )


def test_nats_clients_and_their_identities_match_compose_both_ways():
    assert _inventory()["nats"]["clients"] == _nats_clients()


def test_no_exclusion_survives_the_wave_and_unmeasured_limits_are_named():
    inv = _inventory()
    assert "excluded" not in inv, (
        "استثناءُ الموجة (weather-polygon-worker) زال بزوال الخدمة — بقاؤه يُخفي عميلاً عن الجرد"
    )
    assert any("Docker" in item for item in inv["unmeasured"]), (
        "مصافحةُ TLS داخل مكدّس Docker لم تُقَس — يجب أن يقولها الجردُ صراحةً"
    )
    assert "railway" in inv["out_of_scope"]
