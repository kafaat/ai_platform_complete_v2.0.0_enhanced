#!/usr/bin/env python3
"""Unified Platform Catalog compiler (U2) — a COMPILER, not a new service.

Composes the repository's EXISTING sources of truth into one deterministic
catalog of components and capabilities, discovers wiring, and surfaces the
contradictions between registries. It never becomes a new source of truth for
agricultural data — every fact in its output carries the registry it came from.

Inputs (all pre-existing; the only manual file is the overrides):
  service_inventory.generated.json            service discovery
  route_inventory.generated.json              route discovery
  route_mount_inventory.generated.json        http/worker/job classification
  config/service_feature_ui_contracts.json    consumer contracts
  config/endpoint_ui_coverage_waivers.json    UI waivers (classified in U4)
  docs/architecture/db_ownership.yml          table ownership/writers
  config/indicators_registry.json             canonical spectral products
  event_publish_contracts.yaml                NATS producer/consumer contracts
  docker-compose.v9.yml                       DNS names, ports, env wiring
  nginx/nginx.v9.conf                         gateway routing (upstreams)
  config/platform_catalog_overrides.yml       ONLY non-discoverable facts

Outputs (deterministic — no timestamps; re-running must be byte-identical):
  platform_catalog.generated.json
  component_inventory.generated.csv
  capability_inventory.generated.csv
  dependency_graph.generated.json
  ownership_conflicts.generated.json
  orphan_functions.generated.json
  runtime_capability_manifest.generated.json
  docs/architecture/PLATFORM_CATALOG.generated.md

Modes:
  (default)         write outputs in place
  --check           rebuild into memory and fail (exit 1) on any byte difference
  --enforce-expiry  additionally fail (exit 1) on any U4 decision/waiver whose
                    expires_on is in the past — runtime check only; outputs stay
                    date-independent so the byte-drift gate never depends on today

U3 (wiring/ownership): status.wired for backend components is EVIDENCE-driven —
it comes from the hardened service-feature-ui-contract gate (fail-closed evidence
groups, file:line matches, wiring dispositions), never from compose heuristics.
Ownership conflicts are a hard failure (the registry source must stay clean).

U4 (duplicates/waivers): every measured cross-service (method,path) duplicate
group must carry a human decision in the overrides file (classification +
rationale; expiry for temporary classes; facade decisions name distinct group
members). UI waivers get governed owner/expiry/tracking from policy defaults.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import runpy
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

# U4: مفردات تصنيف التكرارات — المؤقّت منها يتطلّب expires_on.
PERMANENT_DUPLICATE_CLASSIFICATIONS = {
    "standard_capability_contract",
    "standard_liveness",
    "standard_observability",
    "standard_readiness",
    "standard_service_contract",
}
KNOWN_DUPLICATE_CLASSIFICATIONS = PERMANENT_DUPLICATE_CLASSIFICATIONS | {
    "legacy_bff_facade",
    "service_metadata",
    "service_scoped_semantics",
    "standard_health_alias",
}

OUTPUTS = [
    "platform_catalog.generated.json",
    "component_inventory.generated.csv",
    "capability_inventory.generated.csv",
    "dependency_graph.generated.json",
    "ownership_conflicts.generated.json",
    "orphan_functions.generated.json",
    "runtime_capability_manifest.generated.json",
    "docs/architecture/PLATFORM_CATALOG.generated.md",
    # U6: بيان الواجهة — عميل TS مولَّد يستهلكه AdminRuntimePage (قراءة فقط).
    "frontend/src/lib/platformCatalog.generated.ts",
]

_STATUS_LADDER = ["discovered", "declared", "wired", "tested", "configured", "activated"]
_HEALTH_PATHS = {"/healthz", "/readyz", "/health", "/", "/metrics", "/contract", "/capabilities"}


# ── loading ──────────────────────────────────────────────────────


def _load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _load_yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


# ── ARCH-S1a: canonical component classification ─────────────────

_COMPONENT_REGISTRY = "docs/architecture/component_registry.json"


def load_component_registry() -> dict:
    """ARCH-S1a: المصدر القانونيّ الواحد لتصنيف المكوّنات. قبل هذا السجلّ كان
    التصنيف يسقط افتراضيّاً إلى service لكلّ مكوّن غير مذكور في overrides —
    فالمكوّن غير المصنَّف كان يمرّ صامتاً. السجلّ يقلب العقد: التصنيف إعلان
    مُحكَّم، والمُصرِّف يُثبته تقاطعيّاً ضدّ الواقع المقيس ويفشل على أيّ فجوة."""
    return _load_json(_COMPONENT_REGISTRY)


def component_classification_failures(registry: dict, measured: dict[str, dict]) -> list[str]:
    """بوّابة S1a النقيّة: صفر مكوّنات غير مصنَّفة، وصفر صفوف بائتة، وكلّ إعلان
    قابل للقياس (deployment_unit/source_path/authority_kind) مطابق للمقيس.

    measured: component_id -> {deployment_unit, source_path, owns_tables}؛
    القياس يأتي من compose المُحلَّل والجرد وملكيّة الجداول — لا من السجلّ نفسه،
    وإلّا صار الإعلان يُثبت الإعلان."""
    failures: list[str] = []
    kinds = set(registry["component_kinds"])
    authorities = set(registry["authority_kinds"])
    entries = registry["components"]
    for cid in sorted(set(measured) - set(entries)):
        failures.append(f"unclassified component: {cid} — أضِف صفّه إلى {_COMPONENT_REGISTRY}")
    for cid in sorted(set(entries) - set(measured)):
        failures.append(f"stale registry entry: {cid} — لا مكوّن مكتشَفاً يقابله")
    for cid in sorted(set(entries) & set(measured)):
        entry, m = entries[cid], measured[cid]
        if entry["component_kind"] not in kinds:
            failures.append(
                f"{cid}: component_kind {entry['component_kind']!r} خارج المفردات المُحكَّمة"
            )
        if entry["authority_kind"] not in authorities:
            failures.append(
                f"{cid}: authority_kind {entry['authority_kind']!r} خارج المفردات المُحكَّمة"
            )
        if entry["deployment_unit"] != m["deployment_unit"]:
            failures.append(
                f"{cid}: deployment_unit المُعلَن {entry['deployment_unit']!r} "
                f"يخالف المقيس {m['deployment_unit']!r}"
            )
        if entry["source_path"] != m["source_path"]:
            failures.append(
                f"{cid}: source_path المُعلَن {entry['source_path']!r} "
                f"يخالف المقيس {m['source_path']!r}"
            )
        if entry["authority_kind"] == "presentation":
            continue
        if (entry["authority_kind"] == "system_of_record") != m["owns_tables"]:
            failures.append(
                f"{cid}: authority_kind {entry['authority_kind']!r} يناقض ملكيّة الجداول "
                f"المقيسة (owns_tables={m['owns_tables']})"
            )
    return failures


_ALLOWED_OVERRIDE_KEYS = {
    "canonical_aliases",
    "components",
    "extra_components",
    "ui_waiver_policy",
    "duplicate_route_classifications",
}


def load_overrides() -> dict:
    data = _load_yaml("config/platform_catalog_overrides.yml") or {}
    unknown = sorted(set(data) - _ALLOWED_OVERRIDE_KEYS)
    if unknown:
        raise ValueError(f"platform_catalog_overrides: unsupported keys {unknown}")
    data.setdefault("canonical_aliases", {})
    data.setdefault("components", {})
    data.setdefault("extra_components", [])
    data.setdefault("ui_waiver_policy", {})
    data.setdefault("duplicate_route_classifications", [])
    return data


# ── U1: canonical naming ─────────────────────────────────────────


def make_canonicalizer(overrides: dict, known: set[str]):
    """U1: alias → canonical. The ``sahool-`` compose/DNS prefix is presentation,
    not identity — but it is stripped ONLY when doing so lands on a known
    component (``sahool-platform`` is itself a real component and must survive)."""
    aliases = dict(overrides["canonical_aliases"])

    def canonical(name: str | None) -> str | None:
        if not name:
            return name
        if name in aliases:
            return aliases[name]
        if name in known:
            return name
        if name.startswith("sahool-"):
            stripped = name[len("sahool-") :]
            if stripped in aliases:
                return aliases[stripped]
            if stripped in known:
                return stripped
        return name

    return canonical


# ── discovery ────────────────────────────────────────────────────


def discover_compose(canonical) -> dict[str, dict]:
    """Per-canonical-component runtime facts from docker-compose.v9.yml."""
    compose = _load_yaml("docker-compose.v9.yml") or {}
    out: dict[str, dict] = {}
    consumes_env: dict[str, set[str]] = {}
    for svc_name, svc in (compose.get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        comp = canonical(svc_name)
        entry = out.setdefault(
            comp, {"compose_services": [], "ports": [], "healthcheck": None, "env_urls": []}
        )
        entry["compose_services"].append(svc_name)
        for p in svc.get("ports") or []:
            entry["ports"].append(str(p))
        hc = svc.get("healthcheck") or {}
        test = hc.get("test")
        if test and not entry["healthcheck"]:
            entry["healthcheck"] = " ".join(test) if isinstance(test, list) else str(test)
        env = svc.get("environment") or {}
        env_items = (
            env.items()
            if isinstance(env, dict)
            else [(str(e).split("=", 1) + [""])[:2] for e in env]
        )
        for key, value in env_items:
            value = str(value)
            m = re.search(r"https?://(sahool-[a-z0-9-]+|[a-z0-9-]+-service|[a-z0-9-]+)[:/]", value)
            if m and str(key).endswith("_URL"):
                target = canonical(m.group(1))
                if target and target != comp:
                    consumes_env.setdefault(comp, set()).add(target)
    for comp, targets in consumes_env.items():
        out.setdefault(comp, {}).setdefault("consumes_services", [])
        out[comp]["consumes_services"] = sorted(targets)
    return out


def discover_nginx(canonical) -> dict:
    """Gateway upstreams + which upstreams are actually proxied."""
    text = (ROOT / "nginx" / "nginx.v9.conf").read_text(encoding="utf-8")
    upstreams: dict[str, str] = {}
    for m in re.finditer(r"upstream\s+(\w+)\s*\{[^}]*server\s+([a-z0-9._-]+):(\d+)", text):
        upstreams[m.group(1)] = canonical(m.group(2))
    proxied = {
        upstreams[m.group(1)]
        for m in re.finditer(r"proxy_pass\s+http://(\w+)", text)
        if m.group(1) in upstreams
    }
    return {
        "upstream_components": sorted(set(upstreams.values())),
        "proxied_components": sorted(proxied),
    }


def discover_db_ownership(canonical) -> tuple[dict[str, list[str]], list[dict]]:
    """tables per canonical owner + conflicts (multi-writer / TBD / alias drift)."""
    text = (ROOT / "docs" / "architecture" / "db_ownership.yml").read_text(encoding="utf-8")
    owner_tables: dict[str, list[str]] = {}
    conflicts: list[dict] = []
    current: str | None = None
    fields: dict[str, str] = {}

    def flush() -> None:
        if not current:
            return
        raw_owner = fields.get("owner", "")
        owner = canonical(raw_owner) or ""
        writers = [canonical(w) for w in re.findall(r"[\w-]+", fields.get("writers", ""))]
        if owner:
            owner_tables.setdefault(owner, []).append(current)
        if current in {"IF", "if"} or not re.match(r"^[a-z][a-z0-9_]*$", current):
            conflicts.append({"table": current, "kind": "bogus_table_name", "raw_owner": raw_owner})
        if not owner or "TBD" in raw_owner:
            conflicts.append({"table": current, "kind": "owner_tbd", "raw_owner": raw_owner})
        extra_writers = sorted({w for w in writers if w and w != owner})
        if extra_writers:
            conflicts.append(
                {
                    "table": current,
                    "kind": "multi_writer",
                    "owner": owner,
                    "extra_writers": extra_writers,
                }
            )
        if raw_owner and canonical(raw_owner) != raw_owner:
            conflicts.append(
                {
                    "table": current,
                    "kind": "alias_owner_name",
                    "raw_owner": raw_owner,
                    "canonical": owner,
                }
            )

    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if m:
            flush()
            current, fields = m.group(1), {}
            continue
        m = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if current and m:
            fields[m.group(1)] = m.group(2).strip()
    flush()
    return {k: sorted(v) for k, v in sorted(owner_tables.items())}, sorted(
        conflicts, key=lambda c: (c["table"], c["kind"])
    )


def discover_events(canonical) -> list[dict]:
    data = _load_yaml("event_publish_contracts.yaml") or {}
    out = []
    for s in data.get("subjects") or []:
        producer = canonical(s.get("producer")) if s.get("producer") else None
        out.append(
            {
                "subject": s.get("subject"),
                "producer": producer,
                "consumer": s.get("consumer"),
                "reserved_future_subject": bool(s.get("reserved_future_subject")),
            }
        )
    return sorted(out, key=lambda e: str(e["subject"]))


def discover_ui_contracts(canonical) -> dict[str, dict]:
    data = _load_json("config/service_feature_ui_contracts.json")
    out = {}
    for row in data.get("services") or []:
        out[canonical(row.get("service"))] = {"classification": row.get("classification")}
    return out


# ── capability derivation (route/event/job) ──────────────────────


def _slug(path: str) -> str:
    parts = [p for p in re.split(r"[/{}}]+", path) if p and p not in {"api", "v1", "v2"}]
    return ".".join(parts[:3]) or "root"


# ── U5: context/governance derivation (discoverable, not invented) ──

# سياق الحقل/الموسم يُكتشَف من مُعامِلات المسار؛ المستأجِر من مجال البوّابة المصادَق.
_FIELD_PARAM = re.compile(r"/fields?/\{|\{field_id\}|/field/\{")
_SEASON_PARAM = re.compile(r"/seasons?/\{|\{season_id\}")
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# رموز idempotency/approval التي يُشتقّ منها الإلزام من جسم دالّة المعالِج (مسح ساكن).
_IDEMPOTENCY_TOKENS = (
    "client_operation_id",
    "Idempotency-Key",
    "idempotency_key",
    "request_digest",
)
_APPROVAL_TOKENS = (
    "approval_queue",
    "requires_decision_center",
    "require_decision_center",
    "pending_approval",
    "enqueue_approval",
)


def _derive_context(path: str) -> list[str]:
    """سياق مُلزَم مُكتشَف: tenant لكلّ مسار خلف بوّابة /api المصادَقة (nginx يحقن
    X-Tenant-Id الموثّق)، وfield/season من مُعامِلات المسار. لا اختلاق."""
    ctx: set[str] = set()
    if path.startswith("/api/"):
        ctx.add("tenant")
    if _FIELD_PARAM.search(path):
        ctx.add("field")
    if _SEASON_PARAM.search(path):
        ctx.add("season")
    return sorted(ctx)


def _function_source_ranges(text: str) -> list[tuple[str, int, int]]:
    """(اسم الدالّة، أوّل سطر، آخر سطر) لكلّ تعريف دالّة عبر ast — حتميّ ودقيق."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            out.append((node.name, start, node.end_lineno or node.lineno))
    return out


def scan_route_governance(routes: list[dict]) -> dict[tuple[str, str, str], dict]:
    """يمسح جسم دالّة كلّ مسار (مرّة واحدة لكلّ ملفّ) لاشتقاق idempotency/approval
    من رموز حقيقيّة في الكود — لا قيمة مُخترَعة، فقط ما يظهر في المصدر."""
    file_cache: dict[str, tuple[str, list[tuple[str, int, int]]]] = {}
    result: dict[tuple[str, str, str], dict] = {}
    for r in routes:
        rel = r.get("file")
        key = (str(r["method"]).upper(), str(r["path"]), str(r.get("function") or ""))
        gov = {"idempotency": False, "approval": False}
        if rel and (ROOT / rel).exists():
            if rel not in file_cache:
                text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
                file_cache[rel] = (text, _function_source_ranges(text))
            text, ranges = file_cache[rel]
            fn, line = r.get("function"), int(r.get("line") or 0)
            body = ""
            best = None
            for name, start, end in ranges:
                if name == fn and start <= line + 3 and end >= line - 3:
                    if best is None or abs(start - line) < abs(best[0] - line):
                        best = (start, end)
            if best:
                lines = text.splitlines()
                body = "\n".join(lines[best[0] - 1 : best[1]])
            if any(tok in body for tok in _IDEMPOTENCY_TOKENS):
                gov["idempotency"] = True
            if any(tok in body for tok in _APPROVAL_TOKENS):
                gov["approval"] = True
        result[key] = gov
    return result


def build_capabilities(
    routes: list[dict], events: list[dict], canonical, ui_contracts
) -> list[dict]:
    route_gov = scan_route_governance(routes)
    caps: dict[str, dict] = {}
    for r in routes:
        comp = canonical(r["service"])
        path = r["path"]
        if path in _HEALTH_PATHS:
            continue
        cap_id = f"{comp}.{_slug(path)}"
        method = str(r["method"]).upper()
        kind = "query" if method in {"GET", "HEAD"} else "command"
        cap = caps.setdefault(
            cap_id,
            {
                "capability_id": cap_id,
                "kind": kind,
                "owner": comp,
                "producer": comp,
                "entrypoints": [],
                "derived_from": "route",
                # U5: السياق/الحَوكمة مُشتقّة من إشارات مُكتشَفة (مُعامِلات المسار +
                # رموز المصدر)، لا مُخترَعة. curated=false يبقى: لا حكم بشريّ يدويّ.
                "required_context": [],
                "approval_required": False,
                "idempotency_required": False,
                "curated": False,
            },
        )
        entry = f"{method} {path}"
        if entry not in cap["entrypoints"]:
            cap["entrypoints"].append(entry)
        if cap["kind"] != kind:
            cap["kind"] = "mixed"
        cap["required_context"] = sorted(set(cap["required_context"]) | set(_derive_context(path)))
        gov = route_gov.get((method, path, str(r.get("function") or "")), {})
        if gov.get("idempotency") and method in _MUTATING_METHODS:
            cap["idempotency_required"] = True
        if gov.get("approval"):
            cap["approval_required"] = True
        ui = ui_contracts.get(comp, {}).get("classification")
        cap["consumers"] = sorted(
            {*(cap.get("consumers") or []), *(["frontend"] if ui == "ui" else [])}
        )
    for e in events:
        if not e["producer"]:
            continue
        cap_id = (
            f"{e['producer']}.event.{hashlib.sha256(str(e['subject']).encode()).hexdigest()[:8]}"
        )
        caps[cap_id] = {
            "capability_id": cap_id,
            "kind": "event",
            "owner": e["producer"],
            "producer": e["producer"],
            "entrypoints": [f"NATS {e['subject']}"],
            "consumers": [e["consumer"]] if e["consumer"] else [],
            "derived_from": "event",
            # الأحداث ليست مسارات HTTP — لا سياق بوّابة يُشتقّ منها ساكناً.
            "required_context": [],
            "approval_required": False,
            "idempotency_required": False,
            "curated": False,
        }
    for cap in caps.values():
        cap["entrypoints"] = sorted(cap["entrypoints"])
        cap.setdefault("consumers", [])
    return sorted(caps.values(), key=lambda c: c["capability_id"])


# ── U3: evidence-driven wiring (hardened consumer gate) ──────────


def run_consumer_gate(canonical) -> tuple[dict[str, dict], list[str]]:
    """يشغّل بوّابة service-feature-ui-contract المُقوّاة ويعيد صفوفها مفهرسةً
    بالاسم القانونيّ + إخفاقاتها. wired هنا مدفوع بالأدلّة (fail-closed) لا
    بتخمينات compose."""
    gate = runpy.run_path(str(ROOT / "scripts" / "ci" / "service_feature_ui_contract_gate.py"))
    _ok, result = gate["run_gate"](ROOT, ROOT / "config" / "service_feature_ui_contracts.json")
    rows = {canonical(row["service"]): row for row in result["services"]}
    return rows, list(result["failures"])


# ── U4: duplicate-route + UI-waiver governance ───────────────────


def govern_duplicates(
    overrides: dict, dup_groups: list[dict], canonical
) -> tuple[list[dict], list[str]]:
    """كلّ مجموعة تكرار مقاسة تحمل قراراً بشريّاً صالحاً؛ القرارات البائتة
    (بلا مجموعة مقاسة) والمجهولة التصنيف والمفتقرة للسبب/الانتهاء إخفاقات."""
    failures: list[str] = []
    decisions: dict[tuple[str, str], dict] = {}
    for row in overrides["duplicate_route_classifications"]:
        key = (str(row.get("method", "")).upper(), str(row.get("path", "")))
        label = f"{key[0]} {key[1]}"
        if key in decisions:
            failures.append(f"{label}: duplicate decision entry")
            continue
        entry = dict(row)
        for field in ("canonical_owner", "facade"):
            if entry.get(field):
                entry[field] = canonical(entry[field])
        classification = str(entry.get("classification") or "")
        if classification not in KNOWN_DUPLICATE_CLASSIFICATIONS:
            failures.append(f"{label}: unknown classification {classification!r}")
        if not str(entry.get("decision") or "").strip():
            failures.append(f"{label}: decision rationale missing")
        expires_on = entry.get("expires_on")
        if expires_on:
            try:
                date.fromisoformat(str(expires_on))
            except ValueError:
                failures.append(f"{label}: invalid expiry {expires_on!r}")
        elif classification not in PERMANENT_DUPLICATE_CLASSIFICATIONS:
            failures.append(f"{label}: temporary decision requires expires_on")
        if classification == "legacy_bff_facade":
            if not entry.get("canonical_owner") or not entry.get("facade"):
                failures.append(f"{label}: legacy facade requires canonical_owner and facade")
            elif entry["canonical_owner"] == entry["facade"]:
                failures.append(f"{label}: canonical_owner and facade must differ")
        decisions[key] = entry

    actual = {(g["method"], g["path"]) for g in dup_groups}
    for method, path in sorted(actual - set(decisions)):
        failures.append(f"{method} {path}: measured duplicate group has no decision")
    for method, path in sorted(set(decisions) - actual):
        failures.append(f"{method} {path}: stale decision (no measured duplicate group)")

    governed: list[dict] = []
    for group in dup_groups:
        decision = decisions.get((group["method"], group["path"]))
        members = set(group["components"])
        if decision:
            for field in ("canonical_owner", "facade"):
                declared = decision.get(field)
                if declared and declared not in members:
                    failures.append(
                        f"{group['method']} {group['path']}: {field} {declared!r} "
                        f"is not a member of {sorted(members)}"
                    )
        governed.append(
            {
                **group,
                "classified": decision is not None,
                "classification": decision.get("classification") if decision else None,
                "canonical_owner": decision.get("canonical_owner") if decision else None,
                "facade": decision.get("facade") if decision else None,
                "expires_on": decision.get("expires_on") if decision else None,
                "decision": decision.get("decision") if decision else None,
            }
        )
    return governed, failures


def govern_waivers(
    overrides: dict, waivers: list[dict], component_ids: set[str], canonical
) -> tuple[list[dict], list[str]]:
    """حَوكمة إعفاءات تغطية الواجهة: مالك مُشتقّ من مصدر المسار أو من السياسة،
    وانتهاء وتتبّع إلزاميّان. المخرَج حتميّ؛ فحص الانتهاء الفعليّ في --enforce-expiry."""
    policy = overrides["ui_waiver_policy"]
    default_owner = canonical(policy.get("default_owner") or "sahool-platform")
    default_expiry = str(policy.get("default_expires_on") or "")
    default_tracking = str(policy.get("default_tracking") or "")
    failures: list[str] = []
    rows: list[dict] = []
    for index, waiver in enumerate(waivers):
        source_services = {
            canonical(m.group(1))
            for item in waiver.get("methods") or []
            if (m := re.search(r"@services/([^/]+)/", str(item)))
        }
        owner = next(iter(source_services)) if len(source_services) == 1 else default_owner
        expires_on = str(waiver.get("expires_on") or waiver.get("expiry") or default_expiry)
        tracking = str(waiver.get("tracking") or default_tracking)
        label = f"waiver[{index}] {waiver.get('endpoint')}"
        try:
            date.fromisoformat(expires_on)
        except ValueError:
            failures.append(f"{label}: invalid expiry {expires_on!r}")
        if owner not in component_ids:
            failures.append(f"{label}: owner {owner!r} is not a catalog component")
        if not tracking:
            failures.append(f"{label}: tracking missing")
        rows.append(
            {
                "waiver_id": f"ui-waiver-{index + 1:03d}",
                "endpoint": waiver.get("endpoint"),
                "owner": owner,
                "expires_on": expires_on,
                "tracking": tracking,
            }
        )
    return rows, failures


# ── assembly ─────────────────────────────────────────────────────


def build() -> dict[str, object]:
    overrides = load_overrides()
    registry = load_component_registry()
    reg_components = registry["components"]
    measured: dict[str, dict] = {}
    services = _load_json("service_inventory.generated.json")
    services = services if isinstance(services, list) else services["services"]
    known = {s["service"] for s in services}
    known |= set(overrides["canonical_aliases"].values())
    known |= {e["component_id"] for e in overrides["extra_components"]}
    canonical = make_canonicalizer(overrides, known)
    routes = _load_json("route_inventory.generated.json")
    routes = routes if isinstance(routes, list) else routes["routes"]
    mounts = {
        canonical(Path(m["path"]).parts[1] if m["path"].startswith("services/") else m["path"]): m
        for m in _load_json("route_mount_inventory.generated.json")
    }
    waivers = _load_json("config/endpoint_ui_coverage_waivers.json").get("waivers", [])
    indicators = _load_json("config/indicators_registry.json")

    compose = discover_compose(canonical)
    gateway = discover_nginx(canonical)
    owner_tables, ownership_conflicts = discover_db_ownership(canonical)
    events = discover_events(canonical)
    ui_contracts = discover_ui_contracts(canonical)
    gate_rows, gate_failures = run_consumer_gate(canonical)

    components: dict[str, dict] = {}
    for s in services:
        raw = s["service"]
        comp_id = canonical(raw)
        reg = reg_components.get(comp_id, {})
        rt = compose.get(comp_id, {})
        measured[comp_id] = {
            "deployment_unit": (
                sorted(rt.get("compose_services", []))[0] if rt.get("compose_services") else None
            ),
            "source_path": f"services/{raw}",
            "owns_tables": bool(owner_tables.get(comp_id)),
        }
        mount = mounts.get(comp_id, {})
        compose_reachable = bool(rt.get("compose_services")) and (
            comp_id in gateway["proxied_components"]
            or any(comp_id in c.get("consumes_services", []) for c in compose.values())
            or bool(rt.get("consumes_services"))
        )
        gate_row = gate_rows.get(comp_id)
        components[comp_id] = {
            "component_id": comp_id,
            "type": reg.get("component_kind", "unclassified"),
            "component_kind": reg.get("component_kind", "unclassified"),
            "deployment_unit": reg.get("deployment_unit"),
            "authority_kind": reg.get("authority_kind", "unclassified"),
            "source_path": reg.get("source_path"),
            "domain": reg.get("domain", "unclassified"),
            "canonical_name": comp_id,
            "aliases": sorted({raw, *rt.get("compose_services", [])} - {comp_id}),
            "runtime": {
                "compose_services": sorted(rt.get("compose_services", [])),
                "published_ports": sorted(rt.get("ports", [])),
                "healthcheck": rt.get("healthcheck"),
                "mount_status": mount.get("status"),
                # قابليّة الوصول عبر compose/البوّابة — إشارة تشغيليّة، ليست دليل استهلاك.
                "compose_reachable": compose_reachable,
            },
            "owns": {"tables": owner_tables.get(comp_id, [])},
            "consumes": {"services": rt.get("consumes_services", [])},
            "sources": {
                "service_inventory": raw,
                "db_ownership": comp_id in owner_tables,
                "ui_contract": ui_contracts.get(comp_id, {}).get("classification"),
            },
            # U3: عقد الاستهلاك المُتحقَّق (أدلّة fail-closed بمواقع file:line).
            "consumer_contract": {
                "declared": gate_row is not None,
                "wiring_disposition": gate_row.get("wiring_disposition") if gate_row else None,
                "evidence_valid": (gate_row["status"] == "pass") if gate_row else None,
                "reopen_trigger": gate_row.get("reopen_trigger") if gate_row else None,
                "evidence_kinds": (
                    sorted({e["kind"] for e in gate_row["evidence"]}) if gate_row else []
                ),
            },
            # سُلَّم الحالة: نُعلن فقط ما نستطيع اشتقاقه صدقاً من المستودع.
            "status": {
                "built": True,
                # U3: wired مدفوع بالأدلّة — consumed المُثبَت فقط True؛
                # «غير-مستهلَك عمداً» False؛ «مهمّة مستقلّة» null.
                "wired": gate_row["wired"] if gate_row else False,
                "tested": bool(s.get("tests")),
                # configured/activated تتطلّب بيئة تشغيل حيّة — لا تُدَّعى ساكناً.
                "configured": None,
                "activated": None,
            },
        }
    for extra in overrides["extra_components"]:
        cid = extra["component_id"]
        reg = reg_components.get(cid, {})
        measured[cid] = {
            "deployment_unit": None,
            "source_path": cid,
            "owns_tables": bool(owner_tables.get(cid)),
        }
        components[cid] = {
            "component_id": cid,
            "type": reg.get("component_kind", "unclassified"),
            "component_kind": reg.get("component_kind", "unclassified"),
            "deployment_unit": reg.get("deployment_unit"),
            "authority_kind": reg.get("authority_kind", "unclassified"),
            "source_path": reg.get("source_path"),
            "domain": reg.get("domain", "unclassified"),
            "canonical_name": cid,
            "aliases": [],
            "runtime": {
                "compose_services": [],
                "published_ports": [],
                "healthcheck": None,
                "mount_status": None,
                "compose_reachable": None,
            },
            "owns": {"tables": owner_tables.get(cid, [])},
            "consumes": {"services": []},
            "consumer_contract": {
                "declared": False,
                "wiring_disposition": None,
                "evidence_valid": None,
                "reopen_trigger": None,
                "evidence_kinds": [],
            },
            "sources": {
                "service_inventory": None,
                "db_ownership": cid in owner_tables,
                "ui_contract": None,
            },
            "status": {
                "built": True,
                "wired": None,
                "tested": None,
                "configured": None,
                "activated": None,
            },
        }

    capabilities = build_capabilities(routes, events, canonical, ui_contracts)

    # orphans: قدرات-مسار تجاريّة لخدمة بلا تصنيف UI/بوّابة ولا إعفاء (تقرير U4، لا بوّابة بعد)
    waived_paths = {w.get("endpoint") for w in waivers}
    orphan = [
        {
            "capability_id": c["capability_id"],
            "owner": c["owner"],
            "entrypoints": c["entrypoints"],
            "reason": "no_ui_contract_classification_and_no_waiver",
        }
        for c in capabilities
        if c["derived_from"] == "route"
        and not c["consumers"]
        and components.get(c["owner"], {}).get("sources", {}).get("ui_contract") is None
        and not any(e.split(" ", 1)[1] in waived_paths for e in c["entrypoints"])
    ]

    edges = []
    for comp in components.values():
        for target in comp["consumes"]["services"]:
            edges.append({"from": comp["component_id"], "to": target, "via": "env_url"})
    for e in events:
        if e["producer"] and e["consumer"]:
            edges.append(
                {"from": e["producer"], "to": e["consumer"], "via": f"nats:{e['subject']}"}
            )
    edges = sorted(edges, key=lambda x: (x["from"], x["to"], x["via"]))

    unique_method_path = sorted({(r["method"], r["path"]) for r in routes})
    dup_groups = {}
    for r in routes:
        dup_groups.setdefault((r["method"], r["path"]), set()).add(canonical(r["service"]))
    cross_service_dups = sorted(
        (
            {"method": k[0], "path": k[1], "components": sorted(v)}
            for k, v in dup_groups.items()
            if len(v) > 1
        ),
        key=lambda d: (d["path"], d["method"]),
    )

    # U4: حَوكمة التكرارات والإعفاءات (إخفاقاتها الساكنة تُفشِل البناء في main)
    cross_service_dups, dup_failures = govern_duplicates(overrides, cross_service_dups, canonical)
    governed_waivers, waiver_failures = govern_waivers(
        overrides, waivers, set(components), canonical
    )

    # U3: إخفاقات السلك/الملكيّة — بوّابة الأدلّة + نظافة سجلّ الملكيّة.
    u3_failures = list(gate_failures) + [
        f"ownership conflict: {c['table']} ({c['kind']})" for c in ownership_conflicts
    ]
    u4_failures = dup_failures + waiver_failures

    # ARCH-S1a: صفر مكوّنات غير مصنَّفة — الإعلان القانونيّ يُثبَت ضدّ المقيس.
    s1a_failures = component_classification_failures(registry, measured)

    catalog = {
        "schema": "sahool.platform_catalog.v1",
        "counts": {
            "components": len(components),
            "backend_components": len(services),
            "route_rows": len(routes),
            "unique_method_path": len(unique_method_path),
            "capabilities": len(capabilities),
            "cross_service_duplicate_method_paths": len(cross_service_dups),
            "duplicate_groups_classified": sum(1 for d in cross_service_dups if d["classified"]),
            "ownership_conflicts": len(ownership_conflicts),
            "ui_waivers": len(waivers),
            # U5: قدرات بسياق مُلزَم مُشتقّ + قدرات بحَوكمة مُشتقّة.
            "capabilities_tenant_scoped": sum(
                1 for c in capabilities if "tenant" in (c.get("required_context") or [])
            ),
            "capabilities_field_scoped": sum(
                1 for c in capabilities if "field" in (c.get("required_context") or [])
            ),
            "capabilities_season_scoped": sum(
                1 for c in capabilities if "season" in (c.get("required_context") or [])
            ),
            "capabilities_idempotent": sum(
                1 for c in capabilities if c.get("idempotency_required")
            ),
            "capabilities_approval_gated": sum(
                1 for c in capabilities if c.get("approval_required")
            ),
            "indicator_products": len(indicators.get("indicators", indicators) or []),
        },
        "components": [components[k] for k in sorted(components)],
        "capabilities": capabilities,
        "cross_service_duplicate_method_paths": cross_service_dups,
        "ui_waiver_governance": governed_waivers,
        "gateway": gateway,
        # U3/U4: بوّابات الحَوكمة — إخفاقاتها ساكنة (لا تعتمد على تاريخ اليوم)؛
        # فحص الانتهاء الزمنيّ يجري في --enforce-expiry دون المساس بالمخرجات.
        "governance": {
            "s1a_component_classification": {
                "passed": not s1a_failures,
                "failures": sorted(s1a_failures),
            },
            "u3_wiring_ownership": {"passed": not u3_failures, "failures": sorted(u3_failures)},
            "u4_duplicates_waivers": {"passed": not u4_failures, "failures": sorted(u4_failures)},
        },
    }
    # U9: شهادة الاتّساق الساكن — تجميع بوّابات U0–U8 في محصّلة واحدة صادقة.
    # صدق صارم: هذه شهادة اتّساق ساكن للسجلّات، وليست شهادة إنتاج
    # (production_certified يبقى مسؤوليّة المسار الحيّ S1..S12، لا يُدَّعى هنا أبداً).
    consistency_checks = {
        "s1a_component_classification_passed": not s1a_failures,
        "zero_ownership_conflicts": len(ownership_conflicts) == 0,
        "zero_governing_orphans": len(orphan) == 0,
        # u3 يشمل شمول العقود (inventory ⊆ contracts) وصحّة الأدلّة fail-closed.
        "u3_passed": not u3_failures,
        "u4_passed": not u4_failures,
        "all_duplicates_classified": all(d["classified"] for d in cross_service_dups),
    }
    catalog["certification"] = {
        "schema": "sahool.static_consistency.v1",
        "static_consistency_certified": all(consistency_checks.values()),
        "checks": consistency_checks,
        "production_certified": False,
        "note": (
            "static registry-consistency only; live production certification "
            "(S1..S12) is never asserted by this compiler"
        ),
    }
    canonical_bytes = json.dumps(
        catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    catalog["fingerprint"] = hashlib.sha256(canonical_bytes).hexdigest()

    manifest = {
        "schema": "sahool.runtime_capability_manifest.v1",
        "note": (
            "static declaration only — configured/activated require live readiness; "
            "the UI must degrade on live /readyz, never on this file alone"
        ),
        "components": [
            {
                "component_id": c["component_id"],
                "type": c["type"],
                "domain": c["domain"],
                "status": c["status"],
                "wiring_disposition": c["consumer_contract"]["wiring_disposition"],
                "capability_count": sum(
                    1 for cap in capabilities if cap["owner"] == c["component_id"]
                ),
            }
            for c in catalog["components"]
        ],
        "fingerprint": catalog["fingerprint"],
    }

    return {
        "catalog": catalog,
        "graph": {"schema": "sahool.dependency_graph.v1", "edges": edges},
        "conflicts": {"schema": "sahool.ownership_conflicts.v1", "conflicts": ownership_conflicts},
        "orphans": {"schema": "sahool.orphan_functions.v1", "orphans": orphan},
        "manifest": manifest,
    }


# ── rendering ────────────────────────────────────────────────────


def _dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _components_csv(catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "component_id",
            "component_kind",
            "deployment_unit",
            "domain",
            "authority_kind",
            "source_path",
            "aliases",
            "compose_services",
            "tables_owned",
            "wired",
            "tested",
        ]
    )
    for c in catalog["components"]:
        w.writerow(
            [
                c["component_id"],
                c["component_kind"],
                c["deployment_unit"] or "",
                c["domain"],
                c["authority_kind"],
                c["source_path"],
                "|".join(c["aliases"]),
                "|".join(c["runtime"]["compose_services"]),
                len(c["owns"]["tables"]),
                c["status"]["wired"],
                c["status"]["tested"],
            ]
        )
    return buf.getvalue()


def _capabilities_csv(catalog) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        ["capability_id", "kind", "owner", "entrypoints", "consumers", "derived_from", "curated"]
    )
    for c in catalog["capabilities"]:
        w.writerow(
            [
                c["capability_id"],
                c["kind"],
                c["owner"],
                "|".join(c["entrypoints"]),
                "|".join(c["consumers"]),
                c["derived_from"],
                c["curated"],
            ]
        )
    return buf.getvalue()


def _markdown(bundle) -> str:
    cat = bundle["catalog"]
    n = cat["counts"]
    lines = [
        "# Unified Platform Catalog (generated — do not edit)",
        "",
        "مُصرِّف كتالوج، لا خدمة: يركّب السجلّات القائمة ويكشف تناقضاتها. أعد التوليد بـ",
        "`python scripts/architecture/build_platform_catalog.py`؛ التحقّق بـ`--check`.",
        "",
        f"- fingerprint: `{cat['fingerprint']}`",
        f"- components: **{n['components']}** (backend: {n['backend_components']})",
        f"- route rows: **{n['route_rows']}** → unique method/path: **{n['unique_method_path']}**",
        f"- capabilities (derived, uncurated): **{n['capabilities']}**",
        f"- cross-service duplicate method/paths: **{n['cross_service_duplicate_method_paths']}**",
        f"- ownership conflicts (incl. TBD/alias): **{n['ownership_conflicts']}**",
        f"- UI waivers pending U4 classification: **{n['ui_waivers']}**",
        "",
        "## Components",
        "",
        "| component | type | domain | aliases | tables | wired |",
        "|---|---|---|---|---|---|",
    ]
    for c in cat["components"]:
        lines.append(
            f"| {c['component_id']} | {c['type']} | {c['domain']} | "
            f"{', '.join(c['aliases']) or '—'} | {len(c['owns']['tables'])} | {c['status']['wired']} |"
        )
    lines += [
        "",
        "## Governance gates (U3/U4)",
        "",
        f"- U3 wiring/ownership: `{'PASS' if cat['governance']['u3_wiring_ownership']['passed'] else 'FAIL'}`",
        f"- U4 duplicates/waivers: `{'PASS' if cat['governance']['u4_duplicates_waivers']['passed'] else 'FAIL'}`",
        "",
        "## Cross-service duplicate method/paths — governed decisions",
        "",
        "| method | path | classification | canonical owner | review |",
        "|---|---|---|---|---|",
    ]
    for d in cat["cross_service_duplicate_method_paths"]:
        lines.append(
            f"| `{d['method']}` | `{d['path']}` | `{d['classification']}` | "
            f"`{d['canonical_owner'] or 'service-local'}` | `{d['expires_on'] or 'permanent'}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _frontend_ts(bundle) -> str:
    """U6: بيان كتالوج مقروء للواجهة — عميل TS مولَّد حتميّ يستهلكه AdminRuntimePage.
    صدق: يعكس status الساكن فقط (built/wired/tested)؛ configured/activated تبقى
    runtime-only، والواجهة تتدهور على /readyz الحيّ لا على هذا الملفّ وحده."""
    cat = bundle["catalog"]
    manifest = bundle["manifest"]
    counts = cat["counts"]
    rows = []
    for comp in manifest["components"]:
        st = comp["status"]
        rows.append(
            {
                "id": comp["component_id"],
                "type": comp["type"],
                "domain": comp["domain"],
                "wired": st["wired"],
                "wiringDisposition": comp.get("wiring_disposition"),
                "tested": st["tested"],
                "capabilityCount": comp["capability_count"],
            }
        )
    body = json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2)
    counts_body = json.dumps(counts, ensure_ascii=False, sort_keys=True, indent=2)
    lines = [
        "// AUTO-GENERATED from platform_catalog.generated.json — do not edit by hand.",
        "// Regenerate: python scripts/architecture/build_platform_catalog.py",
        "// Drift guard (--check) blocks divergence from the deterministic compiler.",
        "// Honesty: `wired`/`tested` are static-derived; configured/activated are",
        "// runtime-only and NEVER asserted here — the UI must degrade on live /readyz.",
        "",
        "export interface CatalogComponent {",
        "  id: string;",
        "  type: string;",
        "  domain: string;",
        "  wired: boolean | null;",
        "  wiringDisposition: string | null;",
        "  tested: boolean | null;",
        "  capabilityCount: number;",
        "}",
        "",
        f"export const PLATFORM_CATALOG_FINGERPRINT = '{cat['fingerprint']}';",
        "",
        f"export const PLATFORM_CATALOG_COUNTS = {counts_body} as const;",
        "",
        f"export const PLATFORM_CATALOG_COMPONENTS: CatalogComponent[] = {body};",
        "",
    ]
    return "\n".join(lines)


def render(bundle) -> dict[str, str]:
    return {
        "platform_catalog.generated.json": _dump_json(bundle["catalog"]),
        "component_inventory.generated.csv": _components_csv(bundle["catalog"]),
        "capability_inventory.generated.csv": _capabilities_csv(bundle["catalog"]),
        "dependency_graph.generated.json": _dump_json(bundle["graph"]),
        "ownership_conflicts.generated.json": _dump_json(bundle["conflicts"]),
        "orphan_functions.generated.json": _dump_json(bundle["orphans"]),
        "runtime_capability_manifest.generated.json": _dump_json(bundle["manifest"]),
        "docs/architecture/PLATFORM_CATALOG.generated.md": _markdown(bundle),
        "frontend/src/lib/platformCatalog.generated.ts": _frontend_ts(bundle),
    }


def _expiry_failures(catalog: dict) -> list[str]:
    """فحص زمنيّ (وقت التشغيل فقط): قرارات/إعفاءات انتهت صلاحيّتها. لا يلمس
    المخرجات — فتبقى حتميّة بايتاً-ببايت مهما كان تاريخ اليوم."""
    today = date.today()
    failures = []
    for d in catalog["cross_service_duplicate_method_paths"]:
        if d["expires_on"] and date.fromisoformat(d["expires_on"]) < today:
            failures.append(
                f"expired duplicate decision: {d['method']} {d['path']} ({d['expires_on']})"
            )
    for w in catalog["ui_waiver_governance"]:
        if w["expires_on"] and date.fromisoformat(w["expires_on"]) < today:
            failures.append(
                f"expired ui waiver: {w['waiver_id']} {w['endpoint']} ({w['expires_on']})"
            )
    return failures


def main() -> int:
    check = "--check" in sys.argv
    enforce_expiry = "--enforce-expiry" in sys.argv
    rendered = render(build())

    catalog = json.loads(rendered["platform_catalog.generated.json"])
    governance_failures = [
        f for gate in catalog["governance"].values() if not gate["passed"] for f in gate["failures"]
    ]
    if governance_failures:
        print("platform-catalog governance FAIL:")
        for failure in governance_failures:
            print(f"  ✗ {failure}")
        return 1
    if enforce_expiry:
        expired = _expiry_failures(catalog)
        if expired:
            print("platform-catalog expiry FAIL:")
            for failure in expired:
                print(f"  ✗ {failure}")
            return 1

    if check:
        drift = [
            rel
            for rel, content in rendered.items()
            if not (ROOT / rel).exists() or (ROOT / rel).read_text(encoding="utf-8") != content
        ]
        if drift:
            print("platform-catalog drift; rerun scripts/architecture/build_platform_catalog.py:")
            for rel in drift:
                print(f"  ✗ {rel}")
            return 1
        print("platform_catalog_check_ok")
        return 0
    # determinism self-proof: building twice must produce identical bytes
    rendered2 = render(build())
    if rendered != rendered2:
        print("platform-catalog is non-deterministic — refusing to write")
        return 2
    for rel, content in rendered.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print(
        "platform_catalog_written "
        f"components={json.loads(rendered['platform_catalog.generated.json'])['counts']['components']} "
        f"fingerprint={json.loads(rendered['platform_catalog.generated.json'])['fingerprint'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
