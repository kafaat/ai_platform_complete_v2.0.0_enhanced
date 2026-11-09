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
import ast
import bisect
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from collections.abc import Iterable
from functools import cache
from pathlib import Path, PurePosixPath
from typing import NamedTuple

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
    # Delivery/package evidence is not repository implementation evidence.
    "_delivery",
    # Agent knowledge base: prose memory, not implementation evidence. It is not in
    # the release bundle and is rewritten every session, so scanning it both injects
    # spurious keyword hits (e.g. "IF" in narrative text) and makes the map churn —
    # line-number shifts flip which equal-score hit wins, drifting CI vs local.
    "sahool-brain",
}

# Meta-governance witnesses: files whose PURPOSE is documenting/adjudicating the capability
# system itself — mutation/test registries, generated governance inventories, and catalogue
# artifacts that quote capability IDs and event tokens by construction. Measured on PR #850:
# one mutation description in the mutation registry re-attributed ~40 event signals between
# two capabilities. A witness must not affect what it witnesses.
#
# Denied by NAME, never by subtree: hand-authored architecture contracts (ownership, boundary,
# schema, wiring), topology inventories and operational runbooks in the same directories are
# legitimate evidence and stay discoverable — a subtree ban traded contamination for
# undercounting (5017 → 4929 scanned files) and was rejected in review.
META_GOVERNANCE_FILES = {
    "docs/architecture/guard_mutation_registry.json",
    "docs/architecture/capability_core_consumption_registry.json",
    "docs/architecture/nats_subject_ownership_contract.json",
    "docs/architecture/source_text_assertion_inventory.json",
    "docs/runbooks/GUARD_CATALOGUE.md",
    "tests_v9/test_live_gap_closure_runbook_contract.py",
    "tests_v9/test_nats_subject_ownership_contract.py",
    # WITNESS-EXCLUDED-IN-ONE-CENSUS-ONLY-01 — **مقيسٌ على #1012:** شاهدُ حارس
    # «لا تقارير فقط» يذكر مسارات المستودع بحكم موضوعه، فحالةٌ تُسمّي ملفَّ إعداد
    # أدخلت كلمةَ نطاق فربطه الماسحُ بـGIS-003 ورفعت عدّةَ شواهدها 38 → 39 —
    # إشارةُ قدرةٍ كاذبة، ثمّ حجبت بوّابةُ الأثر إعلاناً صادقاً حتّى أُضيفت القدرةُ
    # المزعومة إلى السطر. وهو **صنفُ #857 بعينه** (SAT-007 بكلمة «change»).
    # و`capability_linker` كان يستبعده سلفاً (`META_GOVERNANCE_PREFIXES`) — فالزوجُ
    # كان محروساً نصفَه: جردان لشاهدٍ واحد، أحدُهما يُعفيه والآخر يقرؤه دليلاً.
    "tests_v9/test_no_report_only_change_guard.py",
    # Governance plan and its verifier are not implementation evidence. Scanning
    # their prose and negative fixtures would self-certify DEC/IRR capabilities;
    # the actual domain code remains discoverable through normal source paths.
    # Exact-file scope avoids a broad docs/strategy or scripts/ci subtree ban.
    "config/proof/data_decision_outcome_v1.json",
    "docs/strategy/DATA_DECISION_OUTCOME_PROOF_20261107.md",
    "scripts/ci/data_decision_outcome_proof_gate.py",
    "tests_v9/test_data_decision_outcome_manifest_binding.py",
    "tests_v9/test_data_decision_outcome_proof_gate.py",
    # Read-only Railway backup inventory and negative tests are security/evidence
    # witnesses, not proof of irrigation, database migration or field outcomes.
    "scripts/ci/railway_staging_backup_inventory.py",
    "tests_v9/test_railway_staging_backup_inventory.py",
    # The R1/R2/R3 regression test names capability IDs, domain words and reviewed case
    # paths by construction (positive and negative controls); scanning it would make the
    # witness of the scorer evidence for the capabilities it controls for.
    "tests_v9/test_capability_mapping_dependency_evidence.py",
}
# Extension point for whole witness classes (e.g. a future registries/ subdir). Empty today:
# every measured witness is an individual file, and breadth must be argued per entry.
META_GOVERNANCE_PREFIXES: tuple[str, ...] = ()

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
#:
#: ── عقد المؤقّت والدائم ──────────────────────────────────────────────────────
#:
#: بُعد `database` يقيس **العلاقات الدائمة**. وحتّى هذه الشريحة كان النمط يطلب `TABLE`
#: **مباشرةً** بعد `CREATE`، فيسقط كلّ ما بينهما مُعدِّل — المؤقّت والدائم معاً. فبدا
#: استبعادُ `TEMP` صحيحاً وهو **أثرٌ جانبيّ لا عقد**، وسقط معه `UNLOGGED` **وهو دائم**:
#: صيغةُ الإنشاء بمُعدِّل `UNLOGGED` كانت تُعطي صفر التقاط — مقيس على `68cc8cfb7`.
#: (‏والمثال الحرفيّ في `test_an_unlogged_table_is_a_permanent_relation` لا هنا: نثرٌ
#: على شكل DDL في هذا الملفّ يُقرأ دليلَ «قاعدة بيانات» عن نفسه — وقد وقع ذلك مرّةً
#: بـ`public` فأنتج أربعة مداخل كاذبة. الكاشف مُحقّ؛ النثر هو ما يُعاد صوغه.)
#:
#: فصار الاستبعاد **منصوصاً**: `_NOT_TEMPORARY` نظرةٌ نافية تُبطِل المطابقة عند
#: `TEMP`/`TEMPORARY` (وببادئتَي `GLOBAL`/`LOCAL`)، و`UNLOGGED` وحدها تُقبَل مُعدِّلاً.
#: والفرق عمليّ لا شكليّ: يوم يُضاف مُعدِّلٌ ثالث، يبقى منعُ المؤقّت قائماً بذاته بدل
#: أن يذوب في اتّساع النمط.
#:
#: **ولماذا `UNLOGGED` دائم:** يفقد **بياناته** عند انهيارٍ غير نظيف، لكنّ **تعريفه**
#: في الكتالوج — مالكٌ وقيودٌ وفهارس وهجرةٌ تُنشئه — ويبقى بعد إعادة التشغيل جدولاً
#: فارغاً لا معدوماً. أمّا المؤقّت فيعيش في `pg_temp_N` ويختفي بانتهاء الجلسة.
#:
#: ── حدّ النطاق: ما لا يُدَّعى ────────────────────────────────────────────────
#:
#: هذا ماسحُ **الجداول المحلّيّة الدائمة** المُعلَنة بـ`CREATE TABLE` أو `ALTER TABLE`
#: — لا ماسحُ علاقات PostgreSQL كلّها. فخارج مداه: `CREATE FOREIGN TABLE` · المشاهد
#: المُجسَّدة · `SELECT … INTO` · المتتاليات. وخلوّ بُعد `database` من إحداها **ليس
#: حكماً بغيابها** بل بأنّها ليست من الصنف المسؤول عنه. الحدّ مُثبَّت بـ
#: `test_the_declared_out_of_scope_forms_are_silent`، فتوسيعُه يقتضي تحديث الاثنين معاً.

#: `TEMP`/`TEMPORARY` — وحدها أو ببادئة `GLOBAL`/`LOCAL`. مرفوضة **بالعقد** لا بالمصادفة.
_NOT_TEMPORARY = r"(?!(?:(?:global|local)\s+)?temp(?:orary)?\b)"

TABLE_RE = re.compile(
    r"\b(?:create\s+" + _NOT_TEMPORARY + r"(?:unlogged\s+)?|alter\s+)table\s+"
    r"(?:(?:if\s+(?:not\s+)?exists|only)\s+)*"
    r"(?:[\w\"]+\s*\.\s*)?[\"]?(?!(?:if|not|exists|only)\b)([a-zA-Z_][\w]*)\b(?![\"]?\s*\.)",
    re.I,
)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ── Evidence extraction and weighting (test-impact recall review, 2026-11-09) ─────────
#
# R1 — one normalized term, one weight. A title often repeats an alias in another
# spelling (title "GDD", alias "gdd"). Both normalize to ``gdd`` and both were scored,
# so a single word counted twice and crossed the 8-point threshold on its own
# (services/weather-service/tests/test_missing_temperature_is_not_zero.py: signals
# ``content:GDD`` + ``content:gdd`` = 12). Terms are grouped by ``norm()`` before scoring;
# the merged spellings stay visible as a ``dedup:`` signal so the change is explainable.
#
# R2 — contextual matching for ambiguous words. "inventory" names farm stock (FM-007)
# next to suppliers, reorder levels and agro-inputs; alone it is usually a *software*
# inventory (route/component/diagnostic inventories), which mapped
# scripts/diagnostics/build_main_inventory.py to FM-007. Such a term counts — in the path
# or the content — only when one of its context words occurs in the same file's
# functional text. Default-deny for the ambiguous reading, not a deny-list of technical
# phrases, which could never be complete.
CONTEXTUAL_TERMS: dict[str, tuple[str, ...]] = {
    "inventory": (
        "stock",
        "quantity",
        "supplier",
        "fertilizer",
        "fertiliser",
        "pesticide",
        "warehouse",
        "procurement",
        "purchase",
        "reorder",
        "agrochemical",
        "unit cost",
    ),
}


def _has_context(hay: str, context: tuple[str, ...]) -> bool:
    padded = f" {hay} "
    return any(f" {norm(word)} " in padded for word in context)


@cache
def _scoring_terms(cid: str, title: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """``(normalized term, original spellings)`` — each normalized term exactly once."""
    spellings: dict[str, set[str]] = {}
    for term in (*ALIASES.get(cid, ()), *((title,) if title else ())):
        normalized = norm(term)
        if not normalized or len(normalized) < 3:
            continue
        spellings.setdefault(normalized, set()).add(term)
    return tuple((t, tuple(sorted(s))) for t, s in sorted(spellings.items()))


# R2 — functional text. Capability IDs and domain words inside comments and (for test
# files) fixture data / example payloads are not functional evidence:
# tests_v9/test_main_inventory_generator.py was credited SOIL-001 (+20, explicit_id) for
# a fabricated ``"capability_id": "SOIL-001"`` fixture row, and tests_v9/service_module.py
# was credited SEC-004 for comments recalling an MFA import-cache incident. Python is
# read through ``ast``/``tokenize``; comments are dropped, and in test files every string
# literal inside a dict/list/tuple/set display is dropped (fixture rows, payloads,
# parametrize tables). Docstrings stay: they declare what a module or test is *for*
# (measured: dropping them also removed the reviewed-correct SEC-001 label of
# tests_v9/test_rs_anomaly_pg_isolation_integration.py). Identifiers, calls and other
# literals stay. Unparsable Python and non-Python files keep the legacy raw reading.
_DISPLAYS = (ast.Dict, ast.List, ast.Tuple, ast.Set)


def _span(node: ast.AST) -> tuple[tuple[int, int], tuple[int, int]]:
    return (
        (node.lineno, node.col_offset),
        (node.end_lineno or node.lineno, node.end_col_offset or node.col_offset),
    )


def _non_functional_string_spans(
    tree: ast.AST, *, fixture_data: bool
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for node in ast.walk(tree):
        if fixture_data and isinstance(node, _DISPLAYS):
            for inner in ast.walk(node):
                if isinstance(inner, ast.JoinedStr) or (
                    isinstance(inner, ast.Constant) and isinstance(inner.value, str)
                ):
                    spans.append(_span(inner))
    merged: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for start, end in sorted(set(spans)):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def python_functional_text(text: str, *, fixture_data: bool) -> str | None:
    """Python source without comments and (optionally) test fixture literals.

    ``None`` when the source does not parse — the caller then keeps the raw text.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    spans = _non_functional_string_spans(tree, fixture_data=fixture_data)
    starts = [start for start, _ in spans]
    kept: list[str] = []
    try:
        for tok_type, tok_string, tok_start, tok_end in _version_stable_tokens(text):
            if tok_type == tokenize.COMMENT:
                continue
            if tok_type == tokenize.STRING and spans:
                index = bisect.bisect_right(starts, tok_start) - 1
                if index >= 0 and spans[index][0] <= tok_start and tok_end <= spans[index][1]:
                    continue
            kept.append(tok_string)
    except (tokenize.TokenError, SyntaxError):
        return None
    return " ".join(kept)


# Python 3.12 (PEP 701) tokenizes an f-string as FSTRING_START … FSTRING_END with the
# interpolated expressions as separate tokens; 3.14 adds the same for t-strings. Earlier
# versions emit one STRING token. The functional text feeds generated artifacts that CI
# (3.12) and local runs (3.11) must reproduce byte-for-byte, so an f-string is folded
# back into a single STRING token spanning its exact source text on every version.
_STRING_GROUP_STARTS = {
    getattr(tokenize, name)
    for name in ("FSTRING_START", "TSTRING_START")
    if hasattr(tokenize, name)
}
_STRING_GROUP_ENDS = {
    getattr(tokenize, name) for name in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, name)
}


def _version_stable_tokens(text: str):
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def offset(position: tuple[int, int]) -> int:
        row, col = position
        return offsets[row - 1] + col if row - 1 < len(offsets) else len(text)

    depth = 0
    group_start: tuple[int, int] | None = None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in _STRING_GROUP_STARTS:
            if depth == 0:
                group_start = tok.start
            depth += 1
            continue
        if depth:
            if tok.type in _STRING_GROUP_ENDS:
                depth -= 1
                if depth == 0 and group_start is not None:
                    yield (
                        tokenize.STRING,
                        text[offset(group_start) : offset(tok.end)],
                        group_start,
                        tok.end,
                    )
                    group_start = None
            continue
        yield tok.type, tok.string, tok.start, tok.end


class ScoringText(NamedTuple):
    """What a file is scored on: normalized path, normalized functional text, ID text.

    A NamedTuple, not a dataclass: tests load this script by path without registering
    it in ``sys.modules``, which the dataclass decorator requires."""

    hay_path: str
    hay: str
    id_text: str
    reading: str


def scoring_text(rel: str, text: str, kind: str) -> ScoringText:
    functional: str | None = None
    reading = "raw"
    if rel.endswith(".py"):
        functional = python_functional_text(text, fixture_data=kind == "tests")
        if functional is not None:
            reading = "python_functional"
    body = text if functional is None else functional
    return ScoringText(norm(rel), norm(body[:250_000]), body, reading)


# ── R3: proven test → source dependencies (existing contract, no second selector) ──────
#
# Lexical similarity is not dependency evidence. A test that imports a source module,
# reads a source file by path (``ast.parse(SOURCE.read_text())``) or loads it through a
# shared loader (``load_service_main(dir)``, ``spec_from_file_location``) depends on it,
# whatever words either file contains. These edges are emitted in
# ``capability_mapping.json`` → ``test_dependencies`` and folded by the single impact
# engine (``pr_capability_impact_gate.build_snapshot``): a change to the source selects
# the test with a ``dependency:<kind>:<source>`` reason (path-level, the test's own
# capability label is not rewritten) — no second selector, no new registry, no change to
# escalation or floor rules. They are not capability evidence and never count towards
# ``mapped``/``coverage_dimensions``.
#
# Dynamic relations that cannot be resolved statically are recorded, never guessed:
# ``unresolved``. A test with no capability of its own only inherits its sources'
# capabilities when its relation set is ``bounded`` (every relation resolved, no
# tree-wide scan, no shared test harness, no repository data-file read) — otherwise it
# stays in the floor. Edges are direct only; transitive imports are not followed.
_LOADER_CALLS = {
    "spec_from_file_location",
    "run_path",
    "SourceFileLoader",
    "load_service_main",
}
# Loader helpers that take a *service directory* and import ``<dir>/main.py``.
_DIRECTORY_LOADERS = {"load_service_main": "main.py"}
_TREE_WIDE_CALLS = {"glob", "rglob", "iglob", "walk", "iterdir", "listdir", "scandir"}
_TREE_WIDE_MODULES = {"subprocess"}
_PATH_WRAPPERS = {"str", "Path", "PurePath", "fspath", "resolve", "absolute"}
_PATH_LIKE = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)*/?$")


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _path_parts(node: ast.AST) -> list[str] | None:
    """String parts of a path expression: ``"a/b"``, ``X / "a" / "b"``, ``join(X, "a")``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _path_parts(node.left) or []
        right = _path_parts(node.right)
        if right is None:
            return None
        return left + right
    if isinstance(node, ast.Call) and _call_name(node) == "join" and node.args:
        parts: list[str] = []
        for arg in node.args:
            sub = _path_parts(arg)
            if sub:
                parts.extend(sub)
        return parts or None
    if isinstance(node, ast.Call) and _call_name(node) in {"str", "Path", "PurePath", "fspath"}:
        if len(node.args) == 1:
            return _path_parts(node.args[0])
    return None


class _RepoIndex(NamedTuple):
    files: frozenset[str]
    dirs: frozenset[str]
    module_names: frozenset[str]


def repo_index(tracked: Iterable[str]) -> _RepoIndex:
    files = frozenset(tracked)
    dirs: set[str] = set()
    names: set[str] = set()
    for path in files:
        pure = PurePosixPath(path)
        for parent in pure.parents:
            if str(parent) != ".":
                dirs.add(parent.as_posix())
        if pure.suffix == ".py":
            names.add(pure.parent.name if pure.name == "__init__.py" else pure.stem)
    return _RepoIndex(files, frozenset(dirs), frozenset(names))


def _resolve_path(parts: list[str], test_dir: PurePosixPath, index: _RepoIndex) -> str | None:
    joined = "/".join(p.strip("/") for p in parts if p and p.strip("/") not in {"", "."})
    if not joined or not _PATH_LIKE.match(joined) or ".." in joined.split("/"):
        return None
    candidates = [PurePosixPath(joined)]
    candidates += [anc / joined for anc in (test_dir, *test_dir.parents) if str(anc) != "."]
    for candidate in candidates:
        value = candidate.as_posix()
        if value in index.files or value in index.dirs:
            return value
    return None


def _module_file(root: PurePosixPath | None, dotted: str, index: _RepoIndex) -> str | None:
    base = PurePosixPath(*dotted.split(".")) if root is None else root.joinpath(*dotted.split("."))
    for candidate in (f"{base.as_posix()}.py", f"{base.as_posix()}/__init__.py"):
        if candidate in index.files:
            return candidate
    return None


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    current = parents.get(node)
    while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
        current = parents.get(current)
    return current


def _is_test_support(path: str) -> bool:
    """A non-test module inside a test tree: a shared harness whose own reads are not
    analysed here (e.g. tests_v9/service_module.py mutates sys.path for every test)."""
    pure = PurePosixPath(path)
    in_test_tree = any(part in {"tests", "tests_v9", "test"} for part in pure.parts[:-1])
    return in_test_tree and not is_test_module(path)


def _standalone_path_literal(value: str) -> bool:
    """A lone string is a path candidate only if it looks like one (``a/b`` or ``x.py``)."""
    return "/" in value or bool(re.search(r"\.[A-Za-z0-9]{1,5}$", value))


def extract_test_dependencies(rel: str, text: str, index: _RepoIndex) -> dict | None:
    """Static test → repository-source relations of one Python test file.

    Edge kinds: ``import`` (module import resolved to a tracked file), ``source_read``
    (a tracked ``.py`` path named in the test, e.g. ``ast.parse(SOURCE.read_text())``),
    ``loader`` (a path or service directory handed to a loader: ``spec_from_file_location``,
    ``run_path``, ``load_service_main`` → ``<dir>/main.py``, or a local helper whose every
    call passes a resolvable path). ``None`` for unparsable files or files without any
    relation — no claim either way.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    test_dir = PurePosixPath(rel).parent
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    edges: dict[tuple[str, str], int] = {}
    unresolved: list[dict] = []
    unbounded: set[str] = set()
    path_names: dict[str, str] = {}
    referenced_dirs: dict[str, int] = {}
    used_dirs: set[str] = set()

    def add_edge(source: str, kind: str, line: int) -> None:
        if source != rel and ((source, kind) not in edges or line < edges[(source, kind)]):
            edges[(source, kind)] = line

    def resolve_expr(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name) and node.id in path_names:
            return path_names[node.id]
        if isinstance(node, ast.Call) and _call_name(node) in {"str", "Path", "fspath"}:
            if len(node.args) == 1:
                return resolve_expr(node.args[0])
        parts = _path_parts(node)
        if not parts:
            return None
        if isinstance(node, ast.Constant) and not _standalone_path_literal(node.value):
            return None
        return _resolve_path(parts, test_dir, index)

    # 1. Path expressions naming tracked paths (plain literals and maximal ``/`` chains).
    for node in ast.walk(tree):
        holder = parents.get(node)
        if isinstance(node, ast.Constant):
            if isinstance(holder, ast.BinOp) or not isinstance(node.value, str):
                continue
        elif isinstance(node, ast.BinOp):
            if isinstance(holder, ast.BinOp) or not isinstance(node.op, ast.Div):
                continue
        elif not (isinstance(node, ast.Call) and _call_name(node) == "join"):
            continue
        resolved = resolve_expr(node)
        if resolved is None:
            continue
        while (isinstance(holder, ast.Call) and _call_name(holder) in _PATH_WRAPPERS) or (
            isinstance(holder, ast.Attribute) and holder.attr in _PATH_WRAPPERS
        ):
            holder = parents.get(holder)
        if isinstance(holder, ast.Assign):
            for target in holder.targets:
                if isinstance(target, ast.Name):
                    path_names[target.id] = resolved
        if resolved in index.dirs:
            referenced_dirs.setdefault(resolved, node.lineno)
        elif resolved.endswith(".py"):
            add_edge(resolved, "source_read", node.lineno)
        else:
            unbounded.add("reads_repository_data_file")

    # 2. Loader calls: resolve the path argument, or record the relation as unresolved.
    pending: list[tuple[ast.Call, ast.AST | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in _TREE_WIDE_CALLS:
            unbounded.add("tree_wide_scan")
        if name not in _LOADER_CALLS:
            continue
        resolved_any = False
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            target = resolve_expr(arg)
            if target in index.dirs and name in _DIRECTORY_LOADERS:
                entry = f"{target}/{_DIRECTORY_LOADERS[name]}"
                if entry in index.files:
                    add_edge(entry, "loader", node.lineno)
                    used_dirs.add(target)
                    resolved_any = True
            elif target and target in index.files and target.endswith(".py"):
                add_edge(target, "loader", node.lineno)
                resolved_any = True
        if not resolved_any:
            pending.append((node, _enclosing_function(node, parents)))

    # A loader inside a local helper (``def _load(rel_path, name): spec_from_file_location(
    # name, ROOT / rel_path)``) is resolved when *every* call of that helper in this file
    # passes a resolvable repository path; the helper's targets become ``loader`` edges.
    calls_by_name: dict[str, list[ast.Call]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls_by_name.setdefault(node.func.id, []).append(node)
    for call, function in pending:
        targets: list[tuple[str, int]] = []
        helper_calls = calls_by_name.get(function.name, []) if function is not None else []
        params = (
            {
                a.arg
                for a in (
                    *function.args.posonlyargs,
                    *function.args.args,
                    *function.args.kwonlyargs,
                )
            }
            if function is not None
            else set()
        )
        uses_param = any(
            isinstance(inner, ast.Name) and inner.id in params
            for arg in [*call.args, *(kw.value for kw in call.keywords)]
            for inner in ast.walk(arg)
        )
        if uses_param and helper_calls:
            for helper_call in helper_calls:
                found = [
                    t
                    for arg in [*helper_call.args, *(kw.value for kw in helper_call.keywords)]
                    if (t := resolve_expr(arg)) and t in index.files and t.endswith(".py")
                ]
                if not found:
                    targets = []
                    break
                targets += [(t, helper_call.lineno) for t in found]
        if targets:
            for target, line in targets:
                add_edge(target, "loader", line)
        else:
            unresolved.append({"line": call.lineno, "call": _call_name(call)})

    # 3. Imports (and literal ``import_module``), resolved against directories the test
    #    names, its own directory and ancestors (the sys.path conventions used here), then
    #    the repository root. A non-literal ``import_module`` is an unresolved relation.
    import_roots = [PurePosixPath(d) for d in referenced_dirs]
    roots = [*import_roots, test_dir, *[p for p in test_dir.parents if str(p) != "."], None]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _TREE_WIDE_MODULES:
            unbounded.add("subprocess")
        modules: list[tuple[str, list[str], int]] = []
        if isinstance(node, ast.Import):
            modules = [(alias.name, [], node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level:
            base = test_dir
            for _ in range(node.level - 1):
                base = base.parent
            dotted = node.module or ""
            for sub in (alias.name for alias in node.names if alias.name != "*"):
                sub_found = _module_file(base, f"{dotted}.{sub}" if dotted else sub, index)
                if sub_found:
                    add_edge(sub_found, "import", node.lineno)
            found = _module_file(base, dotted, index) if dotted else None
            if found:
                add_edge(found, "import", node.lineno)
            continue
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names if alias.name != "*"]
            modules = [(node.module or "", names, node.lineno)]
        elif isinstance(node, ast.Call) and _call_name(node) == "import_module" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                modules = [(first.value, [], node.lineno)]
            else:
                unresolved.append({"line": node.lineno, "call": "import_module"})
        for dotted, names, line in modules:
            if not dotted or dotted.startswith("."):
                continue
            found = None
            for root in roots:
                found = _module_file(root, dotted, index)
                if found:
                    if root is not None:
                        used_dirs.add(root.as_posix())
                    for sub in names:
                        sub_found = _module_file(root, f"{dotted}.{sub}", index)
                        if sub_found:
                            add_edge(sub_found, "import", line)
                    break
            if found:
                add_edge(found, "import", line)
                if _is_test_support(found):
                    unbounded.add("shared_test_helper")
                continue
            top = dotted.split(".")[0]
            if top in index.module_names and top not in sys.stdlib_module_names:
                unresolved.append({"line": line, "import": dotted})

    if any(directory not in used_dirs for directory in referenced_dirs):
        unbounded.add("directory_reference")
    if unresolved:
        unbounded.add("unresolved_dynamic_relation")
    if not edges and not unresolved:
        return None
    return {
        "test": rel,
        "bounded": not unbounded,
        "unbounded_reasons": sorted(unbounded),
        "edges": [
            {"source": source, "kind": kind, "line": line}
            for (source, kind), line in sorted(edges.items())
        ],
        "unresolved": sorted(unresolved, key=lambda item: (item["line"], json.dumps(item))),
    }


def is_test_module(rel: str) -> bool:
    name = PurePosixPath(rel).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


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
        # Named meta-governance witnesses only — see META_GOVERNANCE_FILES for the rationale
        # and the review that rejected the wider subtree ban.
        rel_posix = rel.as_posix()
        if rel_posix in META_GOVERNANCE_FILES or rel_posix.startswith(META_GOVERNANCE_PREFIXES):
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
    """Score one file against one capability.

    ``hay`` / ``raw_text`` are the file's *functional* text (see ``scoring_text``); each
    normalized term is weighted once (R1) and contextual terms need their context (R2).
    """
    hits = []
    score = 0
    terms = _scoring_terms(cid, cap.get("title", {}).get("en", ""))
    # The 8-point threshold asks for corroboration: two distinct terms, a path hit or an
    # explicit ID — one term's content weight saturates at 6. A capability whose whole
    # vocabulary is ONE normalized term (NDMI, NDVI, "scouting") can only be corroborated
    # by repetition, so that term saturates at the threshold instead — reached at six
    # occurrences. Before R1 those capabilities bound at two occurrences only because the
    # title repeated the alias and the same word was scored twice.
    saturation = 8 if len(terms) == 1 else 6
    for t, spellings in terms:
        context = CONTEXTUAL_TERMS.get(t)
        if context and not _has_context(hay, context):
            continue
        label = spellings[0]
        hit = False
        if t in hay_path:
            score += 8
            hits.append(f"path:{label}")
            hit = True
        count = hay.count(t)
        if count:
            score += min(saturation, 2 + count)
            hits.append(f"content:{label}")
            hit = True
        if hit and len(spellings) > 1:
            hits.append("dedup:" + "=".join(spellings))
    # Direct capability ID references are authoritative static links — when they occur in
    # functional text, not in a comment or a test fixture row.
    raw_lower = raw_text.lower()
    if cid.lower() in raw_lower or cid.lower().replace("-", "_") in raw_lower:
        score += 20
        hits.append("explicit_id")
    return score, hits


EVIDENCE_DIMENSIONS = (
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


def cap_evidence_dimensions(rec: dict, dedup) -> None:
    """سقف كلّ بُعدٍ مئة، والقصّ **مُعلَنٌ لا صامت**.

    قِيس (CAPABILITY-EVIDENCE-LISTS-TRUNCATE-SILENTLY-01): إضافة ملفَّي اختبار
    أخرجت شاهدَ اختبارٍ قائماً من مصفوفة SAT-003 بلا أثر — وبعد الإعلان ظهر أنّ
    SEC-001.database كان يُسقط 743 شاهداً صامتاً. الترتيب حتميّ (score ثم المسار،
    من dedup) فالباقي مستقرّ، وevidence_truncated يسمّي عدد المحذوف لكلّ بُعدٍ
    قُصّ. السقف نفسه لا يُرفَع هنا (قرار baseline مستقلّ)."""
    truncated: dict[str, int] = {}
    for k in EVIDENCE_DIMENSIONS:
        full = dedup(rec[k], "value")
        rec[k] = full[:100]
        if len(full) > 100:
            truncated[k] = len(full) - 100
    if truncated:
        rec["evidence_truncated"] = truncated


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
    readings = Counter()
    test_dependencies: list[dict] = []
    index = repo_index(_tracked_files())
    files = list(iter_files())
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        kind = classify(rel)
        inventory[kind] += 1
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if is_test_module(rel):
            relations = extract_test_dependencies(rel, text, index)
            if relations is not None:
                test_dependencies.append(relations)
        scored = []
        reading = scoring_text(rel, text, kind)
        readings[reading.reading] += 1
        for cid, cap in by_id.items():
            score, hits = score_blob(cid, cap, rel, reading.hay_path, reading.hay, reading.id_text)
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
        cap_evidence_dimensions(rec, dedup)
        rec["evidence_counts"] = {k: len(rec[k]) for k in EVIDENCE_DIMENSIONS}
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
            "files_by_reading": dict(sorted(readings.items())),
            "test_dependency_files": len(test_dependencies),
            "test_dependency_edges": sum(len(t["edges"]) for t in test_dependencies),
            "test_dependency_bounded_files": sum(t["bounded"] for t in test_dependencies),
            "test_dependency_unresolved_relations": sum(
                len(t["unresolved"]) for t in test_dependencies
            ),
        },
        "capabilities": [maps[k] for k in sorted(maps)],
        "unmapped_artifacts": sorted(unmapped, key=lambda x: x["path"]),
        "ambiguous_artifacts": sorted(ambiguous, key=lambda x: x["path"]),
        # Proven static test → source relations (R3). Not capability evidence and never
        # counted in ``mapped``/``coverage_dimensions``: the impact engine folds them
        # into test selection (``pr_capability_impact_gate.build_snapshot``).
        "test_dependencies_semantics": (
            "static_import_source_read_loader_edges__unresolved_dynamic_relations_explicit"
        ),
        "test_dependencies": sorted(test_dependencies, key=lambda x: x["test"]),
    }


def write_outputs(data: dict, out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "capability_mapping.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (out / "capability_mapping.csv").open("w", newline="", encoding="utf-8") as f:
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
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
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
    (out / "unmapped_artifacts.json").write_text(
        json.dumps(data["unmapped_artifacts"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out / "ambiguous_artifacts.json").write_text(
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
    (out / "CAPABILITY_MAPPING_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {}
    for name in (
        "capability_mapping.json",
        "capability_mapping.csv",
        "unmapped_artifacts.json",
        "ambiguous_artifacts.json",
        "CAPABILITY_MAPPING_REPORT.md",
    ):
        manifest[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / "mapping_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check_outputs(data: dict) -> bool:
    names = (
        "capability_mapping.json",
        "capability_mapping.csv",
        "unmapped_artifacts.json",
        "ambiguous_artifacts.json",
        "CAPABILITY_MAPPING_REPORT.md",
        "mapping_manifest.json",
    )
    with tempfile.TemporaryDirectory(prefix="sahool-capability-mapping-check-") as tmp:
        candidate = Path(tmp)
        write_outputs(data, candidate)
        drifting = [
            name
            for name in names
            if not (OUT / name).exists()
            or (OUT / name).read_bytes() != (candidate / name).read_bytes()
        ]
    if not drifting:
        return True
    print(
        "capability mapping generated-artifact drift: " + ", ".join(drifting),
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
