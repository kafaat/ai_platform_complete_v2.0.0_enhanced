"""MinIO network isolation (MINIO-COMMUNITY-EDITION-RECEIVES-NO-SECURITY-FIXES-01).

Owner decision 2026-10-25: harden isolation now, as a bounded step under the freeze. MinIO used
to sit on sahool-internal (``internal: false``) with every service of the stack. Now:

- ``sahool-object-storage`` is ``internal: true`` and only the listed S3 clients join it;
- ``sahool-minio`` joins that network and ``sahool-object-storage-loopback`` and nothing else —
  the second exists only because Docker publishes no port for a container on internal networks
  alone, and sahool-minio is its only member;
- every MinIO port is published on 127.0.0.1 alone.

``internal: true`` by itself proves nothing (owner condition 2), so each rule of the gate is
falsified below on the real compose document. Isolation reduces exposure; it does not patch
MinIO, and the maintenance gap stays open (owner condition 4).
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
STORAGE = "sahool-object-storage"
LOOPBACK = "sahool-object-storage-loopback"


def _gate():
    spec = importlib.util.spec_from_file_location(
        "minio_gate_isolation", ROOT / "scripts/ci/minio_s3_contract_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GATE = _gate()


def _doc() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _members(doc: dict, network: str) -> set[str]:
    return {
        name
        for name, spec in doc["services"].items()
        if network in GATE._service_networks(spec or {})
    }


# ── the tree as it stands ────────────────────────────────────────────────────────


def test_the_storage_network_is_internal_and_the_loopback_network_is_not():
    networks = _doc()["networks"]
    assert networks[STORAGE]["internal"] is True
    assert networks[LOOPBACK].get("internal") is not True
    assert not networks[STORAGE].get("external") and not networks[LOOPBACK].get("external")


def test_minio_joins_only_the_storage_and_loopback_networks():
    minio = _doc()["services"]["sahool-minio"]
    assert "network_mode" not in minio
    assert GATE._service_networks(minio) == {STORAGE, LOOPBACK}


def test_exactly_the_s3_clients_share_the_storage_network():
    doc = _doc()
    assert _members(doc, STORAGE) == {"sahool-minio"} | set(GATE.STORAGE_CLIENTS)
    assert _members(doc, LOOPBACK) == {"sahool-minio"}
    # The clients keep the networks their own work needs (database, cache, bus).
    for client in GATE.STORAGE_CLIENTS - {"sahool-minio-init"}:
        assert "sahool-internal" in GATE._service_networks(doc["services"][client]), client
    assert GATE._service_networks(doc["services"]["sahool-minio-init"]) == {STORAGE}


def test_every_service_pointing_at_minio_is_classified():
    doc = _doc()
    pointing = {
        name
        for name, spec in doc["services"].items()
        if any(
            "sahool-minio:" in str(v)
            for v in (
                (spec.get("environment") or {}).values()
                if isinstance(spec.get("environment"), dict)
                else spec.get("environment") or []
            )
        )
    }
    assert pointing == set(GATE.STORAGE_CLIENTS) | set(GATE.S3_ENV_WITHOUT_STORAGE_ACCESS)


def test_minio_ports_are_loopback_only_and_still_published():
    ports = [str(p) for p in _doc()["services"]["sahool-minio"]["ports"]]
    assert ports == ["127.0.0.1:9000:9000", "127.0.0.1:9001:9001"]


@pytest.mark.parametrize("compose", sorted(ROOT.glob("docker-compose*.yml")), ids=lambda p: p.name)
def test_every_compose_file_passes_the_isolation_rules(compose):
    doc = yaml.safe_load(compose.read_text(encoding="utf-8"))
    assert GATE.storage_network_errors(doc, compose.name, base=compose == COMPOSE) == []


# ── each rule, falsified on the real document ───────────────────────────────────


def _errors(mutate, *, base: bool = True) -> list[str]:
    doc = copy.deepcopy(_doc())
    mutate(doc)
    return GATE.storage_network_errors(doc, "docker-compose.v9.yml", base=base)


def _set_internal(value):
    def mutate(doc):
        doc["networks"][STORAGE]["internal"] = value

    return mutate


def _drop_internal(doc):
    del doc["networks"][STORAGE]["internal"]


def _external_storage(doc):
    doc["networks"][STORAGE]["external"] = True


def _undeclared_storage(doc):
    del doc["networks"][STORAGE]


def _internal_loopback(doc):
    doc["networks"][LOOPBACK]["internal"] = True


def _minio_on_internal(doc):
    doc["services"]["sahool-minio"]["networks"].append("sahool-internal")


def _minio_on_public(doc):
    doc["services"]["sahool-minio"]["networks"] = [STORAGE, LOOPBACK, "sahool-public"]


def _minio_host_network(doc):
    doc["services"]["sahool-minio"]["network_mode"] = "host"


def _minio_default_network(doc):
    del doc["services"]["sahool-minio"]["networks"]


def _minio_off_storage(doc):
    doc["services"]["sahool-minio"]["networks"] = [LOOPBACK]


def _redis_on_storage(doc):
    doc["services"]["sahool-redis"]["networks"].append(STORAGE)


def _platform_on_storage_dict_form(doc):
    doc["services"]["sahool-platform"]["networks"] = {"sahool-internal": None, STORAGE: None}


def _client_on_loopback(doc):
    doc["services"]["sahool-raster-service"]["networks"].append(LOOPBACK)


def _client_off_storage(doc):
    doc["services"]["sahool-scout-ingest"]["networks"] = ["sahool-internal"]


def _init_off_storage(doc):
    doc["services"]["sahool-minio-init"]["networks"] = ["sahool-internal"]


def _unclassified_s3_endpoint(doc):
    doc["services"]["sahool-redis"].setdefault("environment", {})
    doc["services"]["sahool-redis"]["environment"]["S3_ENDPOINT"] = "http://sahool-minio:9000"


RULES = {
    "storage internal: false": (_set_internal(False), "must be internal: true"),
    "storage internal: 'true' (a string)": (_set_internal("true"), "must be internal: true"),
    "storage internal missing": (_drop_internal, "must be internal: true"),
    "storage external": (_external_storage, "not external"),
    "storage not declared": (_undeclared_storage, f"network {STORAGE} is not declared"),
    "loopback internal": (_internal_loopback, "would publish no port"),
    "minio on sahool-internal": (_minio_on_internal, "sahool-minio joins ['sahool-internal']"),
    "minio on sahool-public": (_minio_on_public, "sahool-minio joins ['sahool-public']"),
    "minio network_mode: host": (_minio_host_network, "network_mode='host'"),
    "minio on the default network": (_minio_default_network, "sahool-minio joins ['default']"),
    "minio off the storage network": (_minio_off_storage, f"is not on {STORAGE}"),
    "redis joins storage": (_redis_on_storage, "sahool-redis joins sahool-object-storage"),
    "platform joins storage (dict form)": (
        _platform_on_storage_dict_form,
        "sahool-platform joins sahool-object-storage",
    ),
    "a client joins loopback": (_client_on_loopback, f"sahool-raster-service joins {LOOPBACK}"),
    "a client loses storage": (_client_off_storage, "S3 client sahool-scout-ingest is not on"),
    "minio-init loses storage": (_init_off_storage, "S3 client sahool-minio-init is not on"),
    "unclassified sahool-minio endpoint": (
        _unclassified_s3_endpoint,
        "sahool-redis points at sahool-minio",
    ),
}


def test_the_unmutated_document_is_clean():
    assert _errors(lambda doc: None) == []


@pytest.mark.parametrize("rule", sorted(RULES))
def test_each_isolation_rule_fires(rule):
    mutate, needle = RULES[rule]
    errors = _errors(mutate)
    assert any(needle in e for e in errors), (rule, errors)


EXPOSED_PORTS = [
    "0.0.0.0:9000:9000",
    "9000:9000",
    "9000",
    "[::]:9000:9000",
    "${MINIO_BIND:-127.0.0.1}:9000:9000",
    "127.0.0.2:9000:9000",
    {"target": 9000, "published": 9000},
    {"target": 9001, "published": 9001, "host_ip": "0.0.0.0"},
]


@pytest.mark.parametrize("port", EXPOSED_PORTS, ids=str)
def test_a_minio_port_beyond_loopback_is_refused(port):
    def mutate(doc):
        doc["services"]["sahool-minio"]["ports"] = ["127.0.0.1:9001:9001", port]

    errors = _errors(mutate)
    assert any("beyond 127.0.0.1" in e for e in errors), (port, errors)


@pytest.mark.parametrize(
    "port",
    ["127.0.0.1:9000:9000", "'127.0.0.1:59000:9000'", {"target": 9000, "host_ip": "127.0.0.1"}],
    ids=str,
)
def test_loopback_forms_are_accepted(port):
    def mutate(doc):
        doc["services"]["sahool-minio"]["ports"] = [port]

    assert _errors(mutate) == []


def test_any_minio_image_service_is_held_to_loopback_ports_in_any_file():
    """A MinIO service under another name (as in the evidence lab) is held to the same binding."""
    doc = {
        "services": {
            "evidence-minio": {
                "image": "${MINIO_IMAGE:-coollabsio/minio:2025-04-22T22-12-26Z@sha256:"
                + "a" * 64
                + "}",
                "ports": ["0.0.0.0:59000:9000"],
            }
        }
    }
    errors = GATE.storage_network_errors(doc, "docker-compose.lab.yml", base=False)
    assert any("evidence-minio publishes" in e for e in errors), errors


def test_an_overlay_cannot_widen_minio():
    overlay = {"services": {"sahool-minio": {"networks": ["sahool-internal"]}}}
    errors = GATE.storage_network_errors(overlay, "docker-compose.extra.yml", base=False)
    assert any("sahool-minio joins ['sahool-internal']" in e for e in errors), errors


def test_a_companion_file_cannot_join_the_storage_network_by_its_project_name():
    companion = {
        "services": {"erp-worker": {"image": "x", "networks": ["objects"]}},
        "networks": {"objects": {"external": True, "name": "sahool_v9_sahool-object-storage"}},
    }
    errors = GATE.storage_network_errors(companion, "docker-compose.erp.yml", base=False)
    assert any("erp-worker joins sahool-object-storage" in e for e in errors), errors


def test_the_gate_fails_closed_on_mains_compose():
    """On main MinIO sat on sahool-internal (internal: false) with no storage network."""
    main_doc = copy.deepcopy(_doc())
    main_doc["networks"].pop(STORAGE)
    main_doc["networks"].pop(LOOPBACK)
    for spec in main_doc["services"].values():
        nets = (spec or {}).get("networks")
        if isinstance(nets, list) and (STORAGE in nets or LOOPBACK in nets):
            kept = [n for n in nets if n not in (STORAGE, LOOPBACK)]
            spec["networks"] = kept or ["sahool-internal"]
    assert main_doc["services"]["sahool-minio"]["networks"] == ["sahool-internal"]
    errors = GATE.storage_network_errors(main_doc, "docker-compose.v9.yml", base=True)
    assert any(f"network {STORAGE} is not declared" in e for e in errors), errors
    assert any("sahool-minio joins ['sahool-internal']" in e for e in errors), errors
