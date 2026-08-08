#!/usr/bin/env python3
"""Build a deterministic repository-to-capability evidence map for SAHOOL.

This scanner is intentionally conservative. It never upgrades maturity, runtime verification,
or production certification. It maps static repository evidence only and emits review queues for
unmapped/ambiguous artifacts.

NOT AUTHORITATIVE. This is the raw scanner-candidate view. Its ``mapped`` reflects specific
implementation-dimension evidence only (backend/routes/db/events/web/mobile/tests) — an honest
LOWER BOUND. The AUTHORITATIVE mapped/unmapped state is the management matrix
(``capability_management_engine.py`` → ``.../management/coverage_dashboard.json``), which also
credits registry-declared on-disk evidence this scanner cannot attribute. Every scanner-mapped
capability is a subset of the management-mapped set; ``governance``/``other_evidence`` buckets are
reported but never promote a capability here (see the honesty invariant at the mapped= computation).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/capability-registry/generated/capability_registry.json"
OUT = ROOT / "docs/capability-registry/generated/mapping"

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".dart",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".md",
}
SKIP_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".next",
    # Agent knowledge base: prose memory, not implementation evidence. It is not in
    # the release bundle and is rewritten every session, so scanning it both injects
    # spurious keyword hits (e.g. "IF" in narrative text) and makes the map churn —
    # line-number shifts flip which equal-score hit wins, drifting CI vs local.
    "sahool-brain",
}

# High-signal synonyms. Generic words are deliberately absent.
ALIASES: dict[str, tuple[str, ...]] = {
    "FM-001": ("tenant", "organization", "multi tenancy"),
    "FM-002": ("farm", "farms"),
    "FM-003": ("field boundary", "field geometry", "field workspace"),
    "FM-004": ("crop season", "season lifecycle", "season"),
    "FM-005": ("cultivar", "crop catalog", "variety"),
    "FM-006": ("farm economics", "profitability", "cost ledger"),
    "FM-007": ("inventory", "procurement", "warehouse"),
    "FM-008": ("erp bridge", "odoo bridge", "accounting integration"),
    "GIS-001": ("geometry validation", "topology", "polygon validity"),
    "GIS-002": ("gis layer", "map layer", "vector layer"),
    "GIS-003": ("terrain", "hillshade", "contour", "slope", "dem"),
    "GIS-004": ("zonal statistics", "spatial analysis", "geospatial"),
    "SAT-001": ("sentinel", "stac", "cdse", "satellite scene"),
    "SAT-002": ("true color", "truecolor", "rgb composite"),
    "SAT-003": ("ndvi",),
    "SAT-004": ("ndmi",),
    "SAT-005": ("cloud mask", "scene cloud", "aoi cloud", "scl"),
    "SAT-006": ("historical imagery", "scene timeline", "backfill scene"),
    "SAT-007": ("change detection",),
    "SAT-008": ("stress zone", "crop stress"),
    "SAT-009": ("cloud optimized geotiff", "cog", "tilejson", "raster tile"),
    "WX-001": ("current weather",),
    "WX-002": ("weather forecast", "forecast"),
    "WX-003": ("historical weather", "weather history"),
    "WX-004": ("et0", "reference evapotranspiration"),
    "WX-005": ("vpd", "vapour pressure deficit", "vapor pressure deficit"),
    "WX-006": ("gdd", "growing degree"),
    "WX-007": ("frost risk", "heat risk"),
    "WX-008": ("spray window", "operation window", "harvest window"),
    "WX-009": ("disease risk", "late blight", "downy mildew", "stripe rust"),
    "WX-010": ("canonical weather", "weather provenance", "weather quality"),
    "SOIL-001": ("soil profile",),
    "SOIL-002": ("soil sampling", "sampling plan"),
    "SOIL-003": ("lab result", "laboratory"),
    "SOIL-004": ("soil nutrient", "organic matter", "soil analysis"),
    "SOIL-005": ("field capacity", "wilting point", "soil water holding", "total available water"),
    "IRR-001": ("water source", "well registry"),
    "IRR-002": ("water quality", "water sample"),
    "IRR-003": ("field water source", "source binding"),
    "IRR-004": ("water balance", "depletion ledger"),
    "IRR-005": ("irrigation recommendation",),
    "IRR-006": ("irrigation schedule",),
    "IRR-007": ("irrigation execution", "pump command", "valve command"),
    "IRR-008": ("irrigation receipt", "execution verification"),
    "IRR-009": ("water suitability", "sodium adsorption ratio", "sodicity", "salinity"),
    "IRR-010": ("leaching requirement", "drainage requirement"),
    "IRR-011": ("irrigation learning", "irrigation calibration"),
    "PA-001": ("management zone", "productivity zone"),
    "PA-002": ("variable rate", "prescription map"),
    "PA-003": ("yield map",),
    "PA-004": ("as applied",),
    "PA-005": ("machine telemetry", "isoxml"),
    "PA-006": ("equipment calibration", "machine calibration"),
    "OPS-001": ("field task", "task management"),
    "OPS-002": ("work order",),
    "OPS-003": ("scouting",),
    "OPS-004": ("field form",),
    "OPS-005": ("offline sync", "sync queue"),
    "OPS-006": ("farm equipment", "machinery"),
    "OPS-007": ("equipment maintenance", "maintenance record"),
    "OPS-008": ("workforce", "operator assignment"),
    "DEC-001": ("decision evidence", "evidence packet"),
    "DEC-002": ("decision candidate", "candidate recommendation"),
    "DEC-003": ("approval workflow", "decision approval"),
    "DEC-004": ("execution request",),
    "DEC-005": ("dispatch authorization",),
    "DEC-006": ("execution receipt",),
    "DEC-007": ("decision outcome", "outcome record"),
    "DEC-008": ("learning attribution", "outcome attribution"),
    "DEC-009": ("model calibration", "evaluation run"),
    "DEC-010": ("model activation", "model rollback", "model promotion"),
    "SEC-001": ("row level security", "rls", "tenant isolation"),
    "SEC-002": ("tenant assertion", "signed tenant"),
    "SEC-003": ("worker identity", "service identity"),
    "SEC-004": ("mfa", "totp", "recovery code"),
    "SEC-005": ("audit log", "audit event"),
    "SEC-006": ("service token", "internal token"),
    "SEC-007": ("system of record", "decision sor"),
    "SEC-008": ("fail closed", "production secret guard"),
    "INT-001": ("openapi", "public sdk"),
    "INT-002": ("nats", "jetstream", "event bus"),
    "INT-003": ("mqtt", "iot sensor"),
    "INT-004": ("john deere", "trimble", "isoxml connector"),
}

ROUTE_RE = re.compile(
    r"@(?:\w+\.)?(?:get|post|put|patch|delete|options|head)\(\s*[rf]?['\"]([^'\"]+)", re.I
)
SUBJECT_RE = re.compile(r"['\"]([a-zA-Z][a-zA-Z0-9_-]*(?:\.[a-zA-Z0-9_*>-]+){1,8})['\"]")
#: `CREATE|ALTER TABLE [IF [NOT] EXISTS] [ONLY] [schema.]name` — والكلمات المفتاحيّة
#: **لا تصلح أسماء جداول**.
#:
#: الصياغة السابقة جعلت `(?:\s+if\s+not\s+exists)?` اختياريّةً قابلة للتراجع: عند
#: `CREATE TABLE IF NOT EXISTS + DROP POLICY…` (تعليقٌ في هجرة) يفشل ما بعدها فيتراجع
#: المُطابِق إلى صفر تكرار **فيلتقط `IF` بوصفه اسم جدول**. وأنتج ذلك ١٢ مدخلاً كاذباً
#: في `capability_mapping.json` — أدلّةُ «قاعدة بيانات» مصدرها تعليقات ونصوص اختبارات،
#: تُرفَع منها `coverage_dimensions` وتنتقل إلى مصفوفة الأدلّة ثمّ إلى مصفوفة الإدارة.
#:
#: والحارس هنا **نظرة أمام** لا ترتيبٌ للبدائل: أيّاً كان مسار التراجع، الاسم الملتقَط
#: لا يجوز أن يكون كلمةً مفتاحيّة — فإن كان، أُعيدت المحاولة باستهلاكها. هذا هو الفرق
#: بين «لم أجد جدولاً» و«التقطتُ كلمةً وسمّيتها جدولاً».
#:
#: **والعطل نفسه عاد بمَعامِلٍ آخر:** بادئة المخطَّط `(?:[\w"]+\.)?` اختياريّة **قابلة
#: للتراجع** أيضاً. فعند `CREATE TABLE public . "<t>" (` يفشل الالتقاط بعد الاقتباس
#: (اسمٌ نائب لا يبدأ بحرف)، فيتراجع المُطابِق ويأخذ **`public`** — أي **المُؤهِّل
#: بوصفه مُؤهَّلاً**. وأنتج ذلك أربعة مداخل كاذبة ورفع `capabilities_multidimensional`
#: من ٤٨ إلى ٤٩: رقمٌ حوكميّ يتحرّك على كذبة.
#:
#: **والعلاج بنيويّ لا حظرَ كلمة:** لا ذكر لـ`public` هنا — فهي **اسم جدولٍ قانونيّ**
#: حين تَرِد غير مؤهَّلة — جدولاً اسمه `public` بلا مخطَّط قبله — وحظرُها بالاسم كان
#: سيُنتِج العمى المقابل: كاشفٌ يرفض حقيقةً ليتجنّب كذبة.
#: المرفوض هو **الموضع** لا الاسم: `\b(?!\s*\.)` يرفض التقاطَ اسمٍ تتبعه نقطة، لأنّ
#: ما قبل النقطة مخطَّطٌ لا جدول. و`\b` ليست زينة: بدونها يتراجع `[\w]*` إلى `publi`
#: فتمرّ النظرة على `c` — **مقيس، وكان أوّل مرشَّح خاطئاً لهذا السبب بالذات**.
#:
#: و`\s*\.\s*` تقبل المسافات حول النقطة: `public . t` قانونيّة، ومُحلِّل PostgreSQL
#: يفصل الرموز بالمسافات كغيرها.
#:
#: **والاقتباس داخل النظرة اللاحقة لا خارجها** — `(?!["]?\s*\.)` لا `(?!\s*\.)`. لأنّ
#: هذا المُصنِّف **يقرأ نثراً وشُذرات غير مكتملة** لا ملفّات SQL وحدها؛ فعند سطرٍ ينتهي
#: عند `ALTER TABLE "public" .` — بلا اسم جدولٍ بعده — تقع النقطة **خلف علامة اقتباس**،
#: فتمرّ النظرة العارية ويُلتقَط `public` مُؤهِّلاً بوصفه مُؤهَّلاً. نفس العطل، في
#: الشُّذرة الناقصة بدل الكاملة.
TABLE_RE = re.compile(
    r"\b(?:create|alter)\s+table\s+(?:(?:if\s+(?:not\s+)?exists|only)\s+)*"
    r"(?:[\w\"]+\s*\.\s*)?[\"]?(?!(?:if|not|exists|only)\b)([a-zA-Z_][\w]*)\b(?![\"]?\s*\.)",
    re.I,
)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_registry() -> list[dict]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data["capabilities"]


def _manifest_files() -> list[str]:
    """Paths listed in the SIGNED release manifest (``release/FILE_CHECKSUMS.sha256``),
    parsed from its ``<sha256>␠␠<relative-path>`` lines. This is the fail-closed
    offline allowlist — only signed files, never arbitrary untracked ones."""
    manifest = ROOT / "release" / "FILE_CHECKSUMS.sha256"
    if not manifest.exists():
        return []
    paths = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)  # "<sha256>  <path>"
        if len(parts) == 2 and parts[1]:
            paths.append(parts[1])
    return paths


def _tracked_files() -> list[str]:
    """git-tracked files only. Scanning the raw filesystem lets local, uncommitted
    artifacts (.claude/settings.local.json, frontend/test-results/*, editor caches)
    leak into the map — they exist on a developer machine but not on a clean CI
    checkout, making the output non-reproducible. Tracked files ARE the repository.

    Offline/ZIP fallback (fail-closed): a source ZIP extracted for audit has no ``.git``,
    so ``git ls-files`` fails. Rather than scan the raw filesystem (which would pull in
    arbitrary untracked files), fall back to the SIGNED release manifest and scan only the
    paths it lists — the manifest is the signed allowlist. If neither git nor the manifest
    is available, fail closed (raise) instead of scanning untracked files. In CI (always a
    git worktree) the git path is used, so committed outputs stay reproducible."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = [x for x in out.split("\0") if x]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass  # no git worktree (e.g. an extracted release ZIP) — try the signed manifest
    manifest_files = _manifest_files()
    if manifest_files:
        return manifest_files
    raise RuntimeError(
        "no git worktree and no signed release manifest (release/FILE_CHECKSUMS.sha256); "
        "refusing to scan the raw filesystem (fail-closed)"
    )


def iter_files() -> Iterable[Path]:
    for rel_str in _tracked_files():
        rel = Path(rel_str)
        p = ROOT / rel
        if p.suffix.lower() not in TEXT_SUFFIXES or not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        # Architecture/governance meta-tests validate the capability system itself and name
        # capability IDs in assertions (e.g. "INT-004"), which the token scanner would credit
        # as spurious tests/other_evidence hits — self-referential, not domain implementation.
        if len(rel.parts) >= 2 and rel.parts[0] == "tests" and rel.parts[1] == "architecture":
            continue
        # Capability metadata (policies, adjudications, release baselines) enumerates every
        # capability ID by construction; scanning it credits each capability against its own
        # registry entry — self-referential, not domain implementation evidence. (The generated/
        # subtree is already excluded below; this covers the hand-authored config beside it.)
        if len(rel.parts) >= 2 and rel.parts[0] == "docs" and rel.parts[1] == "capability-registry":
            continue
        # Generated inventories, release metadata and capability outputs are derived artifacts,
        # not independent implementation evidence. Scanning them creates self-referential
        # mapping → maturity → benchmark/release cycles and inflates routes/events from SBOMs.
        if "generated" in rel.parts or (rel.parts and rel.parts[0] == "release"):
            continue
        if ".generated." in p.name.lower():
            continue
        yield p


def classify(rel: str) -> str:
    n = rel.lower()
    name = Path(rel).name.lower()
    if n.startswith("migrations/") or "/migrations/" in n or n.endswith(".sql"):
        return "database"
    if (
        name.startswith("test_")
        or "/tests/" in f"/{n}"
        or n.endswith("_test.dart")
        or n.endswith(".spec.ts")
        or n.endswith(".test.ts")
    ):
        return "tests"
    if (
        n.startswith(("apps/web/", "web/", "frontend/"))
        or "/src/pages/" in n
        or "/src/components/" in n
    ):
        return "web"
    if n.startswith(("apps/mobile/", "mobile/")) or n.endswith(".dart"):
        return "mobile"
    if n.startswith(("services/", "apps/services/")):
        return "backend"
    if "workflow" in n or n.startswith(".github/"):
        return "governance"
    return "other"


def route_items(rel: str, text: str) -> list[str]:
    return [
        f"{m.group(1)} @ {rel}:{text.count(chr(10), 0, m.start()) + 1}"
        for m in ROUTE_RE.finditer(text)
    ]


def db_items(rel: str, text: str) -> list[str]:
    return [
        f"{m.group(1)} @ {rel}:{text.count(chr(10), 0, m.start()) + 1}"
        for m in TABLE_RE.finditer(text)
    ]


def event_items(rel: str, text: str) -> list[str]:
    out = []
    for m in SUBJECT_RE.finditer(text):
        value = m.group(1)
        if any(
            x in value.lower()
            for x in (
                "sahool",
                "field",
                "weather",
                "irrig",
                "decision",
                "task",
                "sensor",
                "crop",
                "soil",
                "imagery",
                "execution",
            )
        ):
            out.append(f"{value} @ {rel}:{text.count(chr(10), 0, m.start()) + 1}")
    return out


def score_blob(
    cid: str, cap: dict, rel: str, hay_path: str, hay: str, raw_text: str
) -> tuple[int, list[str]]:
    terms = list(ALIASES.get(cid, ()))
    title = cap.get("title", {}).get("en", "")
    if title:
        terms.append(title)
    hits = []
    score = 0
    for term in sorted(set(terms)):
        t = norm(term)
        if not t or len(t) < 3:
            continue
        if t in hay_path:
            score += 8
            hits.append(f"path:{term}")
        count = hay.count(t)
        if count:
            score += min(6, 2 + count)
            hits.append(f"content:{term}")
    # Direct capability ID references are authoritative static links.
    raw_lower = raw_text.lower()
    if cid.lower() in raw_lower or cid.lower().replace("-", "_") in raw_lower:
        score += 20
        hits.append("explicit_id")
    return score, hits


def build() -> dict:
    caps = load_registry()
    by_id = {c["id"]: c for c in caps}
    maps = {
        cid: {
            "capability_id": cid,
            "domain": c["domain"],
            "title": c["title"]["en"],
            "backend": [],
            "routes": [],
            "database": [],
            "events": [],
            "web": [],
            "mobile": [],
            "tests": [],
            "governance": [],
            "other_evidence": [],
            "ambiguous": [],
            "static_evidence_only": True,
            "runtime_verified": False,
            "production_certified": False,
        }
        for cid, c in by_id.items()
    }
    unmapped = []
    ambiguous = []
    inventory = Counter()
    files = list(iter_files())
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        kind = classify(rel)
        inventory[kind] += 1
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scored = []
        hay_path = norm(rel)
        hay = norm(text[:250_000])
        for cid, cap in by_id.items():
            score, hits = score_blob(cid, cap, rel, hay_path, hay, text)
            if score >= 8:
                scored.append((score, cid, hits))
        scored.sort(reverse=True)
        if not scored:
            if kind in {"backend", "database", "web", "mobile", "tests"}:
                unmapped.append({"path": rel, "kind": kind})
            continue
        top = scored[0][0]
        selected = [x for x in scored if x[0] >= max(8, top - 3)][:4]
        if len(selected) > 1:
            ambiguous.append(
                {
                    "path": rel,
                    "kind": kind,
                    "candidates": [
                        {"capability_id": cid, "score": score, "signals": hits}
                        for score, cid, hits in selected
                    ],
                }
            )
        for score, cid, hits in selected:
            rec = {"path": rel, "score": score, "signals": hits}
            target = maps[cid]
            if kind == "backend":
                target["backend"].append(rec)
            elif kind == "web":
                target["web"].append(rec)
            elif kind == "mobile":
                target["mobile"].append(rec)
            elif kind == "tests":
                target["tests"].append(rec)
            elif kind == "governance":
                target["governance"].append(rec)
            elif kind == "database":
                target["database"].append(rec)
            else:
                target["other_evidence"].append(rec)
            for r in route_items(rel, text):
                target["routes"].append({"value": r, "score": score})
            for d in db_items(rel, text):
                target["database"].append({"value": d, "score": score})
            for e in event_items(rel, text):
                target["events"].append({"value": e, "score": score})

    def dedup(items, key):
        best = {}
        for x in items:
            k = x.get(key) or x.get("path") or x.get("value")
            if k not in best or x.get("score", 0) > best[k].get("score", 0):
                best[k] = x
        return sorted(
            best.values(),
            key=lambda x: (-x.get("score", 0), x.get(key) or x.get("path") or x.get("value")),
        )

    mapped = 0
    fully = 0
    for rec in maps.values():
        for k in (
            "backend",
            "routes",
            "database",
            "events",
            "web",
            "mobile",
            "tests",
            "governance",
            "other_evidence",
        ):
            rec[k] = dedup(rec[k], "value")[:100]
        rec["evidence_counts"] = {
            k: len(rec[k])
            for k in (
                "backend",
                "routes",
                "database",
                "events",
                "web",
                "mobile",
                "tests",
                "governance",
                "other_evidence",
            )
        }
        # HONESTY INVARIANT (raw scanner): ``mapped`` is decided by the SPECIFIC
        # implementation dimensions ONLY. ``governance`` and ``other_evidence`` are
        # catch-all buckets — bare capability-ID mentions in narrative/self-reference
        # or generated/governance files — and MUST NEVER promote a capability on their
        # own; otherwise a stray ID mention would falsely map a pure scaffold. This
        # matches the authoritative management engine's specific-dimension rule and
        # makes raw-scanner ``mapped`` an honest LOWER BOUND (⊆ management ``mapped``).
        # The management engine additionally credits registry-declared on-disk evidence
        # the scanner cannot attribute, so it — not this raw artifact — is the sole
        # authoritative mapped/unmapped state (see ``authoritative`` below).
        rec["coverage_dimensions"] = sum(
            bool(rec[k])
            for k in ("backend", "routes", "database", "events", "web", "mobile", "tests")
        )
        rec["mapped"] = rec["coverage_dimensions"] > 0
        if rec["mapped"]:
            mapped += 1
        if rec["coverage_dimensions"] >= 4 and rec["tests"]:
            fully += 1
    return {
        "schema_version": "1.0.0",
        "generated_from": "repository_static_scan",
        "repository_root": ".",
        # This raw scanner artifact is NOT the authoritative mapped/unmapped state. Its
        # ``mapped`` is a specific-dimension LOWER BOUND (⊆ the management matrix). The
        # sole authority is the management engine, which additionally reconciles
        # registry-declared on-disk evidence the scanner cannot attribute. A downstream
        # consumer must read the management dashboard for the canonical state, never this.
        "authoritative": False,
        "authoritative_mapped_state_source": (
            "docs/capability-registry/generated/management/coverage_dashboard.json"
        ),
        "mapped_semantics": "scanner_specific_dimension_evidence_only__lower_bound_of_management",
        "constraints": {
            "runtime_claims": False,
            "production_certification": False,
            "automatic_maturity_upgrade": False,
        },
        "summary": {
            "capabilities_total": len(maps),
            "capabilities_mapped": mapped,
            "capabilities_unmapped": len(maps) - mapped,
            "capabilities_multidimensional": fully,
            "files_scanned": len(files),
            "files_by_kind": dict(sorted(inventory.items())),
            "unmapped_artifacts": len(unmapped),
            "ambiguous_artifacts": len(ambiguous),
        },
        "capabilities": [maps[k] for k in sorted(maps)],
        "unmapped_artifacts": sorted(unmapped, key=lambda x: x["path"]),
        "ambiguous_artifacts": sorted(ambiguous, key=lambda x: x["path"]),
    }


def write_outputs(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "capability_mapping.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (OUT / "capability_mapping.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "capability_id",
            "domain",
            "title",
            "mapped",
            "coverage_dimensions",
            "backend",
            "routes",
            "database",
            "events",
            "web",
            "mobile",
            "tests",
            "governance",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in data["capabilities"]:
            w.writerow(
                {
                    "capability_id": c["capability_id"],
                    "domain": c["domain"],
                    "title": c["title"],
                    "mapped": c["mapped"],
                    "coverage_dimensions": c["coverage_dimensions"],
                    **{k: len(c[k]) for k in fields[5:]},
                }
            )
    (OUT / "unmapped_artifacts.json").write_text(
        json.dumps(data["unmapped_artifacts"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT / "ambiguous_artifacts.json").write_text(
        json.dumps(data["ambiguous_artifacts"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    s = data["summary"]
    lines = [
        "# Capability Mapping — Raw Scanner Candidates (NOT authoritative)",
        "",
        "> Raw static repository scan only. `mapped` here means the scanner found specific",
        "> implementation-dimension evidence (backend/routes/db/events/web/mobile/tests) — an honest",
        "> LOWER BOUND. The AUTHORITATIVE mapped/unmapped state is the management matrix",
        "> (`docs/capability-registry/generated/management/coverage_dashboard.json`), which also",
        "> credits registry-declared on-disk evidence this scanner cannot attribute. `governance` and",
        "> `other_evidence` are reported but never promote a capability. This report does not assert",
        "> runtime verification or production certification.",
        "",
        f"- Capabilities: **{s['capabilities_total']}**",
        f"- Mapped: **{s['capabilities_mapped']}**",
        f"- Unmapped: **{s['capabilities_unmapped']}**",
        f"- Multi-dimensional mappings: **{s['capabilities_multidimensional']}**",
        f"- Files scanned: **{s['files_scanned']}**",
        f"- Ambiguous artifacts queued: **{s['ambiguous_artifacts']}**",
        f"- Unmapped artifacts queued: **{s['unmapped_artifacts']}**",
        "",
        "## Capability coverage",
        "",
        "| ID | Domain | Backend | Routes | DB | Events | Web | Mobile | Tests | Dimensions |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in data["capabilities"]:
        lines.append(
            f"| {c['capability_id']} | {c['domain']} | {len(c['backend'])} | {len(c['routes'])} | {len(c['database'])} | {len(c['events'])} | {len(c['web'])} | {len(c['mobile'])} | {len(c['tests'])} | {c['coverage_dimensions']} |"
        )
    (OUT / "CAPABILITY_MAPPING_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {}
    for name in (
        "capability_mapping.json",
        "capability_mapping.csv",
        "unmapped_artifacts.json",
        "ambiguous_artifacts.json",
        "CAPABILITY_MAPPING_REPORT.md",
    ):
        manifest[name] = hashlib.sha256((OUT / name).read_bytes()).hexdigest()
    (OUT / "mapping_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_outputs(data: dict) -> bool:
    target = OUT / "capability_mapping.json"
    if not target.exists():
        return False
    committed = json.loads(target.read_text(encoding="utf-8"))
    if committed == data:
        return True
    # Emit a concise, targeted diff so drift is diagnosable in CI rather than opaque.
    if committed.get("summary") != data.get("summary"):
        print(
            f"summary drift: committed={committed.get('summary')} fresh={data.get('summary')}",
            file=sys.stderr,
        )
    for field in ("unmapped_artifacts", "ambiguous_artifacts"):
        if committed.get(field) != data.get(field):
            ca = {x["path"] for x in committed.get(field, [])}
            da = {x["path"] for x in data.get(field, [])}
            print(
                f"{field} drift: only-committed={sorted(ca - da)[:5]} only-fresh={sorted(da - ca)[:5]}",
                file=sys.stderr,
            )
    return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--generate", action="store_true")
    p.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    if not REGISTRY.exists():
        print(
            "canonical capability registry missing; run capability_registry_v1.py --generate",
            file=sys.stderr,
        )
        return 2
    data = build()
    if a.check:
        if not check_outputs(data):
            print(
                "capability mapping drift; run capability_mapping_engine.py --generate",
                file=sys.stderr,
            )
            return 1
    else:
        write_outputs(data)
    s = data["summary"]
    print(
        f"capability_mapping_ok mapped={s['capabilities_mapped']}/{s['capabilities_total']} files={s['files_scanned']} ambiguous={s['ambiguous_artifacts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
