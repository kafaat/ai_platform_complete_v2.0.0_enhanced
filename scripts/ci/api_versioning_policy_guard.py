#!/usr/bin/env python3
"""Inventory and freeze unversioned business routes.

New business endpoints should use /v1 unless explicitly classified as health,
metrics, internal S2S, GraphQL facade, or legacy_unversioned in the generated
allowlist. This avoids breaking existing clients while preventing drift.
"""

from __future__ import annotations

import ast
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INV = ROOT / "api_versioning_inventory.generated.json"
CSV = ROOT / "api_versioning_inventory.csv"
ALLOW = ROOT / "api_versioning_legacy_allowlist.generated.json"
METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
INFRA_PREFIXES = ("/health", "/healthz", "/readyz", "/metrics", "/contract", "/capabilities", "/")


def _service_for(path: Path) -> str:
    parts = path.relative_to(ROOT).parts
    if parts[0] == "services":
        return parts[1]
    if parts[0] == "bots":
        return f"bots/{parts[1]}"
    return parts[0]


# APIRouter(prefix=...) العمى: collect() كان يقرأ نصّ الديكوريتر وحده — @router.get("/plan")
# — بلا تركيب بادئة الراوتر نفسه (`router = APIRouter(prefix="/v1/phase9/autonomy")`)، فمسار
# مُصدَّر فعلاً على الشبكة (`/v1/phase9/autonomy/plan`) يُصنَّف «غير مُصدَّر» لأنّ نصّه الحرفيّ
# لا يبدأ بمقطع إصدار. مسح شامل للمستودع (`include_router(..., prefix=...)` عبر خدمة) لم يجد
# ولا استخداماً واحداً — البادئة الوحيدة المُستعمَلة فعليّاً هي `APIRouter(prefix=...)` في نفس
# ملفّ الراوتر، فالتركيب هنا محليّ الملفّ بحت، لا يحتاج تتبّعاً عبر ملفّات. (API-VERSIONING-GUARD-IS-A-MIRROR-01)
def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "APIRouter"
        ):
            continue
        prefix = None
        for kw in call.keywords:
            if (
                kw.arg == "prefix"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                prefix = kw.value.value
        if prefix is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _routes(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    prefixes = _router_prefixes(tree)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in METHODS
            ):
                if (
                    dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                ):
                    route_path = dec.args[0].value
                    if isinstance(dec.func.value, ast.Name):
                        prefix = prefixes.get(dec.func.value.id)
                        if prefix:
                            route_path = prefix.rstrip("/") + route_path
                    rows.append(
                        {
                            "service": _service_for(path),
                            "file": path.relative_to(ROOT).as_posix(),
                            "line": getattr(node, "lineno", 0),
                            "method": dec.func.attr.upper(),
                            "path": route_path,
                            "handler": node.name,
                        }
                    )
    return rows


# مقطع إصدار في البادئة: `/v1/...` أو `/api/v1/...`. المُصنِّف الأوّل عرف الأوّل
# وحده، بينما عرف المنصّة الفعليّ هو الثاني — فصُنِّف **٥١٧ مساراً مُصدَّراً** بوصفه
# «قديماً غير مُصدَّر». لم يكن خطأ بيانات بل خطأ **تعريف**: قاعدة كُتبت من عرف
# مُتخيَّل لا من الشجرة. (API-VERSIONING-GUARD-IS-A-MIRROR-01)
_VERSIONED = re.compile(r"^(?:/api)?/v[0-9]+(?:/|$)")


def _classify(path: str) -> str:
    if _VERSIONED.match(path):
        return "versioned"
    if path.startswith("/internal/"):
        return "internal_s2s"
    if path == "/graphql":
        return "graphql_facade"
    # /runtime-identity is grouped with healthz/readyz/metrics as a provenance/
    # infrastructure route (CLAUDE.md, platform_route_placement_contract.json) and
    # is contract-declared, probe-configured (functional_probe_runner.py identity_path),
    # and attestation-tested — not a genuine unversioned business route to migrate.
    if path.startswith("/health") or path in {
        "/readyz",
        "/metrics",
        "/contract",
        "/capabilities",
        "/runtime-identity",
        "/",
    }:
        return "infra"
    return "legacy_unversioned_business"


def _is_test_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return "/tests/" in rel or rel.startswith("tests/") or path.name.startswith("test_")


# وحدات تُعرّف مسارات على تطبيق FastAPI **مستقلّ غير مُركَّب** — أمثلة مرجعيّة لا سطح
# مخدوم. نفس صنف استبعاد ملفّات الاختبار أعلاه: الجرد يصف ما تخدمه الخدمة فعلاً، وادّعاء
# مسار غير موجود في التطبيق العامل خطأ صدق لا دَين هجرة.
#   • services/sahool-platform/api/chat_proxy_reference.py — ثلاثة أقفال بنيويّة مستقلّة:
#     (١) خارج `api/routers/`، و`register_routers()` يُسجّل تلقائيّاً وحدات تلك الحزمة
#         وحدها (`pkgutil.iter_modules(_routers_pkg.__path__)`، api/router_registry.py)؛
#     (٢) صفر استيراد إنتاجيّ في المستودع (المطابقتان الوحيدتان تعليق في
#         ai_provider_config.py ونصّ docstring داخل الملفّ نفسه — لا `import`)؛
#     (٣) لا يُصدِّر `router` إطلاقاً، بل `app = FastAPI(...)` داخل try/except كمثال
#         قابل للتشغيل مستقلّاً (`uvicorn api.chat_proxy_reference:app`).
#     docstring الملفّ صريح: «هذا ملف مرجعي يوضّح النمط… النواة الحالية لا تتضمّن خادماً».
#     سابقة مستقلّة قائمة: tests_v9/test_endpoint_auth_coverage.py يستثنيه بالاسم للسبب نفسه.
#   الحقائق الثلاث مُثبَّتة في tests_v9/test_api_versioning_policy_guard.py — لو رُكِّب
#   الملفّ يوماً (أو نُقِل إلى api/routers/) يسقط الاختبار ويُجبِر إعادة التقييم.
_UNMOUNTED_REFERENCE_FILES = frozenset({"services/sahool-platform/api/chat_proxy_reference.py"})


def _is_unmounted_reference(path: Path) -> bool:
    return path.relative_to(ROOT).as_posix() in _UNMOUNTED_REFERENCE_FILES


def collect():
    paths = list(ROOT.glob("services/**/*.py")) + list(ROOT.glob("bots/**/*.py"))
    rows = []
    for p in sorted(paths):
        if "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        # الجرد يقيس الـAPI الإنتاجيّ، لا مسارات الفحص الداخليّة داخل ملفّات الاختبار
        # (مثل `GET /probe` في test_correlation_middleware.py) — استبعاد بنيويّ لا
        # يدويّ، حتى يبقى الأساس 250/230/55 قابلاً لإعادة التوليد بلا تدخّل.
        if _is_test_file(p):
            continue
        # تطبيق مرجعيّ مستقلّ غير مُركَّب ⇒ ليس سطحاً مخدوماً (انظر التعليق أعلاه).
        if _is_unmounted_reference(p):
            continue
        rows.extend(_routes(p))
    for r in rows:
        r["classification"] = _classify(r["path"])
    return rows


def write(rows):
    INV.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["service", "file", "line", "method", "path", "handler", "classification"]
        )
        w.writeheader()
        w.writerows(rows)
    legacy = sorted(
        {
            f"{r['method']} {r['path']}"
            for r in rows
            if r["classification"] == "legacy_unversioned_business"
        }
    )
    ALLOW.write_text(
        json.dumps({"legacy_unversioned_business_routes": legacy}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def main():
    check = "--check" in sys.argv
    rows = collect()
    before = INV.read_text(encoding="utf-8") if INV.exists() else None
    before_csv = CSV.read_text(encoding="utf-8") if CSV.exists() else None
    before_allow = ALLOW.read_text(encoding="utf-8") if ALLOW.exists() else None
    write(rows)
    if check and before is not None:
        if (
            before != INV.read_text(encoding="utf-8")
            or before_csv != CSV.read_text(encoding="utf-8")
            or before_allow != ALLOW.read_text(encoding="utf-8")
        ):
            raise SystemExit(
                "api versioning inventory drift; rerun scripts/ci/api_versioning_policy_guard.py and review unversioned allowlist"
            )
        # API-VERSIONING-GUARD-IS-A-MIRROR-01: المقارنة أعلاه تكشف الانحراف، لكنّ
        # علاجها المُوثَّق «أعِد التوليد» — فمسار غير مُصدَّر **جديد** يُقبَل بمجرّد
        # الالتزام بالقائمة الجديدة. كاشف انحراف لا بوّابة سياسة. الراتشِت أدناه
        # يمنع **النموّ**: التقلّص مسموح ومطلوب، والزيادة تُسقِط CI.
        #
        # شرطان مستقلّان، لا شرط واحد: عدّ فقط (len(current) <= ceiling) لا يمنع
        # استبدال دَين قديم بدَين جديد — إغلاق مسارَين وفتح مسارَين مختلفَين يُبقي
        # العدد ثابتاً فيمرّ صامتاً. الشرط الثاني (current_set ⊆ frozen_set) يمنع هذا:
        # أيّ مسار **جديد** في القائمة الحاليّة لم يكن في المجموعة المُجمَّدة يُسقِط CI
        # فوراً حتى لو بقي العدد الكلّي تحت السقف.
        import json as _json

        baseline = ROOT / "docs" / "architecture" / "api_versioning_legacy_baseline.json"
        if baseline.exists():
            baseline_data = _json.loads(baseline.read_text(encoding="utf-8"))
            ceiling = baseline_data["ceiling"]
            current_routes = _json.loads(ALLOW.read_text(encoding="utf-8"))[
                "legacy_unversioned_business_routes"
            ]
            current = len(current_routes)
            if current > ceiling:
                raise SystemExit(
                    f"قائمة السماح نمت {ceiling} ⇒ {current}. مسار عمل جديد بلا إصدار "
                    "لا يُقبَل بإعادة التوليد — أصدِره تحت /api/v1/ أو صنّفه بحقّه. "
                    f"الأساس: {baseline.relative_to(ROOT)} (يتقلّص ولا ينمو)."
                )
            if current < ceiling:
                print(f"  قائمة السماح تقلّصت {ceiling} ⇒ {current} — حدّث ceiling في الأساس.")

            frozen_routes = baseline_data.get("routes")
            if frozen_routes is not None:
                current_set = set(current_routes)
                frozen_set = set(frozen_routes)
                escaped = current_set - frozen_set
                if escaped:
                    raise SystemExit(
                        "قائمة السماح تحمل مساراً/مسارات جديدة ليست في المجموعة المُجمَّدة "
                        f"(استبدال دَين لا تقلّصه، مرفوض حتى لو بقي العدد تحت السقف): "
                        f"{sorted(escaped)}. أصدِرها تحت /api/v1/ أو أضِفها إلى `routes` في "
                        f"{baseline.relative_to(ROOT)} إن كانت هجرة مُقرَّرة."
                    )
                if current_set != frozen_set:
                    print(
                        "  المجموعة المُجمَّدة تقلّصت "
                        f"{len(frozen_set)} ⇒ {len(current_set)} — حدّث `routes` في الأساس."
                    )
        print("api_versioning_policy_check_ok")
    else:
        counts = {}
        for r in rows:
            counts[r["classification"]] = counts.get(r["classification"], 0) + 1
        print("api_versioning_inventory_written", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
