#!/usr/bin/env python3
"""MANIFEST-REGISTRY-01 — سجلّ البيانات التعريفية التحكيمية وحراسته.

الفجوة: عشرات ملفّات ``docs/architecture/*.json`` بياناتٌ تعريفية تحكم حراساً،
بعضها محكَّم بتاريخ (``adjudicated_on``) وبعضها عارٍ، ولا قائمة بها أصلاً —
فبيان جديد يدخل بصمت ولا يعرف أحد أيّها يحتاج تحكيماً وأيّها لا.

القاعدة (مشتقّة لا يدويّة — نمط schema_validation_policy):
  كلّ ملف ``docs/architecture/*.json`` يحمل ``adjudicated_on`` **يجب** أن يكون
  مسجَّلاً هنا. والسجلّ نفسه محكَّم. الجرد يُشتقّ من ``git ls-files`` وقت
  التشغيل؛ قائمة مكتوبة يدويّاً تنحرف يوم يُضاف بيان جديد.

الراتش (لا يكسر القديم):
  - ``governed``: ``schema`` + ``version`` + ``adjudicated_on`` — الواجب لكلّ جديد.
  - ``legacy_schema_version`` / ``legacy_adjudicated``: صنفان انتقاليّان
    للستّة القائمة — تُصنَّف وتُؤرخَخ ولا تُكسر، وأيّ بيان جديد خارج
    ``governed`` يُرفض.

الاستعمال: التشغيل العاري فحص (نمط claim_base_guard)، و``--fix`` يعيد توليد
السجلّ من الجرد. الفحص يجري في CI عبر tests_v9/test_manifest_registry_guard.py
وعبر باك-stop المكنسة (شجرة متّسخة بعد الفحص = انحراف).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "manifest_registry.json"
SCAN_DIR = "docs/architecture"
SCHEMA = "sahool.manifest_registry"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

KIND_RULES = {
    "governed": ("schema", "version", "adjudicated_on"),
    "legacy_schema_version": ("schema_version", "adjudicated_on"),
    "legacy_adjudicated": ("adjudicated_on",),
}


def tracked_manifests() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", f"{SCAN_DIR}/*.json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    return sorted(p for p in out.stdout.split() if p.strip())


def classify(path: str) -> str | None:
    """يعيد صنف البيان إن كان يحمل adjudicated_on، وإلا None (خارج النطاق)."""
    try:
        data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or "adjudicated_on" not in data:
        return None
    if "schema" in data and "version" in data:
        return "governed"
    if "schema_version" in data:
        return "legacy_schema_version"
    return "legacy_adjudicated"


def derive_entries() -> dict[str, str]:
    """{path: kind} من الجرد الفعلي — لا يد تكتب هذه القائمة."""
    entries = {}
    for path in tracked_manifests():
        kind = classify(path)
        if kind:
            entries[path] = kind
    return entries


def validate_manifest(path: str, kind: str, errors: list[str]) -> None:
    """قيود الصنف على الملف ذاته (وجود المفاتيح + تاريخ ISO سليم)."""
    try:
        data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{path}: JSON فاسد — {e}")
        return
    for key in KIND_RULES[kind]:
        if key not in data:
            errors.append(f"{path}: صنفه {kind} لكنه بلا «{key}»")
    date = data.get("adjudicated_on", "")
    if not ISO_DATE.match(str(date)):
        errors.append(f"{path}: adjudicated_on بصيغة غير ISO: {date!r}")


def build_registry(entries: dict[str, str]) -> dict:
    return {
        "schema": SCHEMA,
        "version": 1,
        "adjudicated_on": "2026-08-05",
        "note_ar": "سجلّ البيانات التعريفية التحكيمية (MANIFEST-REGISTRY-01). لا تُحرَّر القائمة يدويّاً: تُشتقّ من `git ls-files docs/architecture/*.json` + قاعدة «يحمل adjudicated_on»، ويعيد توليدها `manifest_registry_guard.py --fix`. الراتش: كلّ بيان جديد يجب أن يكون governed (schema+version+adjudicated_on)؛ الصنفان legacy انتقالان للستّة القائمة فقط.",
        "derivation_rule_ar": "كل docs/architecture/*.json يحمل adjudicated_on يُسجَّل؛ ما عداه خارج نطاق المرحلة 1.",
        "entries": [{"path": path, "kind": kind} for path, kind in sorted(entries.items())],
    }


def check(fix: bool) -> int:
    errors: list[str] = []
    expected = derive_entries()

    if not REGISTRY.is_file():
        if not fix:
            print(f"✗ {REGISTRY.relative_to(ROOT)} غير موجود — شغّل --fix")
            return 1
    if REGISTRY.is_file():
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        # السجلّ نفسه بيان governed — لا استثناء لحارس السجلّ.
        for key in KIND_RULES["governed"]:
            if key not in registry:
                errors.append(f"السجلّ نفسه بلا «{key}» — حارس بلا تحكيم")
        if registry.get("schema") != SCHEMA:
            errors.append(f"schema السجلّ = {registry.get('schema')!r} ≠ {SCHEMA!r}")
        registered = {e["path"]: e["kind"] for e in registry.get("entries", [])}
    else:
        registered = {}

    missing = sorted(set(expected) - set(registered))
    extra = sorted(set(registered) - set(expected))
    reclassified = sorted(p for p in expected if p in registered and registered[p] != expected[p])
    for p in missing:
        errors.append(f"بيان محكَّم غير مسجَّل: {p} ({expected[p]})")
    for p in extra:
        errors.append(f"مدخل بلا بيان محكَّم فعلي: {p} — احذفه أو أعد التحكيم")
    for p in reclassified:
        errors.append(f"{p}: مسجَّل {registered[p]} والفعلي {expected[p]} — أعد التصنيف")

    # قيود الأصناف على الملفات ذاتها (المتوقَّعة = الواقع، لا السجلّ وحده)
    for path, kind in expected.items():
        validate_manifest(path, kind, errors)

    if errors and fix:
        REGISTRY.write_text(
            json.dumps(build_registry(expected), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"أُعيد توليد {REGISTRY.relative_to(ROOT)} ({len(expected)} مدخلاً)")
        # أعد الفحص بعد التوليد — التوليد لا يُعلن النجاح قبل إثباته
        return check(fix=False)

    if errors:
        for e in errors:
            print(f"✗ {e}")
        return 1
    print(
        f"manifest_registry_guard_ok: {len(expected)} بياناً محكَّماً مسجَّلاً "
        f"(governed={sum(1 for k in expected.values() if k == 'governed')}, "
        f"legacy={sum(1 for k in expected.values() if k != 'governed')})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args(argv)
    return check(fix=args.fix)


if __name__ == "__main__":
    sys.exit(main())
