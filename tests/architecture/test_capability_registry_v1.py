import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "scripts/ci/capability_registry_v1.py"
spec = importlib.util.spec_from_file_location("capability_registry_v1", P)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def test_registry_is_valid_and_complete():
    idx, domains, caps = m.load()
    assert m.validate(idx, domains, caps) == []
    assert len(idx["domains"]) == 10
    assert len(caps) == 81


def test_ids_are_unique_and_domain_prefixed():
    idx, _, caps = m.load()
    prefixes = {
        d["key"]: set(d.get("accepted_prefixes", [d["capability_prefix"]])) for d in idx["domains"]
    }
    assert len({c["id"] for c in caps}) == len(caps)
    assert all(c["id"].split("-")[0] in prefixes[c["domain"]] for c in caps)


def test_generated_registry_has_no_drift():
    idx, _, caps = m.load()
    got = json.loads((m.OUT / "capability_registry.json").read_text())
    assert got == m.canonical(idx, caps)


def test_all_dependencies_resolve():
    _, _, caps = m.load()
    ids = {c["id"] for c in caps}
    assert all(d in ids for c in caps for d in c.get("dependencies", []))


def test_no_capability_is_implicitly_certified():
    _, _, caps = m.load()
    assert all(not c["production_certified"] for c in caps)
