#!/usr/bin/env python3
"""Build a descriptive inventory baseline before diagnostic probes.

This program deliberately emits no verdict, score, threshold, or recommended fix.
It normalizes existing repository evidence into machine-readable inventory artifacts.
Unknown relationships stay unresolved instead of being inferred as absent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "artifacts" / "diagnostics" / "inventory"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    # `text=True` بلا `encoding` يفكّ الخرجَ بترميز الآلة، فيموت تحت `LC_ALL=C` — وهو
    # الصنفُ المُسجَّل `GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01`، ويفرضه
    # `tests_v9/test_text_encoding_locale.py` على كلّ ملفٍّ جديد. وSHA هنا ASCII خالص،
    # لكنّ العقد على **الشكل** لا على ما يصادف أن يمرّ: مدخلٌ بلا ترميزٍ صريح يدخل
    # الأساسَ ثمّ يُنسخ إلى موضعٍ يقرأ عربيّةً.
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _split_pipe(value: str) -> list[str]:
    return [item for item in value.split("|") if item]


def _tri(value: str) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def load_components() -> list[dict[str, Any]]:
    path = ROOT / "component_inventory.generated.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        result.append(
            {
                "component_id": row["component_id"],
                "component_kind": row["component_kind"],
                "domain": row["domain"],
                "authority_kind": row["authority_kind"],
                "source_path": row["source_path"],
                "deployment_units": _split_pipe(row["deployment_units"]),
                "aliases": _split_pipe(row["aliases"]),
                "compose_services": _split_pipe(row["compose_services"]),
                "tables_owned_declared": int(row["tables_owned"] or 0),
                "wired_static": _tri(row["wired"]),
                "tested_static": _tri(row["tested"]),
                "evidence_state": "declared",
            }
        )
    return sorted(result, key=lambda item: item["component_id"])


def load_capabilities() -> list[dict[str, Any]]:
    catalog = _json(ROOT / "platform_catalog.generated.json")
    result = []
    for cap in catalog.get("capabilities", []):
        result.append(
            {
                "capability_id": cap.get("capability_id"),
                "owner": cap.get("owner"),
                "producer": cap.get("producer"),
                "consumers_declared": sorted(cap.get("consumers") or []),
                "entrypoints": sorted(cap.get("entrypoints") or []),
                "kind": cap.get("kind"),
                "approval_required": cap.get("approval_required"),
                "idempotency_required": cap.get("idempotency_required"),
                "derived_from": cap.get("derived_from"),
                "evidence_state": "declared",
            }
        )
    return sorted(result, key=lambda item: item["capability_id"] or "")


def deployment_units(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for component in components:
        for unit in component["deployment_units"]:
            rows.append(
                {
                    "deployment_unit": unit,
                    "component_id": component["component_id"],
                    "domain": component["domain"],
                    "compose_declared": unit in component["compose_services"],
                    "evidence_state": "declared",
                }
            )
    return sorted(rows, key=lambda item: (item["deployment_unit"], item["component_id"]))


def integration_edges(
    capabilities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for cap in capabilities:
        producer = cap["producer"]
        for consumer in cap["consumers_declared"]:
            # The catalogue is a declaration. A real caller is required before this edge
            # may become `resolved`; absence of one is not called no-consumer here.
            unresolved.append(
                {
                    "edge_kind": "capability-consumer",
                    "from": producer,
                    "to": consumer,
                    "capability_id": cap["capability_id"],
                    "entrypoints": cap["entrypoints"],
                    "evidence_state": "declared",
                    "question_to_ask": "Which concrete source call-site or runtime trace proves this consumer edge?",
                }
            )
    return resolved, sorted(unresolved, key=lambda item: (item["capability_id"] or "", item["to"]))


def _load_engine(path: Path, alias: str):
    """يُحمَّل محرّكٌ حاجبٌ بالمسار — **وغيابُه غيرُ عطبِه، والفرقُ يُرى**.

    `AN-ENGINE-THAT-FAILS-TO-LOAD-IS-REPORTED-AS-AN-ABSENT-MEASURE-01` — مقيسٌ أثناء
    بناء سطح المسارات: أوّلُ صياغةٍ لي ابتلعت خطأَ التحميل بـ`except Exception: return
    None`، فأبلغ الجردُ `not_measured` **وكأنّه امتناعٌ صادقٌ عن القياس** بينما المحرّكُ
    قائمٌ في الشجرة ويحجب في CI. وذاك صنفُ «الغيابُ يُقرأ قياساً» بعينه، مقلوباً: عطبٌ
    يلبس ثوبَ الصدق.

    والعطلُ الذي كشفه ليس فرضيّاً: `@dataclass` يقرأ `sys.modules[cls.__module__]`، فإن
    لم تُسجَّل الوحدةُ **قبل** التنفيذ سقط التحميلُ بـ`AttributeError` — أي أنّ كلَّ
    محرّكٍ يحمل dataclass كان سيُبلَّغ «غيرَ موجود».

    فالقاعدةُ هنا: ملفٌّ غيرُ موجود ⇒ `None` (السطحُ لم يُقَس بصدق)؛ وملفٌّ موجودٌ لا
    يُحمَّل ⇒ **فشلٌ صريح**، لأنّ شجرةً تحمل المحرّكَ ولا تستطيع تشغيله عطلٌ يُصلَح لا
    قياسٌ يُمتنَع عنه.
    """
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"ENGINE_UNLOADABLE: تعذّر بناء مواصفة تحميلٍ لـ{path}")
    module = importlib.util.module_from_spec(spec)
    # التسجيلُ **قبل** التنفيذ: `dataclasses._is_type` يبحث عن الوحدة في `sys.modules`.
    sys.modules[alias] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - يفشل صراحةً بدل أن يُبلِغ غياباً
        sys.modules.pop(alias, None)
        raise SystemExit(
            f"ENGINE_UNLOADABLE: {path} موجودٌ ولم يُحمَّل ({exc.__class__.__name__}: {exc}). "
            "شجرةٌ تحمل المحرّكَ ولا تُشغّله عطلٌ يُصلَح — ولا يُبلَّغ عنه «لم يُقَس»."
        ) from exc
    return module


def _ownership_engine():
    """محرّكُ ملكيّة الكتابة **نفسُه** الذي يحجب في CI — لا نسخةٌ ثانية منه.

    السؤالُ («أيُّ مكوّنٍ يملك الكتابة، وبأيّ عقدٍ معلَن؟») له مُجيبٌ قائمٌ في الشجرة:
    `db_writer_ownership_guard`. وكتابةُ ماسحٍ ثانٍ هنا كانت ستُنتِج نمطَ كتابةٍ ثانياً
    وقواعدَ استثناءٍ ثانية، فيختلف الجوابان عن سؤالٍ واحد **بلا ما يُظهِر الاختلاف**.

    ويمرّ بـ`_load_engine` لأنّ ابتلاعَ خطأ التحميل هنا كان سيُبلِّغ «لم يُقَس» عن
    محرّكٍ **قائمٍ يحجب في CI** — والعطلُ قِيس على محرّكٍ آخر، لا يُفترَض.
    """
    path = ROOT / "scripts" / "ci" / "db_writer_ownership_guard.py"
    return _load_engine(path, "_dbw_guard_for_inventory")


#: ما لا يراه الماسح — يُحمَل **في المصنوعة** لا في تعليقٍ بجانبها.
#:
#: هذا هو الدرسُ الذي وُجِد هذا السطحُ لأجله بعينه: النيّةُ في تعليقٍ فوق الدالّة
#: والقارئُ الآليُّ لا يقرأ التعليقات. فحدُّ الأداة يجب أن يكون حقلاً يُقرأ، وإلّا
#: قُرئ `declared` (بلا موضعٍ مقيس) نفياً لوجود كاتب — وهو أخطرُ من `[]` العارية،
#: لأنّه يحمل هيئةَ القياس.
_OWNERSHIP_BLIND_SPOTS = [
    "حرفيّاتُ SQL في ملفّات بايثون وحدَها تُمسَح: لا `.sql` ولا ترحيلات.",
    "لا ORM ولا استعلامٌ يُركَّب في وقت التشغيل من أجزاء.",
    "دليلا الاختبارات مستثنيان، فكاتبٌ لا يظهر إلّا فيهما لا يُرى.",
    "ولذلك: `evidence_state=declared` تعني «لم يُعثَر على موضع» لا «لا كاتب».",
]


def database_ownership() -> dict[str, Any]:
    """سطحُ ملكيّة الكتابة — مقيسٌ بطبقتَي دليلٍ لا بطبقةٍ واحدة.

    **والفرقُ بين الطبقتين هو كلُّ الفائدة:** العقدُ سجلٌّ في المستودع، فهو دليلٌ
    `declared`. وموضعُ الكتابة في المصدر دليلٌ `resolved`. ودمجُهما في رقمٍ واحد
    كان سيُنتِج «٣٩١ حافّةَ ملكيّة» تُقرأ محقَّقةً وهي في أكثرها غيرُ مسنَدة.

    فالصفوفُ تحمل الحالتين صراحةً، وتُضاف إليها حالةُ العقد (`authorised` ·
    `not_authorised` · `outside_contract`) — فالكتابةُ المقيسةُ التي لم يأذن بها
    العقدُ حافّةٌ حقيقيّةٌ أيضاً، وإخفاؤها يجعل السطحَ يصف عقداً لا شجرة.
    """
    guard = _ownership_engine()
    contract_path = ROOT / "docs" / "architecture" / "db_ownership.yml"
    if guard is None or not contract_path.exists():
        # شجرةٌ بلا عقدٍ أو بلا محرّك: يبقى السطحُ غيرَ مقيس. الترقيةُ بالقياس لا
        # بالتحرير — ولو أُرجِعت هنا صفوفٌ فارغةٌ بحالة `measured` لكان ذلك ادّعاءً.
        return None

    try:
        contract = guard.load_contract()
        measured = guard.write_sites(ROOT)
    except SystemExit:
        # `load_contract` تفشل صراحةً على عقدٍ غيرِ مقروء بدل أن تُبلِغ صفراً كاذباً.
        return None

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for key, sites in measured.items():
        table, component = key.split("::", 1)
        meta = contract.get(table)
        if not isinstance(meta, dict):
            state = "outside_contract"
        elif guard._write_allowed(table, component, contract):
            state = "authorised"
        else:
            state = "not_authorised"
        seen.add((table, component))
        rows.append(
            {
                "table": table,
                "component": component,
                "relation": "writer",
                "evidence_state": "resolved",
                "contract_state": state,
                "sites": sites,
                "declared_source": (meta or {}).get("source") if isinstance(meta, dict) else None,
            }
        )

    for table, meta in contract.items():
        if not isinstance(meta, dict):
            continue
        for component in meta.get("writers") or []:
            if (table, component) in seen:
                continue
            rows.append(
                {
                    "table": table,
                    "component": component,
                    "relation": "writer",
                    "evidence_state": "declared",
                    "contract_state": "authorised",
                    "sites": [],
                    "declared_source": meta.get("source"),
                }
            )

    rows.sort(key=lambda r: (r["table"], r["component"], r["evidence_state"]))
    by_evidence = {"resolved": 0, "declared": 0}
    by_contract = {"authorised": 0, "not_authorised": 0, "outside_contract": 0}
    for row in rows:
        by_evidence[row["evidence_state"]] += 1
        by_contract[row["contract_state"]] += 1

    return {
        "schema": "sahool.diagnostic-inventory.surface.v1",
        "surface": "database_ownership.json",
        "measurement_state": "measured",
        "rows": rows,
        "row_count": len(rows),
        "counts": {
            "tables_in_contract": len(contract),
            "by_evidence_state": by_evidence,
            "by_contract_state": by_contract,
        },
        "engine": "scripts/ci/db_writer_ownership_guard.py",
        "contract": "docs/architecture/db_ownership.yml",
        "blind_spots_ar": _OWNERSHIP_BLIND_SPOTS,
        "what_this_does_not_claim_ar": (
            "لا يُدَّعى أنّ العقدَ صحيح، ولا أنّ حافّةً `declared` بلا كاتب. المقيسُ "
            "موضعُ كتابةٍ وُجِد أو لم يُوجَد بماسحٍ حدودُه مُعلَنةٌ أعلاه؛ و"
            "`not_authorised` تعني كتابةً مقيسةً لم يأذن بها العقد — لا حكماً بأنّها خطأ."
        ),
    }


def _route_engine():
    """محرّكُ تصنيف المسارات **نفسُه** الذي يحجب في `platform-route-budget`.

    نفسُ حجّة `_ownership_engine`: السؤالُ («أيُّ مسارٍ يُعلَن أين، وهل هو نطاقٌ أم
    بنية؟») له مُجيبٌ حاجبٌ في الشجرة. وماسحٌ ثانٍ هنا كان سيحمل قائمةَ بنيةٍ ثانية
    وتطبيعَ مسارٍ ثانياً — فينحرف جوابان عن سؤالٍ واحد بلا ما يُظهِر الانحراف، وأحدُهما
    هو الذي تُقاس عليه الميزانيّة.
    """
    path = ROOT / "scripts" / "ci" / "platform_route_classification.py"
    return _load_engine(path, "_route_classification_for_inventory")


#: حدودُ قياس المسارات — حقلٌ يُقرأ في المصنوعة لا تعليقٌ بجانبها.
_ROUTE_BLIND_SPOTS = [
    "شجرةُ `services/sahool-platform` وحدَها تُمسَح: مسارُ خدمةٍ أخرى لا يظهر هنا.",
    "المسارُ هو **حرفيّةُ المُزخرِف** لا المسارَ المُركَّب: بادئاتُ `include_router` "
    "غيرُ محلولة، فمفتاحٌ يتكرّر عبر وحدتين ليس بالضرورة تصادماً "
    "(`route_conflict_guard` يحكم ذلك).",
    "إعلانٌ غيرُ حرفيٍّ يفشل مُغلَقاً في المحرّك، فلا يُعَدّ ولا يُبتلَع صامتاً.",
    "دليلُ `tests/` مستثنًى.",
    "و`target_owner` **دليلٌ مُعلَن** من خريطة الاستخراج — نيّةُ بنيةٍ لا موضعَ تشغيل.",
]


def routes_surface() -> dict[str, Any] | None:
    """سطحُ المسارات — الإعلانُ مقيس، والملكيّةُ مُعلَنة، والتصنيفُ من المحرّك الحاجب.

    **وطبقتا الدليل هنا مختلفتان عن بعضهما عمداً:** موضعُ الإعلان `resolved` (ملفٌّ
    وسطرٌ قاسهما المحرّك)، وأمّا المالكُ فـ`declared` — سجلٌّ في `platform_extraction_map.json`
    يصف **البنيةَ المقصودة** لا موضعَ تشغيلٍ قائماً. ودمجُهما كان سيُنتِج «٦٣٢ مساراً
    مملوكاً» تُقرأ محقَّقةً، والمقيسُ منها موضعُ الإعلان وحدَه.
    """
    engine = _route_engine()
    platform_root = ROOT / "services" / "sahool-platform"
    extraction_path = ROOT / "docs" / "architecture" / "platform_extraction_map.json"
    placement_path = ROOT / "docs" / "architecture" / "platform_route_placement_contract.json"
    if engine is None or not platform_root.exists() or not extraction_path.exists():
        # الترقيةُ بالقياس لا بالتحرير: بلا محرّكٍ أو بلا خريطةٍ يبقى السطحُ غيرَ مقيس.
        return None

    try:
        declarations = engine.collect_platform_routes(platform_root)
    except Exception:
        return None
    if not declarations:
        # صفرُ مسارٍ على شجرةٍ تحمل راوترات = ماسحٌ فشل، لا شجرةٌ خالية. ولا يُبلَّغ
        # `measured` بصفوفٍ فارغة — تلك دعوى.
        return None

    infrastructure, domain = engine.partition_routes(declarations)

    # نفسُ قاعدة `_load_engine`: الغيابُ حُسِم أعلاه بـ`return None`؛ وأمّا خريطةٌ
    # **موجودةٌ لا تُقرأ** فعطبٌ يفشل صراحةً. وابتلاعُها هنا بـ`return None` كان
    # يُنتِج `not_measured` بهيئة امتناعٍ صادق — وهو ما أبقى الطفرةَ [٣] حيّةً في
    # أوّل زرع: الشرطُ فوق كان يبدو حارساً، والحارسُ الفعليُّ هذا الابتلاع.
    owners: dict[tuple[str, str], str] = {}
    try:
        mapped = json.loads(extraction_path.read_text(encoding="utf-8")).get("routes") or []
    except Exception as exc:
        raise SystemExit(
            f"EXTRACTION_MAP_UNREADABLE: {extraction_path} موجودةٌ ولم تُقرأ "
            f"({exc.__class__.__name__}: {exc}) — ولا يُبلَّغ عنها «لم يُقَس»."
        ) from exc
    for row in mapped:
        if not isinstance(row, dict):
            continue
        method, path, owner = row.get("method"), row.get("path"), row.get("target_owner")
        if method and path and owner:
            owners[(str(method).strip().upper(), str(path))] = owner

    placement: dict[tuple[str, str], dict[str, Any]] = {}
    if placement_path.exists():
        try:
            for row in json.loads(placement_path.read_text(encoding="utf-8")).get("routes") or []:
                if isinstance(row, dict) and row.get("method") and row.get("path"):
                    placement[(str(row["method"]).upper(), str(row["path"]))] = row
        except Exception:
            placement = {}

    rows: list[dict[str, Any]] = []
    for route in declarations:
        key = route.key
        contract = placement.get(key)
        declared_source = contract.get("required_source") if contract else None
        actual_source = f"services/sahool-platform/{route.source}"
        rows.append(
            {
                "method": route.method,
                "path": route.path,
                "kind": "infrastructure" if route.infrastructure else "domain",
                "evidence_state": "resolved",
                "site": f"{actual_source}:{route.line}",
                "function": route.function,
                "owner": owners.get(key),
                "owner_evidence_state": "declared" if key in owners else "unmapped",
                "placement_state": (
                    None
                    if contract is None
                    else ("at_required_source" if actual_source == declared_source else "elsewhere")
                ),
            }
        )

    rows.sort(key=lambda r: (r["path"], r["method"], r["site"]))
    unique_keys = {(r["method"], r["path"]) for r in rows}
    unmapped = [r for r in rows if r["owner_evidence_state"] == "unmapped"]
    by_owner: dict[str, int] = {}
    for row in rows:
        if row["owner"]:
            by_owner[row["owner"]] = by_owner.get(row["owner"], 0) + 1

    return {
        "schema": "sahool.diagnostic-inventory.surface.v1",
        "surface": "routes.json",
        "measurement_state": "measured",
        "rows": rows,
        "row_count": len(rows),
        "counts": {
            "declarations": len(rows),
            "unique_method_path_keys": len(unique_keys),
            "domain": len(domain),
            "infrastructure": len(infrastructure),
            "unmapped_owner": len(unmapped),
            "by_declared_owner": dict(sorted(by_owner.items())),
        },
        "engine": "scripts/ci/platform_route_classification.py",
        "contract": "docs/architecture/platform_extraction_map.json",
        "blind_spots_ar": _ROUTE_BLIND_SPOTS,
        "what_this_does_not_claim_ar": (
            "الصفُّ إعلانٌ مقيس، لا مسارٌ يُثبَت وصولُه حيّاً: لا يُدَّعى أنّه مُركَّبٌ "
            "في تطبيقٍ يعمل ولا أنّ بادئتَه هي المكتوبة هنا. و`owner` نيّةُ بنيةٍ "
            "مُعلَنة لا موضعَ تشغيل؛ و«عددُ النطاق» هنا عددُ **إعلانات** لا مفاتيحَ "
            "فريدة — والفرقُ مقيسٌ في `counts` لا مطويٌّ فيه."
        ),
    }


# ── `AN-UNMEASURED-SURFACE-SERIALISED-AS-AN-EMPTY-LIST-READS-AS-NO-RELATIONS-01` ──
#
# هذه الأسطحُ كانت تُكتب `[]` عارية. والنيّةُ كانت صادقة — «لم نقس بعد» — لكنّ الشكل
# لا يحملها: ملفٌّ محتواه `[]` يقرؤه كلُّ مستهلكٍ لاحق **«لا علاقات»**، وهو صنفُ
# «الغيابُ يُقرأ قياساً» المُسجَّلُ في هذا المستودع مراراً. والفرقُ ليس بلاغيّاً:
# `measured` + صفرُ صفوف دعوى، و`not_measured` + صفرُ صفوف امتناعٌ عن الدعوى.
#
# فصار لكلّ سطحٍ **حالةُ قياسٍ صريحة** و**سؤالٌ يجب أن يُحسَم** ومرشّحاتُ مصدرٍ
# تُوجّه القياسَ التالي. ولا يُرقّى سطحٌ إلى `measured` إلّا بمقياسٍ يُنتِج صفوفَه.
_NOT_MEASURED: dict[str, dict[str, Any]] = {
    "database_ownership.json": {
        "question": "أيُّ مكوّنٍ يملك الكتابة إلى كلّ جدول، وبأيّ عقدٍ معلَن؟",
        "candidate_sources": [
            "docs/architecture/db_ownership.yml",
            "migrations/",
            "services/*/models",
        ],
    },
    "event_topology.json": {
        "question": "أيُّ موضوعٍ يُنشَر، ومن ناشرُه، ومن مستهلكُه المُثبَت بموضع استدعاء؟",
        "candidate_sources": ["services/*/outbox", "docker-compose*.yml", "services/*/nats"],
    },
    "workers_schedulers.json": {
        "question": "أيُّ عمليّةٍ تعمل دوريّاً، وبأيّ جدولة، وما الحالةُ التي تمسّها؟",
        "candidate_sources": ["docker-compose*.yml", "services/*/worker", "k8s/cronjob"],
    },
    "external_integrations.json": {
        "question": "أيُّ خدمةٍ خارجيّة تُستدعى، من أيّ مكوّن، وبأيّ اعتمادٍ وحدود؟",
        "candidate_sources": ["services/*/clients", "config/", ".env.example"],
    },
    "frontend_consumers.json": {
        "question": "أيُّ نقطةِ واجهةٍ تستهلك أيّ مسارِ خلفيّة، مُثبَتاً من موضع النداء؟",
        "candidate_sources": ["frontend/src", "frontend/nginx.conf"],
    },
    "mobile_consumers.json": {
        "question": "أيُّ شاشةٍ في تطبيق الجوّال تستهلك أيّ مسار، وبأيّ إصدارِ عقد؟",
        "candidate_sources": ["mobile/lib", "mobile/pubspec.yaml"],
    },
    "ai_runtime_graph.json": {
        "question": "أيُّ نموذجٍ يُحمَّل أين، ومن يستدعيه، وبأيّ بصمةِ مصنوعٍ معتمدة؟",
        "candidate_sources": [
            "services/sam2-inference",
            "services/agriai-engine",
            "services/*/onnx",
        ],
    },
    "observability_surface.json": {
        "question": "أيُّ مقياسٍ/أثرٍ يُصدَّر من أيّ مكوّن، ومن يقرؤه في لوحةٍ أو إنذار؟",
        "candidate_sources": ["monitoring/", "services/*/metrics", "docs/observability"],
    },
    "test_evidence_map.json": {
        "question": "أيُّ اختبارٍ يُثبِت أيَّ علاقةٍ مُعلَنة، وبأيّ صنفِ دليل (ساكن/حيّ)؟",
        "candidate_sources": ["tests_v9/", "tests/", "services/*/tests"],
    },
    "routes.json": {
        "question": "أيُّ مسارٍ يُعلَن أين، ومن يملكه، وهل هو نطاقٌ أم بنية؟",
        "candidate_sources": [
            "services/sahool-platform/api/routers",
            "docs/architecture/platform_route_placement_contract.json",
        ],
    },
}


def placeholders() -> dict[str, dict[str, Any]]:
    """أسطحٌ **لم تُقَس**، مُصرَّحٌ بذلك في البنية لا في تعليقٍ بجانبها."""
    return {
        name: {
            "schema": "sahool.diagnostic-inventory.surface.v1",
            "surface": name,
            "measurement_state": "not_measured",
            "rows": [],
            "row_count": 0,
            "why_empty_is_not_a_finding_ar": (
                "صفرُ صفوفٍ هنا يعني «لم يُقَس»، لا «لا توجد علاقات». ولا يصير "
                "`measured` إلّا بمقياسٍ يُنتِج صفوفَه — فالترقيةُ بالقياس لا بالتحرير."
            ),
            "question_to_resolve": spec["question"],
            "candidate_sources": spec["candidate_sources"],
        }
        for name, spec in _NOT_MEASURED.items()
    }


def _resolver():
    """يُحمَّل بالمسار لا بالحزمة — `scripts/` ليست حزمةً مثبَّتة."""
    path = Path(__file__).resolve().with_name("resolve_inventory_edges.py")
    spec = importlib.util.spec_from_file_location("resolve_inventory_edges", path)
    if not spec or not spec.loader:  # pragma: no cover - يفشل مغلقاً
        raise SystemExit(f"✗ لا يمكن تحميل حاسمِ الحوافّ من {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    components = load_components()
    capabilities = load_capabilities()
    units = deployment_units(components)
    resolved, unresolved = integration_edges(capabilities)

    _write(out / "components.json", components)
    _write(out / "deployment_units.json", units)
    _write(out / "capabilities.json", capabilities)
    surfaces = placeholders()

    # حسمُ ما يُحسَم بدليلٍ مصدريّ، وإبقاءُ الباقي كما هو. الترقيةُ تحتاج سلسلةَ
    # أدلّةٍ كاملة؛ وما انقطعت سلسلتُه يبقى `declared` ولا يُقال عنه إنّه غيرُ موجود.
    promoted, unresolved, resolution = _resolver().resolve(unresolved, components, ROOT)
    resolved = promoted
    _write(out / "integration_edges.json", resolved)
    _write(out / "unresolved_edges.json", unresolved)
    # الترقيةُ **مشروطةٌ بإنتاج الصفوف**: على شجرةٍ بلا عقدٍ أو بلا محرّك يُرجِع
    # القياسُ `None` فيبقى السطحُ `not_measured` بسؤاله ومرشّحاته. وهذا ليس احتياطاً:
    # هو ما يجعل «الترقيةُ بالقياس لا بالتحرير» خاصّيّةً تُختبَر لا جملةً تُقال.
    ownership = database_ownership()
    if ownership is not None:
        surfaces["database_ownership.json"] = ownership

    # وسطحُ المسارات بالشرط نفسِه — ومن المحرّك الحاجب نفسِه الذي تُقاس عليه الميزانيّة،
    # فلا يختلف جردٌ عن بوّابةٍ في عدّ الشيء الواحد.
    route_rows = routes_surface()
    if route_rows is not None:
        surfaces["routes.json"] = route_rows

    # **سطحٌ واحدٌ خرج من «لم يُقَس» لأنّه قِيس** — لا لأنّ أحداً قرّر ذلك. صفوفُه
    # هي الحوافُّ المحسومةُ بسلسلة أدلّة، وحدُّ الماسح مُعلَنٌ معها في الصفّ نفسِه:
    # «قِيس» هنا تعني «هذا ما رآه ماسحٌ ساكن»، لا «هذا كلُّ ما يقع».
    surfaces["frontend_consumers.json"] = {
        "schema": "sahool.diagnostic-inventory.surface.v1",
        "surface": "frontend_consumers.json",
        "measurement_state": "measured",
        "rows": [
            {
                "capability_id": edge["capability_id"],
                "producer": edge["from"],
                "entrypoint": edge["resolved_entrypoint"],
                "evidence": edge["evidence"],
            }
            for edge in resolved
        ],
        "row_count": len(resolved),
        "what_measured_means_ar": (
            "كلُّ صفٍّ هنا حافّةٌ أثبتتها سلسلةُ أدلّةٍ من أربع خطوات في الشجرة "
            "(بادئةُ العميل · ربطُ النسخة · موضعُ النداء · قاعدةُ البوّابة). "
            "والصفوفُ ليست كلَّ ما يقع: ما لا يراه ماسحٌ ساكن يبقى في "
            "`unresolved_edges.json`، وحجمُ عماه في `edge_resolution.scanner_blind_spots`."
        ),
        "measured_by": "scripts/diagnostics/resolve_inventory_edges.py",
    }
    for name, value in surfaces.items():
        _write(out / name, value)

    sources = [
        ROOT / "component_inventory.generated.csv",
        ROOT / "platform_catalog.generated.json",
    ]
    manifest = {
        "schema": "sahool.diagnostic-inventory.v1",
        "source_sha": _git_sha(),
        "mode": "descriptive",
        "verdicts": False,
        "thresholds": False,
        "counts": {
            "components": len(components),
            "deployment_units": len(units),
            "capabilities": len(capabilities),
            "declared_consumer_edges_pending_resolution": len(unresolved),
            "resolved_consumer_edges": len(resolved),
            # يُعلَن في الترويسة كي لا يحتاج القارئ أن يفتح عشرة ملفّات ليكتشف
            # حالة كل سطح. العدد مشتق من القياس، ولا يفترض بقاء أي سطح غير مقيس.
            "surfaces_not_measured": sum(
                1 for s in surfaces.values() if s["measurement_state"] == "not_measured"
            ),
            "surfaces_declared": len(surfaces),
        },
        "sources": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for path in sources
        ],
        # قياسُ الحسم نفسُه يُصدَّر — بما فيه **عمى الماسح**. أخضرُ بلا إعلانِ حدوده
        # يُقرأ «كلُّ ما لم يُحسَم غيرُ موجود»، وهو ما وُجِد هذا الجردُ ليمنعه.
        "edge_resolution": resolution,
        "evidence_semantics": {
            "resolved": "supported by an independently located concrete source/runtime edge",
            "declared": "present in a repository registry/catalogue but not independently resolved",
            "unresolved": "insufficient evidence; absence is not inferred",
        },
    }
    _write(out / "inventory_manifest.json", manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    build(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
