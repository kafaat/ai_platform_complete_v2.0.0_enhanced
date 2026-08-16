#!/usr/bin/env python3
"""يجعل الإسقاط التوافقيّ صادقاً: الحقول canonical-owned تُكتَب من مالكها وحده.

A′-4b — تقارب الكتّاب. سياسة سلطة الحقول تقول إنّ ستّة حقول يملكها التعريف
القانونيّ (Registry v1) وإنّ دور السجلّ القديم إسقاطُ توافقٍ — لكنّ قيم الإسقاط
كانت تُكتَب تاريخيّاً بيد كتّابٍ آخرين (الرابط يشتقّ owner من شكل المستودع مثلاً)
فبقيت بائتة. هذا المُسقِط هو **الكاتب الوحيد** المخوَّل لتلك الحقول في الإسقاط:

* يقرأ التعريف القانونيّ والسياسة، ويرفض هويّةً مختلفة بين السجلّين (لا ضمّ
  بالتقاطع)، ويرفض حقلاً canonical غائباً أو منقوطاً (يحتاج دامجاً صريحاً).
* ``--generate`` يكتب الحقول الستّة في الإسقاط من قيمها القانونيّة — **اشتقاقٌ
  آليّ لا تحرير يدويّ**: تغيّرت القيمة القانونيّة تغيّر الإسقاط، ولا طريق آخر.
* ``--check`` يفشل مغلقاً على أيّ انحراف، مسمّياً كلّ هويّة ``CID:field`` —
  فيستحيل أن يعود حقلٌ canonical في الإسقاط بائتاً بصمت.

**حدُّ صدقه:** لا يمسّ إلا الحقول التي تملكها السلطة القانونيّة نصّاً في
السياسة؛ الحقول المتحوّلة (runtime/certification) وحقول إسقاط المستودع تبقى
لكتّابها المخوَّلين. وليس سجلّاً ثالثاً: يكتب **في** الإسقاط **من** القانونيّ.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
CANONICAL = ROOT / "docs/capability-registry/generated/capability_registry.json"
LEGACY = ROOT / "capabilities/registry/capabilities.json"
POLICY_SCHEMA = "sahool.capability-field-authority/v1"
CANONICAL_AUTHORITY = "canonical_capability_definition"


class ProjectionSyncError(RuntimeError):
    """الإسقاط لا يُزامَن على عقدٍ ناقص أو هويّةٍ ملتبسة."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectionSyncError(f"cannot read projection input: {path}") from exc
    if not isinstance(value, dict):
        raise ProjectionSyncError(f"projection input is not an object: {path}")
    return value


def _rows(document: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = document.get("capabilities")
    if not isinstance(rows, list):
        raise ProjectionSyncError(f"{label} registry has no capabilities list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ProjectionSyncError(f"{label} registry contains a malformed row")
        if row["id"] in result:
            raise ProjectionSyncError(f"{label} registry duplicates capability id: {row['id']}")
        result[row["id"]] = row
    return result


def canonical_owned_fields(policy: dict[str, Any]) -> list[str]:
    if policy.get("schema") != POLICY_SCHEMA:
        raise ProjectionSyncError("field authority policy schema mismatch")
    reconciliation = policy.get("reconciliation")
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get("no_third_value_registry") is not True
    ):
        raise ProjectionSyncError("field authority policy must forbid a third value registry")
    field_authority = policy.get("field_authority")
    if not isinstance(field_authority, dict):
        raise ProjectionSyncError("field authority policy has no field_authority map")
    fields = sorted(
        field
        for field, spec in field_authority.items()
        if isinstance(spec, dict) and spec.get("authority") == CANONICAL_AUTHORITY
    )
    if not fields:
        raise ProjectionSyncError("policy grants no fields to the canonical definition")
    for field in fields:
        if "." in field:
            raise ProjectionSyncError(f"nested canonical field requires explicit merger: {field}")
    return fields


def drift(root: Path = ROOT) -> tuple[list[str], dict[str, Any], list[str]]:
    """``(هويّات الانحراف CID:field، وثيقة الإسقاط بعد المزامنة، الحقول القانونيّة)``."""
    policy = _load(root / POLICY.relative_to(ROOT))
    fields = canonical_owned_fields(policy)
    canonical = _rows(_load(root / CANONICAL.relative_to(ROOT)), "canonical")
    legacy_doc = _load(root / LEGACY.relative_to(ROOT))
    legacy = _rows(legacy_doc, "legacy")
    if set(canonical) != set(legacy):
        only_c = sorted(set(canonical) - set(legacy))
        only_l = sorted(set(legacy) - set(canonical))
        raise ProjectionSyncError(
            f"capability identity sets disagree: canonical_only={only_c} legacy_only={only_l}"
        )
    identities: list[str] = []
    synced = copy.deepcopy(legacy_doc)
    synced_rows = {row["id"]: row for row in synced["capabilities"]}
    for cid in sorted(canonical):
        source = canonical[cid]
        target = synced_rows[cid]
        for field in fields:
            if field not in source:
                raise ProjectionSyncError(f"canonical capability {cid} lacks owned field: {field}")
            if target.get(field) != source[field]:
                identities.append(f"{cid}:{field}")
                target[field] = copy.deepcopy(source[field])
    return sorted(identities), synced, fields


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="مزامنة الحقول canonical-owned في الإسقاط التوافقيّ")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--generate", action="store_true")
    args = ap.parse_args(argv)
    identities, synced, fields = drift()
    if args.check:
        if identities:
            print("capability_projection_sync: DRIFT — حقول canonical بائتة في الإسقاط:")
            for identity in identities:
                print(f"  {identity}")
            print("شغّل --generate: الإسقاط يُكتَب من مالكه لا يُحرَّر بيد.")
            return 1
        print(
            f"capability_projection_sync_ok fields={len(fields)} "
            f"capabilities={len(synced['capabilities'])} drift=0"
        )
        return 0
    LEGACY.write_text(json.dumps(synced, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"capability_projection_sync: projected {len(identities)} identities "
        + (f"({', '.join(identities)})" if identities else "(already converged)")
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
