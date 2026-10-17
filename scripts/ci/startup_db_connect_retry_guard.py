#!/usr/bin/env python3
"""إقلاعٌ لا يفترض أنّ Postgres جاهز — `RESTART-POLICY-BYPASSES-DEPENDS-ON-HEALTH-01`.

``depends_on: condition: service_healthy`` يُقيَّم عند ``docker compose up`` وحده.
حاوٍ أعادته سياسةُ ``restart:`` بعد إعادة تشغيل الخادم لا ينتظر تبعيّاته، فخدمةٌ
يفشل اتّصالُها الأوّل سريعاً تموت (أو تبتلع الرفض فتعمل بلا قاعدة إلى الأبد) بينما
Postgres ما يزال يُقلِع. فالضمانُ في الخدمة لا في compose.

يفرض هذا الحارس الجردَ ``docs/architecture/startup_db_connect_inventory.json``:

1. **المجموعة مشتقّة لا منسوخة:** خدماتُ ``docker-compose.v9.yml`` التي تعتمد على
   ``sahool-postgres`` بشرط ``service_healthy`` = خدماتُ الجرد ∪ ``pending_removal``.
   خدمةٌ جديدة بهذا الاعتماد بلا تصنيفٍ تُحجَب، ومدخلٌ لخدمةٍ غابت يُحجَب.
2. **الصنف يُقرأ من الشيفرة عند المرساة** (``path::function``، لا رقمَ سطر — فنقلُ
   الأسطر لا يُحمِّر): أوّلُ اتّصالٍ في الدالّة إمّا عبر ``retry_startup_connect``،
   أو داخل حلقةٍ تبتلع الفشل، أو مباشرٌ — ويجب أن يطابق الصنفَ المُعلَن.
3. ``gate01_frozen_fail_fast`` لا يُقبَل إلّا لمسارٍ في ``frozen_paths`` من
   ``gate01_policy.json`` — وما سواه يُصلَح لا يُصنَّف.
4. ``one_shot`` لا يُقبَل إلّا مع ``restart: "no"``، و``third_party_image`` إلّا بلا
   ``build:``.
5. ``retries_with_backoff`` يلزمه أن تنسخ صورةُ الخدمة ``shared/startup_retry.py``
   (``shared/`` كاملاً أو الملفّ نفسه) — إصلاحٌ لا يصل الصورة ليس إصلاحاً.

``pending_removal`` يقبل وجودَ الاسم في compose وغيابَه معاً، ويطبع تذكيراً بحذفه
متى غاب — كي يبقى الحارس أخضرَ قبل إزالة خدمةٍ تُزال بفرعٍ موازٍ وبعدها.

حدودٌ مكتوبة: ``connects_lazily`` يُفحَص داخل وحدة المرساة وحدها (لا تستدعيها دالّةُ دورة
الحياة هناك: ``lifespan`` أو ما يُمرَّر ``lifespan=``)، لا رسمَ الاستدعاء عبر الوحدات. و
``no_postgres_client`` يفحص مجلّد الخدمة لا ``shared/`` المنسوخة معه.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "architecture" / "startup_db_connect_inventory.json"
GATE01_POLICY = ROOT / "docs" / "architecture" / "gate01_policy.json"

CLASSES = frozenset(
    {
        "retries_with_backoff",
        "polls_until_ready",
        "connects_lazily",
        "no_postgres_client",
        "third_party_image",
        "one_shot",
        "gate01_frozen_fail_fast",
    }
)
_NEEDS_PY_ANCHOR = frozenset(
    {"retries_with_backoff", "connects_lazily", "gate01_frozen_fail_fast", "polls_until_ready"}
)
_CONNECTS = frozenset({"create_pool", "connect"})
_RETRY = "retry_startup_connect"
_PG_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:asyncpg|psycopg2?|psycopg)\b", re.M)
_SHELL_WAIT = re.compile(r"^\s*(?:until|while)\b[^\n]*\bpg_isready\b", re.M)


def dependants(compose: dict, postgres: str) -> dict[str, dict]:
    """الخدمات التي تعتمد على ``postgres`` بشرط ``service_healthy``."""
    out: dict[str, dict] = {}
    for name, svc in (compose.get("services") or {}).items():
        dep = (svc or {}).get("depends_on") or {}
        if isinstance(dep, dict):
            cond = dep.get(postgres)
            if isinstance(cond, dict) and cond.get("condition") == "service_healthy":
                out[name] = svc
    return out


def _direct_connect(call: ast.Call, via: str | None) -> bool:
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr in _CONNECTS:
        return isinstance(fn.value, ast.Name) and fn.value.id == "asyncpg"
    return via is not None and isinstance(fn, ast.Name) and fn.id == via


def _is_retry(call: ast.Call) -> bool:
    fn = call.func
    name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
    return name == _RETRY


def _find_function(tree: ast.AST, qualname: str) -> ast.AST | None:
    scope: list[ast.AST] = [tree]
    node: ast.AST | None = None
    for part in qualname.split("."):
        node = None
        for parent in scope:
            for child in ast.iter_child_nodes(parent):
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and child.name == part
                ):
                    node = child
                    break
            if node is not None:
                break
        if node is None:
            return None
        scope = [node]
    return node


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def first_connect(func: ast.AST, via: str | None) -> tuple[str, ast.Call] | None:
    """أوّلُ اتّصالٍ بترتيب المصدر: ``("retry", call)`` أو ``("direct", call)``."""
    calls = sorted(
        (n for n in ast.walk(func) if isinstance(n, ast.Call)),
        key=lambda n: (n.lineno, n.col_offset),
    )
    for call in calls:
        if _is_retry(call):
            return "retry", call
        if _direct_connect(call, via):
            return "direct", call
    return None


def _inside_polling_loop(call: ast.Call, func: ast.AST, parents: dict) -> bool:
    """الاستدعاء داخل ``try`` تلتقط ``Exception`` وهي بدورها داخل ``while``."""
    node, caught = call, False
    while node is not func and node in parents:
        parent = parents[node]
        if isinstance(parent, ast.Try) and node in parent.body:
            caught = caught or any(
                h.type is None or (isinstance(h.type, ast.Name) and h.type.id == "Exception")
                for h in parent.handlers
            )
        if isinstance(parent, ast.While) and caught:
            return True
        node = parent
    return False


def _lifespans(tree: ast.AST) -> set[str]:
    """أسماءُ دوالّ دورة الحياة: ما يُمرَّر ``lifespan=`` في الوحدة، و``lifespan`` نفسها."""
    names = {"lifespan"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            for kw in n.keywords:
                if kw.arg == "lifespan" and isinstance(kw.value, ast.Name):
                    names.add(kw.value.id)
    return names


def _called_from_lifespan(tree: ast.AST, name: str) -> list[str]:
    hits = []
    lifespans = _lifespans(tree)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name not in lifespans:
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name:
                hits.append(fn.name)
    return hits


def _image_copies_startup_retry(svc: dict) -> bool | None:
    build = svc.get("build")
    if not isinstance(build, dict) or not build.get("dockerfile"):
        return None
    dockerfile = ROOT / build.get("context", ".") / build["dockerfile"]
    if not dockerfile.is_file():
        return False
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].upper() == "COPY":
            srcs = [p for p in parts[1:-1] if not p.startswith("--")]
            if any(s.rstrip("/") in {"shared", "shared/startup_retry.py"} for s in srcs):
                return True
    return False


def check_entry(name: str, entry: dict, svc: dict | None, frozen: set[str]) -> list[str]:
    errs: list[str] = []
    cls = entry.get("class")
    if cls not in CLASSES:
        return [f"{name}: صنفٌ مجهول {cls!r} — المسموح: {sorted(CLASSES)}"]
    svc = svc or {}

    if cls == "one_shot":
        restart = svc.get("restart")
        if restart not in ("no", False):
            errs.append(f'{name}: one_shot يلزمه restart: "no" (وجدتُ {restart!r})')
        return errs
    if cls == "third_party_image":
        if "build" in svc or not svc.get("image"):
            errs.append(f"{name}: third_party_image يلزمه image بلا build")
        return errs
    if cls == "no_postgres_client":
        src = ROOT / str(entry.get("source_dir", ""))
        if not entry.get("source_dir") or not src.is_dir():
            return [f"{name}: no_postgres_client يلزمه source_dir موجود"]
        for py in sorted(src.rglob("*.py")):
            if "test" in py.name:
                continue
            if _PG_IMPORT.search(py.read_text(encoding="utf-8", errors="replace")):
                errs.append(
                    f"{name}: صُنِّف no_postgres_client و{py.relative_to(ROOT)} يستورد "
                    "عميل Postgres — صنّفه من شيفرته."
                )
        return errs

    anchor = str(entry.get("anchor", ""))
    path_s, _, qual = anchor.partition("::")
    path = ROOT / path_s
    if not path_s or not path.is_file():
        return [f"{name}: المرساة {anchor!r} لا تشير إلى ملفّ موجود"]

    if cls == "gate01_frozen_fail_fast" and path_s not in frozen:
        errs.append(
            f"{name}: gate01_frozen_fail_fast على {path_s} وهو غير مجمَّد في "
            "gate01_policy.json — هذا يُصلَح بـretry_startup_connect لا يُصنَّف."
        )

    if cls == "polls_until_ready" and not qual:
        if not _SHELL_WAIT.search(path.read_text(encoding="utf-8")):
            errs.append(f"{name}: {path_s} لا ينتظر بـuntil/while pg_isready")
        return errs

    if cls in _NEEDS_PY_ANCHOR and not qual:
        return errs + [f"{name}: {cls} يلزمه مرساةٌ بصيغة path::function"]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    func = _find_function(tree, qual)
    if func is None:
        return errs + [f"{name}: الدالّة {qual!r} غير موجودة في {path_s}"]
    via = entry.get("via")
    found = first_connect(func, via)
    if found is None:
        return errs + [f"{name}: لا اتّصالَ بـPostgres في {anchor}"]
    kind, call = found
    where = f"{path_s}:{call.lineno}"

    if cls == "retries_with_backoff":
        if kind != "retry":
            errs.append(
                f"{name}: صُنِّف retries_with_backoff وأوّلُ اتّصالٍ في {where} مباشر — "
                "إعادةٌ بسياسة restart بعد إعادة تشغيل الخادم تموت على أوّل رفض."
            )
        elif _image_copies_startup_retry(svc) is False:
            errs.append(f"{name}: صورتُه لا تنسخ shared/startup_retry.py — الإصلاح لا يصل الحاوية")
    elif cls == "gate01_frozen_fail_fast":
        if kind != "direct":
            errs.append(
                f"{name}: صُنِّف gate01_frozen_fail_fast و{where} يعيد المحاولة — "
                "أعِد تصنيفه retries_with_backoff."
            )
    elif cls == "polls_until_ready":
        if kind != "direct" or not _inside_polling_loop(call, func, _parents(func)):
            errs.append(f"{name}: صُنِّف polls_until_ready و{where} ليس داخل while/try تبتلع الفشل")
    elif cls == "connects_lazily":
        callers = _called_from_lifespan(tree, qual.split(".")[-1])
        if callers:
            errs.append(
                f"{name}: صُنِّف connects_lazily و{qual} تُستدعى من دورة الحياة "
                f"{callers} في {path_s} — هذا اتّصالُ إقلاع."
            )
    return errs


def check(inventory: dict, compose: dict, frozen: set[str]) -> tuple[list[str], list[str]]:
    """يُرجِع (أسباب الحجب، ملاحظات)."""
    errs: list[str] = []
    notes: list[str] = []
    derived = dependants(compose, inventory.get("postgres_service", "sahool-postgres"))
    services = inventory.get("services") or {}
    pending = inventory.get("pending_removal") or {}

    both = sorted(set(services) & set(pending))
    if both:
        errs.append(f"في services وpending_removal معاً: {both}")
    for name, meta in pending.items():
        if not str((meta or {}).get("reason", "")).strip():
            errs.append(f"pending_removal[{name}]: بلا سبب مكتوب")
        if name not in derived:
            notes.append(f"{name} غاب عن compose — احذف مدخله من pending_removal")

    unclassified = sorted(set(derived) - set(services) - set(pending))
    for name in unclassified:
        errs.append(
            f"{name}: يعتمد على Postgres بشرط service_healthy ولا تصنيفَ له في "
            f"{INVENTORY.relative_to(ROOT)} — والشرطُ لا يحمي إعادةً بسياسة restart. "
            "لُفّ اتّصاله الأوّل بـshared.startup_retry.retry_startup_connect وصنّفه."
        )
    for name in sorted(set(services) - set(derived)):
        errs.append(f"{name}: مُصنَّف في الجرد ولا يعتمد على Postgres في compose — احذفه")

    for name in sorted(set(services) & set(derived)):
        errs.extend(check_entry(name, services[name] or {}, derived[name], frozen))
    return errs, notes


def load_frozen() -> set[str]:
    policy = json.loads(GATE01_POLICY.read_text(encoding="utf-8"))
    return {str(p) for p in policy.get("frozen_paths", [])}


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    compose_path = ROOT / inventory.get("compose_file", "docker-compose.v9.yml")
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    errs, notes = check(inventory, compose, load_frozen())
    for note in notes:
        print(f"  note: {note}")
    if errs:
        print("startup_db_connect_retry_guard: FAIL", file=sys.stderr)
        for e in errs:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    for entry in (inventory.get("services") or {}).values():
        counts[entry["class"]] = counts.get(entry["class"], 0) + 1
    summary = " · ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"startup_db_connect_retry_guard_ok — {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
