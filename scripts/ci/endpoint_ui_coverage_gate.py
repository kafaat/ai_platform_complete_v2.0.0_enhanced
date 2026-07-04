#!/usr/bin/env python3
"""SAHOOL endpoint-ui-coverage-gate.

بوّابة ساكنة لعقد «backend ⇒ واجهة»:
  1. تفحص أنّ كلّ endpoint جوهريّ (مُصنَّف في config/endpoint_ui_coverage.json
     بجمهور غير internal/admin-internal) يملك دليلاً نصّيّاً في الواجهة
     (frontend/src أو mobile/lib) — لا endpoint منتِج يبقى بلا hook/شاشة.
  2. تولّد (بـ--report) مصفوفة تغطية كاملة backend⇄frontend مُصنَّفة بالجمهور
     إلى docs/api/BACKEND_FRONTEND_COVERAGE.md.

صدق: الدليل نصّ حقيقيّ في الكود (نفس فلسفة service_feature_ui_contract_gate) —
لا توليد وثائق يُعتمَد عليه وحده. المسارات الداخليّة/العامل/الإدارة الخالصة تُصنَّف
internal ولا تُطالَب بواجهة مستخدم.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / "config" / "endpoint_ui_coverage.json"
REPORT = REPO / "docs" / "api" / "BACKEND_FRONTEND_COVERAGE.md"

ROUTE_RE = re.compile(
    r'@(?:router|app)\.(get|post|put|delete|patch|websocket)\(\s*["\']([^"\']+)["\']'
)
HEALTH_TOKENS = ("health", "readyz", "livez", "metrics")

FRONTEND_ROOTS = ("frontend/src", "mobile/lib")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def collect_backend_routes() -> dict[str, set[str]]:
    """كلّ المسارات غير الصحّيّة في services/ ⇒ {path: {method@file}}."""
    routes: dict[str, set[str]] = {}
    for py in (REPO / "services").rglob("*.py"):
        parts = set(py.parts)
        if parts & {"tests", "__pycache__", "node_modules"}:
            continue
        text = _read(py)
        for m in ROUTE_RE.finditer(text):
            path = m.group(2)
            if any(tok in path for tok in HEALTH_TOKENS):
                continue
            routes.setdefault(path, set()).add(f"{m.group(1)}@{py.relative_to(REPO)}")
    return routes


def collect_frontend_corpus() -> str:
    """نصّ الواجهة كاملاً (للبحث عن أدلّة المسارات)."""
    chunks: list[str] = []
    for root in FRONTEND_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".dart"}:
                chunks.append(_read(f))
    return "\n".join(chunks)


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def classify(path: str, classifications: list[dict]) -> str:
    for rule in classifications:
        if path.startswith(rule["prefix"]):
            return rule["audience"]
    # المسارات غير المُبوَّبة عبر /api/v1 عقودُ خدمةٍ داخليّةٌ (workers/بروكسي بوّابة/
    # ML runtime) تحرسها بوّابة service_feature_ui_contract المنفصلة (26/26) —
    # فتصنيفها الافتراضيّ internal لا unclassified. أمّا /api/v1/* فيجب تصنيفه
    # صراحةً في config (الحارس يفرض صفر unclassified).
    if not path.startswith("/api/v1/"):
        return "internal"
    return "unclassified"


def run_gate() -> int:
    cfg = load_config()
    corpus = collect_frontend_corpus()
    failures: list[str] = []
    for entry in cfg["core_endpoints"]:
        evidence = entry["evidence"]
        if evidence not in corpus:
            failures.append(
                f"  ✗ {entry['endpoint']} (جمهور: {entry['audience']}) — لا دليل واجهة للنمط `{evidence}`"
            )
    if failures:
        print("endpoint-ui-coverage-gate: FAIL — endpoints جوهريّة بلا واجهة/hook:")
        print("\n".join(failures))
        return 1
    print(
        f"endpoint-ui-coverage-gate: PASS — {len(cfg['core_endpoints'])} endpoint جوهريّ كلّها بدليل واجهة."
    )
    return 0


def write_report() -> None:
    cfg = load_config()
    corpus = collect_frontend_corpus()
    routes = collect_backend_routes()
    classifications = cfg["classifications"]

    rows: list[tuple[str, str, str]] = []
    audience_counts: dict[str, list[int]] = {}
    for path in sorted(routes):
        audience = classify(path, classifications)
        # دليل التغطية: المسار الحرفيّ أو جذعه قبل أوّل {param} موجود في نصّ الواجهة.
        stem = re.split(r"\{", path)[0].rstrip("/")
        covered = bool(stem) and len(stem) > len("/api/v1/") and stem in corpus
        rows.append((path, audience, "✅" if covered else "—"))
        agg = audience_counts.setdefault(audience, [0, 0])
        agg[0] += 1
        agg[1] += 1 if covered else 0

    lines = [
        "# مصفوفة تغطية Backend ⇄ Frontend",
        "",
        "> تُولَّد بـ`python3 scripts/ci/endpoint_ui_coverage_gate.py --report` — لا تُحرَّر يدويّاً.",
        "> «مغطّى» = جذع المسار (قبل أوّل معامل) يظهر حرفيّاً في frontend/src أو mobile/lib.",
        "> التغطية النصّيّة استدلاليّة: وجود الجذع لا يعني شاشة كاملة، وغيابه لمسار داخليّ ليس نقصاً.",
        "",
        "## ملخّص حسب الجمهور",
        "",
        "| الجمهور | المسارات | مغطّى نصّيّاً |",
        "|---|---|---|",
    ]
    for aud in sorted(audience_counts):
        total, cov = audience_counts[aud]
        lines.append(f"| {aud} | {total} | {cov} |")
    lines += [
        "",
        f"العقد الملزِم (core): {len(cfg['core_endpoints'])} endpoint في `config/endpoint_ui_coverage.json` — تحرسها بوّابة CI.",
        "",
        "## الجدول الكامل",
        "",
        "| المسار | الجمهور | مغطّى |",
        "|---|---|---|",
    ]
    for path, audience, covered in rows:
        lines.append(f"| `{path}` | {audience} | {covered} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {REPORT.relative_to(REPO)} ({len(rows)} مساراً)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="توليد مصفوفة التغطية")
    args = parser.parse_args()
    if args.report:
        write_report()
        return 0
    return run_gate()


if __name__ == "__main__":
    sys.exit(main())
