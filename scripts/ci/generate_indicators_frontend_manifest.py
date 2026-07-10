#!/usr/bin/env python3
"""مولّد مانيفست الواجهة (build-time) لسجلّ المؤشّرات — WS-B.2 (manifest-only).

المصدر الأوحد `config/indicators_registry.json` (WS-B.1) لا يُشحَن في الحاويات ولا
يُقرأ وقت التشغيل، وسقف مسارات المنصّة (p2_6=575) يمنع نقطة runtime جديدة. لذا نُولّد
منه **مانيفست TypeScript مُلتزَماً** يُدمَج وقت البناء — فتقود الواجهة كتالوج المؤشّرات
حتميّاً من مصدر واحد بلا نقطة runtime ولا اعتماد config.

الإسقاط عموميّ (حقول العرض فقط: id/name/unit/range/renderable/availability/source_class)
+ REGISTRY_VERSION/DIGEST كعلامة نضارة مبنيّة وقت البناء.

الاستعمال: `python scripts/ci/generate_indicators_frontend_manifest.py [--check]`
`--check` يُفشِل (exit 1) عند انحراف المانيفست المُلتزَم عن المصدر (بوّابة مزامنة CI).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "config" / "indicators_registry.json"
_OUT = _ROOT / "frontend" / "src" / "lib" / "indicatorsRegistry.generated.ts"

_PUBLIC_FIELDS = ("id", "name_ar", "name_en", "category", "unit", "range", "renderable")


def _project(indicators: list[dict]) -> list[dict]:
    out = []
    for e in indicators:
        row = {k: e.get(k) for k in _PUBLIC_FIELDS}
        row["source_class"] = e.get("source")
        status = e.get("status")
        row["availability"] = (
            "active"
            if status == "implemented"
            else ("estimated" if status == "estimated" else "unavailable")
        )
        out.append(row)
    return out


def build() -> tuple[str, str, list[dict]]:
    data = json.loads(_SRC.read_text(encoding="utf-8"))
    public = _project(data["indicators"])
    canonical = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest, digest[7:19], public


def render() -> str:
    digest, version, public = build()
    # ليترالات JSON صالحة كـTS (true/false/null مطابقة) — إسقاط عموميّ فقط.
    body = json.dumps(public, ensure_ascii=False, indent=2)
    return (
        "// AUTO-GENERATED from config/indicators_registry.json — do not edit by hand.\n"
        "// Regenerate: python scripts/ci/generate_indicators_frontend_manifest.py\n"
        "// Sync guard (--check) blocks drift from the canonical single source (WS-B.2).\n\n"
        "export type IndicatorAvailability = 'active' | 'estimated' | 'unavailable';\n"
        "export type IndicatorSourceClass = 'real' | 'estimated' | 'derived' | null;\n\n"
        "export interface RegistryIndicator {\n"
        "  id: string;\n"
        "  name_ar: string | null;\n"
        "  name_en: string | null;\n"
        "  category: string | null;\n"
        "  unit: string | null;\n"
        "  range: [number, number] | null;\n"
        "  renderable: boolean | null;\n"
        "  source_class: IndicatorSourceClass;\n"
        "  availability: IndicatorAvailability;\n"
        "}\n\n"
        f"export const REGISTRY_VERSION = '{version}';\n"
        f"export const REGISTRY_DIGEST = '{digest}';\n\n"
        f"export const INDICATORS_MANIFEST: RegistryIndicator[] = {body};\n"
    )


def main() -> int:
    check = "--check" in sys.argv[1:]
    rendered = render()
    if check:
        current = _OUT.read_text(encoding="utf-8") if _OUT.exists() else ""
        if current != rendered:
            print(
                "indicatorsRegistry.generated.ts drift — run "
                "scripts/ci/generate_indicators_frontend_manifest.py",
                file=sys.stderr,
            )
            return 1
        print("indicators_frontend_manifest_in_sync")
        return 0
    _OUT.write_text(rendered, encoding="utf-8")
    print(f"generated {_OUT.relative_to(_ROOT)} ({len(build()[2])} indicators)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
