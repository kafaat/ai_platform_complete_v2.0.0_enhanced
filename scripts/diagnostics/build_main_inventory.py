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
import json
import subprocess
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


def _ownership_engine():
    """محرّكُ ملكيّة الكتابة **نفسُه** الذي يحجب في CI — لا نسخةٌ ثانية منه.

    السؤالُ («أيُّ مكوّنٍ يملك الكتابة، وبأيّ عقدٍ معلَن؟») له مُجيبٌ قائمٌ في الشجرة:
    `db_writer_ownership_guard`. وكتابةُ ماسحٍ ثانٍ هنا كانت ستُنتِج نمطَ كتابةٍ ثانياً
    وقواعدَ استثناءٍ ثانية، فيختلف الجوابان عن سؤالٍ واحد **بلا ما يُظهِر الاختلاف**.
    """
    import importlib.util

    path = ROOT / "scripts" / "ci" / "db_writer_ownership_guard.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_dbw_guard_for_inventory", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


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


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    components = load_components()
    capabilities = load_capabilities()
    units = deployment_units(components)
    resolved, unresolved = integration_edges(capabilities)

    _write(out / "components.json", components)
    _write(out / "deployment_units.json", units)
    _write(out / "capabilities.json", capabilities)
    _write(out / "integration_edges.json", resolved)
    _write(out / "unresolved_edges.json", unresolved)
    surfaces = placeholders()
    # الترقيةُ **مشروطةٌ بإنتاج الصفوف**: على شجرةٍ بلا عقدٍ أو بلا محرّك يُرجِع
    # القياسُ `None` فيبقى السطحُ `not_measured` بسؤاله ومرشّحاته. وهذا ليس احتياطاً:
    # هو ما يجعل «الترقيةُ بالقياس لا بالتحرير» خاصّيّةً تُختبَر لا جملةً تُقال.
    ownership = database_ownership()
    if ownership is not None:
        surfaces["database_ownership.json"] = ownership
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
            # يُعلَن في الترويسة كي لا يحتاج القارئ أن يفتح عشرة ملفّات ليكتشف
            # أنّ عشرة أسطحٍ لم تُقَس. عددٌ في الترويسة أصعبُ على الإغفال من صمت.
            "surfaces_not_measured": sum(
                1 for s in surfaces.values() if s["measurement_state"] == "not_measured"
            ),
            "surfaces_declared": len(surfaces),
        },
        "sources": [
            {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for path in sources
        ],
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
