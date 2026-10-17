#!/usr/bin/env python3
"""ملفُّ Compose واحدٌ يُعرّف المكدّس — `COMPOSE-ALTERNATES-UNGUARDED-AND-NAME-INCOMPATIBLE-01`.

كان في الجذر أربعةَ عشرَ ملفّ compose غير ``docker-compose.v9.yml``، بعضُها يُعرّف
المكدّسَ نفسَه بأسماء خدماتٍ أخرى (``auth-service`` مقابل ``sahool-auth``)، فأيُّ
``depends_on`` أو upstream كُتِب لأحدها لا يعمل مع الآخر، وأربعةٌ منها لا يذكرها أيُّ
workflow. وقرارُ المالك (2026-10-15): v9 وحدَه تعريفُ المكدّس، والبدائلُ إلى
``docs/history/compose/``.

وما بقي ليس بديلاً بل **دورٌ مُعلَن** في ``docs/architecture/compose_file_roster.json``:

* ``overlay`` — يُطبَّق فوق v9؛ كلُّ خدمةٍ فيه موجودةٌ في v9 أو تحمل image/build، وكلُّ
  ``depends_on`` يُحلّ في الاتّحاد. **مقيسٌ لا نظريّ:** ``docker-compose.production.yml``
  سمّى ``vegetation-analysis-service`` و``sahool-raster`` — اسمين لا وجود لهما في v9 —
  فكان ``docker compose -f v9 -f production config`` يرفض المشروع والأمرُ الإنتاجيّ
  القانونيّ لا يُقلِع، وCI تتخطّاه بوصفه «تراكباً».
* ``test_stack`` — مكدّسٌ زائل لا يُعيد استعمال اسم خدمةٍ من v9.
* ``companion`` — مكدّسٌ بجوار v9 ينضمّ إلى شبكةٍ منه، ولا يُعيد اسم خدمةٍ منه.

والسطحُ **أوسعُ** من ``compose_surface.py`` عمداً: كلُّ ملفٍّ متعقَّب في git يطابق
``(docker-)compose*.y(a)ml`` في **أيّ** دليل عدا ``docs/history/compose/`` — فملفٌّ في
``services/x/compose.yaml`` تعريفٌ ثانٍ كذلك، وسطحٌ يرى الجذرَ وحدَه يتركه. والحكمُ **مساواةُ مجموعات**:
ملفٌّ جديد خارج السجلّ يحجب، ومدخلٌ في السجلّ بلا ملفّ يحجب. ولكلّ مدخلٍ مستهلِكٌ
موجودٌ يُسمّيه — ملفٌّ لا يُشغّله أحدٌ هو البديلُ الصامت الذي أُغلِقت الفجوةُ لأجله.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compose_surface import ROOT  # noqa: E402

ROSTER = ROOT / "docs" / "architecture" / "compose_file_roster.json"
ROLES = {"overlay", "test_stack", "companion"}
UNIVERSE_SOURCE = "git ls-files | (docker-)compose*.y(a)ml في أيّ دليل، عدا history_dir"
_COMPOSE_NAME = re.compile(r"(?:^|/)(?:docker-)?compose[^/]*\.ya?ml$")


def tracked_compose_files(history_dir: str) -> list[str]:
    """المتعقَّب في git لا ما يصادف وجوده على القرص — ملفٌّ غير متعقَّب لا يبلغ CI."""
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=True
    ).stdout
    prefix = history_dir.rstrip("/") + "/"
    return sorted(
        line
        for line in out.splitlines()
        if _COMPOSE_NAME.search(line) and not line.startswith(prefix)
    )


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _services(doc: dict) -> dict:
    return {k: (v or {}) for k, v in (doc.get("services") or {}).items()}


def _depends(service: dict) -> list[str]:
    deps = service.get("depends_on") or []
    return list(deps) if isinstance(deps, list | dict) else []


def _joins_base_network(doc: dict, base_networks: set[str]) -> bool:
    """شبكةٌ external تُسمّي شبكةً من الأساس (بمفتاحها أو بـ``<project>_<key>``)."""
    for key, spec in (doc.get("networks") or {}).items():
        spec = spec or {}
        if not spec.get("external"):
            continue
        name = str(spec.get("name") or key)
        if any(name == net or name.endswith((f"_{net}", f"-{net}")) for net in base_networks):
            return True
    return False


def audit(
    root: Path | None = None,
    *,
    tracked: list[str] | None = None,
    roster: dict | None = None,
) -> list[str]:
    root = ROOT if root is None else root
    roster = roster if roster is not None else json.loads(ROSTER.read_text(encoding="utf-8"))
    if tracked is None:
        tracked = tracked_compose_files(roster["history_dir"])
    base_rel = roster["base"]
    entries: dict[str, dict] = roster.get("files") or {}
    problems: list[str] = []

    declared = {base_rel, *entries}
    on_disk = set(tracked)
    for rel in sorted(on_disk - declared):
        problems.append(
            f"{rel}: ملفّ compose متعقَّب خارج السجلّ — v9 وحدَه يُعرّف المكدّس؛ أعلِن دوره في "
            f"{ROSTER.relative_to(ROOT).as_posix()} أو انقله إلى {roster.get('history_dir')}/"
        )
    for rel in sorted(declared - on_disk):
        problems.append(f"{rel}: مُسجَّلٌ ولا ملفَّ متعقَّب بهذا الاسم — سجلٌّ بائت")

    base_path = root / base_rel
    if not base_path.is_file():
        return [*problems, f"{base_rel}: الأساسُ غائب — لا شيء يُقاس عليه"]
    base = _load(base_path)
    base_services = set(_services(base))
    base_networks = set(base.get("networks") or {})

    for rel, entry in sorted(entries.items()):
        role = entry.get("role")
        if role not in ROLES:
            problems.append(f"{rel}: دورٌ غير معروف {role!r} — المسموح {sorted(ROLES)}")
            continue
        consumers = entry.get("consumers") or []
        if not consumers:
            problems.append(f"{rel}: بلا مستهلِك — ملفٌّ لا يُشغّله أحدٌ بديلٌ صامت")
        name = Path(rel).name
        for consumer in consumers:
            path = root / consumer
            if not path.is_file():
                problems.append(f"{rel}: المستهلِك {consumer} غير موجود")
            elif name not in path.read_text(encoding="utf-8", errors="replace"):
                problems.append(f"{rel}: المستهلِك {consumer} لا يُسمّي {name}")
        path = root / rel
        if not path.is_file():
            continue
        doc = _load(path)
        services = _services(doc)
        if role == "overlay":
            union = base_services | set(services)
            for svc, spec in sorted(services.items()):
                if svc not in base_services and "image" not in spec and "build" not in spec:
                    problems.append(
                        f"{rel} :: {svc} — ليست في {base_rel} ولا تحمل image/build؛ التراكبُ "
                        "يُسمّي خدمةً لا وجود لها فيرفض compose المشروعَ كلّه"
                    )
                for dep in _depends(spec):
                    if dep not in union:
                        problems.append(f"{rel} :: {svc} — depends_on {dep} لا يُحلّ في الاتّحاد")
            continue
        for svc in sorted(set(services) & base_services):
            problems.append(f"{rel} :: {svc} — {role} يُعيد اسمَ خدمةٍ من {base_rel}: تعريفٌ ثانٍ لها")
        if role == "companion" and not _joins_base_network(doc, base_networks):
            problems.append(
                f"{rel}: رفيقٌ لا ينضمّ إلى شبكةٍ من {base_rel} ({sorted(base_networks)}) — "
                "لا يصله المكدّس ولا يصل إليه"
            )
    return problems


def main() -> int:
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    tracked = tracked_compose_files(roster["history_dir"])
    problems = audit(tracked=tracked, roster=roster)
    if problems:
        print("compose_roster_guard: FAIL")
        for line in problems:
            print(f"  ✗ {line}")
        return 1
    print(
        f"compose_roster_guard: PASS ({len(tracked)} ملفّاً متعقَّباً == الأساس + "
        f"{len(roster['files'])} مُسجَّلاً · المصدر: {UNIVERSE_SOURCE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
