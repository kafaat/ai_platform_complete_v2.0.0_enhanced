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

الاستعمال: التشغيل العاري يعيد توليد السجلّ عند انحرافه ويفشل على ما لا يُصلحه
التوليد (راتشة الصنف) — نمط build_platform_catalog «بلا علم، التشغيل العاري يكتب».
الفحص الصرف يجري في CI عبر tests_v9/test_manifest_registry_guard.py (تستدعي
check(fix=False))؛ لا يُعلَن علم كتابة لأنّ صلاحيات الدفع الحالية بلا workflow
scope فلا يمكن وصله بخطوة workflow — يُغلَق ذلك عند توفّرها.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "manifest_registry.json"
SCAN_DIR = "docs/architecture"
SCHEMA = "sahool.manifest_registry"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# راتشة الانتقال: الستّة القائمة عند ولادة الحارس — وحدها يُقبل صنف legacy لها.
# بيان جديد بلا schema+version يُرفض هنا، لا عند مراجعة بشرية قد تفوت.
LEGACY_ALLOWED = frozenset(
    {
        "docs/architecture/claim_base_registry.json",
        "docs/architecture/deferred_import_declaration_contract.json",
        "docs/architecture/expected_control_flow_exceptions.json",
        "docs/architecture/guard_mutation_registry.json",
        "docs/architecture/permanent_compatibility_contract.json",
        "docs/architecture/physical_effect_boundary_contract.json",
    }
)

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
    if out.returncode != 0:
        # جرد فارغ عند تعطّل git يُقرأ «لا بيانات» — فشل صامت. الحارس يُغلِق لا يفتح.
        raise RuntimeError(f"git ls-files فشل ({out.returncode}): {out.stderr.strip()}")
    # git pathspec ``docs/architecture/*.json`` also matches descendants; this contract
    # intentionally governs direct architecture manifests only. Nested evidence may be arrays
    # or other JSON payloads and has its own evidence contracts.
    return sorted(
        p for p in out.stdout.splitlines() if p.strip() and Path(p).parent.as_posix() == SCAN_DIR
    )


def _load(path: str) -> dict:
    """قراءة بيان. الفاسد يُرفع استثناءً — الابتلاع هنا كان fail-open (مراجعة Copilot)."""
    data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: الجذر ليس كائناً")
    return data


def classify(path: str) -> str | None:
    """يعيد صنف البيان إن كان يحمل adjudicated_on، وإلا None (خارج النطاق)."""
    data = _load(path)
    if not isinstance(data, dict) or "adjudicated_on" not in data:
        return None
    if "schema" in data and "version" in data:
        return "governed"
    if "schema_version" in data:
        return "legacy_schema_version"
    return "legacy_adjudicated"


def derive_entries(errors: list[str] | None = None) -> dict[str, str]:
    """{path: kind} من الجرد الفعلي — لا يد تكتب هذه القائمة.

    JSON الفاسد **خطأ يُجمَّع** حين تُمرَّر قائمة أخطاء (فحص CI)، ويُرفع استثناءً
    حين لا تُمرَّر (نداء الاختبارات المباشر) — ولا يُبتلَع صامتاً في الحالتين.
    """
    entries = {}
    for path in tracked_manifests():
        try:
            kind = classify(path)
        except Exception as e:
            if errors is None:
                raise
            errors.append(f"{path}: JSON فاسد أو غير قابل للقراءة — {e}")
            continue
        if kind:
            entries[path] = kind
    return entries


def validate_manifest(path: str, kind: str, errors: list[str]) -> None:
    """قيود الصنف على الملف ذاته (وجود المفاتيح + تاريخ ISO سليم)."""
    rules = KIND_RULES.get(kind)
    if rules is None:
        errors.append(f"{path}: صنف غير معروف {kind!r} — الأصناف: {sorted(KIND_RULES)}")
        return
    try:
        data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{path}: JSON فاسد — {e}")
        return
    for key in rules:
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
        "note_ar": "سجلّ البيانات التعريفية التحكيمية (MANIFEST-REGISTRY-01). لا تُحرَّر القائمة يدويّاً: تُشتقّ من `git ls-files docs/architecture/*.json` + قاعدة «يحمل adjudicated_on»، ويعيد توليدها `manifest_registry_guard.py`. الراتش: كلّ بيان جديد يجب أن يكون governed (schema+version+adjudicated_on)؛ الصنفان legacy انتقالان للستّة القائمة فقط.",
        "derivation_rule_ar": "كل ملف JSON مباشر تحت docs/architecture يحمل adjudicated_on يُسجَّل؛ مجلدات الأدلة المتداخلة خارج نطاق هذا السجل ولها عقودها الخاصة.",
        "entries": [{"path": path, "kind": kind} for path, kind in sorted(entries.items())],
    }


def check(fix: bool) -> int:
    errors: list[str] = []
    expected = derive_entries(errors)

    # الراتشة الفعليّة: legacy مقصور على الستّة الانتقاليّة — بيان جديد بلا
    # schema+version يُرفض حتى لو سُجّل (مراجعة Copilot: التصنيف وحده ليس إنفاذاً).
    for path, kind in sorted(expected.items()):
        if kind != "governed" and path not in LEGACY_ALLOWED:
            errors.append(
                f"{path}: بيان جديد بصنف {kind} — الواجب governed "
                "(schema + version + adjudicated_on)؛ legacy للستّة الانتقاليّة فقط"
            )

    if not REGISTRY.is_file():
        if not fix:
            print(f"✗ {REGISTRY.relative_to(ROOT)} غير موجود — شغّل السكربت بلا أعلام")
            return 1
    if REGISTRY.is_file():
        try:
            registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"السجلّ نفسه JSON فاسد — {e}")
            registry = None
    else:
        registry = None
    if registry is not None:
        # السجلّ نفسه بيان governed — لا استثناء لحارس السجلّ.
        for key in KIND_RULES["governed"]:
            if key not in registry:
                errors.append(f"السجلّ نفسه بلا «{key}» — حارس بلا تحكيم")
        if registry.get("schema") != SCHEMA:
            errors.append(f"schema السجلّ = {registry.get('schema')!r} ≠ {SCHEMA!r}")
        entries_raw = registry.get("entries", [])
        if not isinstance(entries_raw, list) or any(
            not isinstance(e, dict)
            or not isinstance(e.get("path"), str)
            or e.get("kind") not in KIND_RULES
            for e in entries_raw
        ):
            errors.append("entries في السجلّ ليست قائمة من {path, kind} بصنف معروف")
            registered = {}
        else:
            registered = {e["path"]: e["kind"] for e in entries_raw}
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
    # بلا أعلام عمداً (انظر الترويسة): التشغيل العاري = توليد ثم تحقّق.
    return check(fix=True)


if __name__ == "__main__":
    sys.exit(main())
