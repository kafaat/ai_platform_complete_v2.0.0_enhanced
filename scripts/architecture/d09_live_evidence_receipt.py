#!/usr/bin/env python3
"""D09 live-evidence receipt collector — سلسلة الدليل الحيّ كاملةً في إيصالٍ واحد.

قراءةٌ صِرف. لا يكتب في Qdrant ولا يحذف ولا يُهاجِر ولا يرفع سلطة. يجمع — في
تشغيلةٍ واحدة على البيئة الحيّة — بنودَ قائمة الاعتماد كما أملاها الـrunbook:

* **M1 · M2** — جردان كاملان متتاليان عبر أداة D08 القائمة (استيرادٌ لا نسخ)،
  ولكلٍّ منهما هويّةُ D09-M المركّبة (``point_count`` + ``id_set_digest`` +
  ``content_digest``) محسوبةً بـ``corpus_identity`` نفسِها — السلطة الوحيدة —
  من صفوف **القراءة نفسها** التي بُني منها الإيصال.
* **M1 == M2** — تطابقُ الثلاثيّة والعدّ الدقيق بين القياسين ⇒ ``no_live_mutation``.
* **D09-E** — حكمُ ``readiness_problems`` (الدالّة النقيّة القانونيّة) مُطبَّقاً على
  التقرير **المقيس حيّاً** من M2، لا على تقريرٍ مُختلَق.
* **/readyz · /v1/search** — مشاهدتا الخدمة نفسِها، بحالة HTTP وجسمٍ مُقلَّم
  (بصماتُ نتائج لا نصوصها — الوثائق لا تدخل المصنوعة).

الربط إلزاميّ لا اختياريّ: ``--subject-sha`` و``--subject-tree`` (40-hex) **و**
مرجعُ مصنوعة النشر وبصمتُها. إيصالٌ بلا ربطٍ كامل لا يُكتَب أصلاً — «لا دليلَ
مُصطنَع» تعني أيضاً «لا إيصالَ بلا مَربِط».

اتفاقيّةُ الخروج على سنّة أداة الجرد: إيصالٌ مكتملٌ يوثّق فشلَ بندٍ **دليلٌ لا
عطلُ أداة** ⇒ رمز 0 والحكم في ``verdict``. العجزُ عن القياس نفسِه ⇒ رمز 1.

التشغيل من مضيفٍ يرى Qdrant وخدمةَ الاسترجاع::

    python3 scripts/architecture/d09_live_evidence_receipt.py \
      --subject-sha <40-hex> --subject-tree <40-hex> \
      --deployment-artifact ghcr.io/…/rag-retrieval:… \
      --deployment-artifact-digest sha256:… \
      --search-tenant <tenant> --search-query "نصّ استعلام حقيقيّ" \
      --output evidence/d09-live-receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "scripts/architecture/rag_live_corpus_audit.py"
SCHEMA = "sahool.d09-live-evidence-receipt/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAMPLE_CAP = 5

CHECKLIST_ITEMS = (
    "m1_receipt",
    "m2_receipt",
    "identity_match",
    "no_live_mutation",
    "d09_e",
    "readyz",
    "v1_search",
    "observation",
)


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("d09_live_audit", AUDIT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load audit tool at {AUDIT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_fingerprint(row: Any) -> str:
    """بصمةُ نتيجةِ بحثٍ بتسلسلٍ قانونيّ — لا بـ``str()``.

    تمثيلُ ``str(dict)`` غيرُ مضمونِ الثبات عبر ترتيب المفاتيح والإصدارات،
    وبصمةٌ تتبدّل على بياناتٍ واحدة تُسقِط قابليّةَ إعادة القياس — وهي علّةُ
    وجود الإيصال. أمسكها مراجعٌ آليّ على #898 قبل أن تكلّف.
    """
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _safe_host(url: str) -> str:
    parts = urlsplit(url)
    return parts.hostname or "<unknown>"


def _http_json(
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - operator-supplied internal URLs
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body[:2000]


def _measure_once(
    audit, pq, *, qdrant_url: str, collection: str, subject_sha: str, subject_tree: str
) -> dict[str, Any]:
    """قياسٌ واحد: إيصالُ جردٍ كامل + هويّةُ D09-M من صفوف القراءة نفسها."""
    client = pq.QdrantHttpClient(
        qdrant_url,
        collection,
        vector_size=0,
        api_key=os.getenv("QDRANT_API_KEY") or None,
    )
    exact_count = client.collection_point_count()
    rows = client.scroll_payloads()
    receipt = audit.build_receipt(
        pq,
        rows,
        exact_count=exact_count,
        subject_sha=subject_sha,
        subject_tree=subject_tree,
        collection=collection,
        qdrant_identity=_safe_host(qdrant_url),
    )
    identity = pq.corpus_identity(rows)
    noncanonical = [
        r["point_id"]
        for r in receipt["point_records"]
        if r["serving_candidate"] and not r["canonical_serving_eligible"]
    ]
    return {
        "receipt": receipt,
        "identity": identity,
        "exact_count": exact_count,
        "noncanonical_serving_points": len(noncanonical),
        "noncanonical_serving_samples": noncanonical[:_SAMPLE_CAP],
    }


def compare_identities(m1: dict[str, Any], m2: dict[str, Any]) -> dict[str, bool]:
    """تطابقُ الثلاثيّة حقلاً حقلاً — التسمية الصريحة تجعل موضعَ الانحراف مقروءاً."""
    return {
        "point_count": m1.get("point_count") == m2.get("point_count"),
        "id_set_digest": bool(m1.get("id_set_digest"))
        and m1.get("id_set_digest") == m2.get("id_set_digest"),
        "content_digest": bool(m1.get("content_digest"))
        and m1.get("content_digest") == m2.get("content_digest"),
    }


def derive_verdict(checklist: dict[str, bool]) -> str:
    missing = [k for k in CHECKLIST_ITEMS if not checklist.get(k)]
    return "PASS" if not missing else "FAIL: " + ",".join(missing)


def build_evidence_receipt(
    *,
    subject_sha: str,
    subject_tree: str,
    deployment_artifact: str,
    deployment_artifact_digest: str,
    qdrant_url: str,
    collection: str,
    m1: dict[str, Any],
    m2: dict[str, Any],
    m1_path: str,
    m1_sha256: str,
    m2_path: str,
    m2_sha256: str,
    d09e_problems: list[str],
    readyz_status: int,
    readyz_body: Any,
    search_status: int,
    search_result_count: int | None,
    search_result_fingerprints: list[str],
    search_tenant: str,
    search_query_sha256: str,
    settle_seconds: int,
) -> dict[str, Any]:
    identity_match = compare_identities(m1["identity"], m2["identity"])
    readyz_ready = (
        readyz_status == 200
        and isinstance(readyz_body, dict)
        and readyz_body.get("status") == "ready"
    )
    checklist = {
        "m1_receipt": bool(m1["receipt"].get("physical_count_complete")),
        "m2_receipt": bool(m2["receipt"].get("physical_count_complete")),
        "identity_match": all(identity_match.values()),
        # «غياب الطفرة الحيّة» أوسع من تطابق الهويّة: العدّ الدقيق نفسه لم يتحرّك.
        "no_live_mutation": all(identity_match.values()) and m1["exact_count"] == m2["exact_count"],
        "d09_e": not d09e_problems,
        "readyz": readyz_ready,
        "v1_search": search_status == 200,
        "observation": search_result_count is not None and search_result_count > 0,
    }
    return {
        "schema": SCHEMA,
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject_sha,
        "subject_tree": subject_tree,
        "deployment_artifact": {
            "ref": deployment_artifact,
            "digest": deployment_artifact_digest,
        },
        "qdrant_identity": _safe_host(qdrant_url),
        "collection": collection,
        "read_only": True,
        "authority_promotion": False,
        "settle_seconds_between_measurements": settle_seconds,
        "m1": {
            "receipt_path": m1_path,
            "receipt_sha256": m1_sha256,
            "observed_at": m1["receipt"]["observed_at"],
            "exact_count": m1["exact_count"],
            "corpus_identity": m1["identity"],
        },
        "m2": {
            "receipt_path": m2_path,
            "receipt_sha256": m2_sha256,
            "observed_at": m2["receipt"]["observed_at"],
            "exact_count": m2["exact_count"],
            "corpus_identity": m2["identity"],
        },
        "identity_match": identity_match,
        "d09_e": {
            "judged_by": "services/sahool-platform/core/rag/production_qdrant.py::readiness_problems",
            "input_source": "M2 live measurement",
            "noncanonical_serving_points": m2["noncanonical_serving_points"],
            "noncanonical_serving_samples": m2["noncanonical_serving_samples"],
            "problems": d09e_problems,
        },
        "readyz": {"status": readyz_status, "body": readyz_body},
        "v1_search": {
            "status": search_status,
            "tenant_id": search_tenant,
            "query_sha256": search_query_sha256,
            "result_count": search_result_count,
            "result_fingerprints": search_result_fingerprints,
        },
        "checklist": checklist,
        "verdict": derive_verdict(checklist),
    }


def _validate_40hex(value: str, label: str) -> str:
    value = value.lower()
    if not _HEX40.fullmatch(value):
        raise ValueError(f"{label} must be a full 40-character hex id")
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--subject-tree", required=True)
    ap.add_argument("--deployment-artifact", required=True, help="مرجع مصنوعة النشر (صورة/حزمة)")
    ap.add_argument(
        "--deployment-artifact-digest",
        required=True,
        help="بصمة المصنوعة المنشورة فعلاً بصيغة sha256:<64-hex>",
    )
    ap.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://sahool-qdrant:6333"))
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "sahool_agri_kb"))
    ap.add_argument(
        "--retrieval-url",
        default=os.getenv("RAG_RETRIEVAL_URL", "http://sahool-rag-retrieval:8000"),
    )
    ap.add_argument("--search-tenant", required=True)
    ap.add_argument(
        "--search-query", required=True, help="استعلامٌ حقيقيّ يختاره المشغِّل — لا افتراضيّ"
    )
    ap.add_argument("--settle-seconds", type=int, default=30)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    try:
        subject_sha = _validate_40hex(args.subject_sha, "subject_sha")
        subject_tree = _validate_40hex(args.subject_tree, "subject_tree")
        if not _ARTIFACT_DIGEST.fullmatch(args.deployment_artifact_digest.lower()):
            raise ValueError("deployment_artifact_digest must match sha256:<64-hex>")

        audit = _load_audit_module()
        pq = audit._load_pq()

        m1 = _measure_once(
            audit,
            pq,
            qdrant_url=args.qdrant_url,
            collection=args.collection,
            subject_sha=subject_sha,
            subject_tree=subject_tree,
        )
        # قيمةٌ واحدة مُطبَّعة للنوم وللإيصال معاً: تسجيلُ الخام مع نومٍ مقصوصٍ
        # يجعل الإيصالَ يوثّق مهلةً لم تحدث. أمسكها مراجعٌ آليّ على #898.
        settle_seconds = max(args.settle_seconds, 0)
        time.sleep(settle_seconds)
        m2 = _measure_once(
            audit,
            pq,
            qdrant_url=args.qdrant_url,
            collection=args.collection,
            subject_sha=subject_sha,
            subject_tree=subject_tree,
        )

        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        m_paths = []
        for name, m in (("m1", m1), ("m2", m2)):
            p = out.with_name(out.stem + f".{name}.json")
            p.write_text(
                json.dumps(m["receipt"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            m_paths.append((str(p), _sha256_file(p)))

        d09e_problems = pq.readiness_problems(
            {
                "noncanonical_serving_points": m2["noncanonical_serving_points"],
                "noncanonical_serving_samples": m2["noncanonical_serving_samples"],
                "corpus_identity": m2["identity"],
            }
        )

        readyz_status, readyz_body = _http_json(f"{args.retrieval_url.rstrip('/')}/readyz")
        search_status, search_body = _http_json(
            f"{args.retrieval_url.rstrip('/')}/v1/search",
            {"tenant_id": args.search_tenant, "query": args.search_query, "final_k": 5},
        )
        results = search_body.get("results") if isinstance(search_body, dict) else None
        search_count = len(results) if isinstance(results, list) else None
        fingerprints = [result_fingerprint(r) for r in (results or [])[:_SAMPLE_CAP]]

        receipt = build_evidence_receipt(
            subject_sha=subject_sha,
            subject_tree=subject_tree,
            deployment_artifact=args.deployment_artifact,
            deployment_artifact_digest=args.deployment_artifact_digest.lower(),
            qdrant_url=args.qdrant_url,
            collection=args.collection,
            m1=m1,
            m2=m2,
            m1_path=m_paths[0][0],
            m1_sha256=m_paths[0][1],
            m2_path=m_paths[1][0],
            m2_sha256=m_paths[1][1],
            d09e_problems=d09e_problems,
            readyz_status=readyz_status,
            readyz_body=readyz_body,
            search_status=search_status,
            search_result_count=search_count,
            search_result_fingerprints=fingerprints,
            search_tenant=args.search_tenant,
            search_query_sha256=hashlib.sha256(args.search_query.encode()).hexdigest(),
            settle_seconds=settle_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - أداةُ دليلٍ تفشل مغلقةً
        print(f"d09_live_evidence_receipt_fail {exc}", file=sys.stderr)
        return 1

    out.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"d09_live_evidence_receipt: {receipt['verdict']} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
