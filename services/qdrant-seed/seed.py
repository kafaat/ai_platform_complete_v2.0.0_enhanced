#!/usr/bin/env python3
"""
SAHOOL v9.0 — services/qdrant-seed/seed.py
تحميل المعرفة الزراعية إلى Qdrant (RAG)
مصادر: FAO crop guides + Yemen agricultural research + WOFOST docs
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = logging.getLogger("qdrant-seed")
logging.basicConfig(level=logging.INFO)

QDRANT_HOST = os.getenv("QDRANT_HOST", "sahool-qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_URL = os.getenv("QDRANT_URL", f"http://{QDRANT_HOST}:{QDRANT_PORT}")
# compose يُمرّر QDRANT_API_KEY منذ البداية، وهذا الملفّ كان يتجاهله فيتصل بلا اعتماد.
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
# الاسم القانونيّ للمجموعة هو ما يقرؤه المستهلكان: local-ai-rag (COLLECTION_NAME) و
# rag-retrieval (QDRANT_COLLECTION) وكلاهما يفترض `sahool_agri_kb`. الافتراضيّ السابق
# (`sahool-agri-knowledge`) كان يبذر مجموعةً لا يقرؤها أحد.
COLLECTION = os.getenv("COLLECTION_NAME") or os.getenv("COLLECTION") or "sahool_agri_kb"
# نموذج التضمين + عنوان Ollama — يطابقان local-ai-rag كي تتّسق المتجهات بين
# البذور والاستعلام (نفس النموذج ⇒ نفس فضاء المتجهات). البُعد يُكتشَف تلقائيّاً.
# وcompose يُمرّر EMBEDDING_URL/EMBEDDING_MODEL بهذين الاسمين، فيُقبَلان مرادفَين.
_embedding_url = os.getenv("EMBEDDING_URL")
OLLAMA_BASE_URL = (
    os.getenv("OLLAMA_BASE_URL")
    or (_embedding_url.removesuffix("/api/embeddings") if _embedding_url else None)
    or "http://sahool-ollama:11434"
).rstrip("/")
EMBED_MODEL = os.getenv("EMBED_MODEL") or os.getenv("EMBEDDING_MODEL") or "nomic-embed-text"
SEED_TENANT_ID = (os.getenv("QDRANT_SEED_TENANT_ID") or "__seed_quarantine__").strip()
SEED_REVISION = (os.getenv("QDRANT_SEED_REVISION") or "yemen-reference-v1").strip()
SEED_PROVENANCE_FILE = (os.getenv("QDRANT_SEED_PROVENANCE_FILE") or "").strip()
SEED_PROVENANCE_JSON = (os.getenv("QDRANT_SEED_PROVENANCE_JSON") or "").strip()
SAHOOL_ENV = (os.getenv("SAHOOL_ENV") or "development").strip().lower()
if SAHOOL_ENV == "production" and SEED_PROVENANCE_JSON:
    raise RuntimeError(
        "QDRANT_SEED_PROVENANCE_JSON is forbidden in production; use QDRANT_SEED_PROVENANCE_FILE"
    )
if not SEED_TENANT_ID:
    raise RuntimeError("QDRANT_SEED_TENANT_ID must not be empty")
# ملفّ استثناء الهويّات المحجورة (CORPUS-RECONCILIATION-01): «أيّ
# HOLD_LOGICAL_ID_COLLISION يبقى HOLD ولا يُنفَّذ ضدّه شيء» — والبذر القانونيّ
# upsert على مُعرِّفات حتميّة، فقد يكتب فوق عضو مجموعةٍ محجورة لو صادف مُعرِّفَها.
# الاستثناء صريحٌ ومغلق: ملفٌّ مذكورٌ يتعذّر قراءته يُفشل البذر كلّه، لا يُتخطّى —
# بذرٌ «كاملٌ» فوق حجرٍ أسوأ من لا بذر.
SEED_EXCLUDE_FILE = (os.getenv("QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE") or "").strip()


def _load_excluded_chunk_ids() -> frozenset[str]:
    if not SEED_EXCLUDE_FILE:
        return frozenset()
    data = json.loads(Path(SEED_EXCLUDE_FILE).read_text(encoding="utf-8"))
    ids = data.get("exclude_chunk_ids") if isinstance(data, dict) else data
    if not isinstance(ids, list) or not all(isinstance(x, str) and x.strip() for x in ids):
        raise RuntimeError(
            "QDRANT_SEED_EXCLUDE_CHUNK_IDS_FILE must hold a JSON list of chunk ids "
            "(or an object with exclude_chunk_ids)"
        )
    return frozenset(x.strip() for x in ids)


# قاعدة معرفية زراعية لليمن (يُستبدل بـ embedding حقيقي في الإنتاج)
KNOWLEDGE_BASE = [
    {
        "id": 1,
        "text": "القمح الصلب يحتاج 1200-1600 GDD للنضج في المناخ اليمني. موسم الزراعة: أكتوبر-فبراير.",
        "topic": "wheat",
        "source": "FAO-Yemen",
    },
    {
        "id": 2,
        "text": "الشعير أكثر تحملاً للجفاف من القمح. معامل Kc في منتصف الموسم: 1.10",
        "topic": "barley",
        "source": "FAO-56",
    },
    {
        "id": 3,
        "text": "الري بالتنقيط يوفر 40-60% من مياه الري مقارنة بالغمر في تربة البيضاء",
        "topic": "irrigation",
        "source": "Yemen-NWRA",
    },
    {
        "id": 4,
        "text": "محافظة البيضاء تتلقى 150-400 ملم أمطار سنوياً. معظمها في مارس-أبريل ويوليو-أغسطس",
        "topic": "climate",
        "source": "YMSA",
    },
    {
        "id": 5,
        "text": "منّ الحبوب (Aphid) يظهر عادة في مراحل الإشطاء والإيفاع. العلاج: Imidacloprid 200ml/ha",
        "topic": "pest",
        "source": "Yemen-DOPA",
    },
    {
        "id": 6,
        "text": "التسميد النيتروجيني للقمح: 120 kg N/ha مقسمة 50% عند الزراعة و50% عند الإشطاء",
        "topic": "fertilizer",
        "source": "FAO-56",
    },
    {
        "id": 7,
        "text": "صدأ القمح (Rust) يُكافح بـ Propiconazole 0.5L/ha. التطبيق المبكر أفعل",
        "topic": "disease",
        "source": "ICARDA",
    },
    {
        "id": 8,
        "text": "NDVI > 0.7 يُشير لغطاء نباتي صحي ممتاز. 0.4-0.7 جيد. < 0.4 يحتاج تدخلاً",
        "topic": "remote_sensing",
        "source": "Sentinel-2-ESA",
    },
    {
        "id": 9,
        "text": "أسعار القمح في صنعاء: 400-500 ريال/كجم. الذرة: 280-350 ريال/كجم (2026)",
        "topic": "market",
        "source": "FAO-GIEWS",
    },
    {
        "id": 10,
        "text": "إنتاجية القمح في البيضاء: 1.5-3.5 طن/هكتار. المتوسط الوطني: 2.2 طن/هكتار",
        "topic": "yield",
        "source": "CIMMYT-Yemen",
    },
]


def _load_provenance_manifest() -> dict[str, dict[str, str]]:
    """Load publisher/source/revision/license for every global seed source.

    Built-in seed text is legacy sample content and is not allowed to acquire
    global reference status from a short source label alone. Production/global
    seeding therefore requires an operator-supplied provenance manifest.
    """
    if SEED_PROVENANCE_JSON:
        try:
            raw = json.loads(SEED_PROVENANCE_JSON)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid QDRANT_SEED_PROVENANCE_JSON: {exc}") from exc
    elif SEED_PROVENANCE_FILE:
        path = Path(SEED_PROVENANCE_FILE)
        if not path.is_file():
            raise RuntimeError(f"Qdrant seed provenance manifest not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid Qdrant seed provenance manifest: {exc}") from exc
    else:
        if SEED_TENANT_ID == "__global__":
            raise RuntimeError(
                "global reference seed requires QDRANT_SEED_PROVENANCE_FILE or QDRANT_SEED_PROVENANCE_JSON"
            )
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError("Qdrant seed provenance manifest must be an object")
    required = ("publisher", "source_uri", "source_revision", "license")
    normalized: dict[str, dict[str, str]] = {}
    for source, entry in raw.items():
        if not isinstance(entry, dict):
            raise RuntimeError(f"seed provenance for {source!r} must be an object")
        missing = [key for key in required if not str(entry.get(key) or "").strip()]
        if missing:
            raise RuntimeError(f"seed provenance for {source!r} missing: {', '.join(missing)}")
        normalized[str(source)] = {key: str(entry[key]).strip() for key in required}
    return normalized


def _collection_vector_size(info) -> int:
    """Read an unnamed Qdrant vector size from get_collection() without guessing.

    Named/missing vector schemas are outside the current canonical RAG contract and
    therefore fail closed. This function is intentionally read-only: a mismatch is a
    migration requirement, never permission to drop/recreate production data.
    """
    if hasattr(info, "model_dump"):
        raw = info.model_dump()
    elif hasattr(info, "dict"):
        raw = info.dict()
    elif isinstance(info, dict):
        raw = info
    else:
        raise RuntimeError("Qdrant collection info is not serializable")
    vectors = ((raw.get("config") or {}).get("params") or {}).get("vectors")
    if not isinstance(vectors, dict):
        raise RuntimeError("Qdrant collection vectors schema missing")
    size = vectors.get("size")
    if not isinstance(size, int) or size <= 0:
        raise RuntimeError("Qdrant named/invalid vector schema is not supported by seed contract")
    return size


# ─── إضافة بيانات الجوف/السنيدار (52 قاعدة) ────────────────────
# مع تصحيح S1 → SA1..SA13 (أسماء العيّنات vs تصنيف Sodium Hazard)
try:
    from aljawf_knowledge import ALJAWF_KNOWLEDGE, validate_entries

    # تحقّق من سلامة البيانات قبل الإضافة (fail-fast)
    _validation = validate_entries(ALJAWF_KNOWLEDGE)
    if not _validation["valid"]:
        logger.error(f"⚠️ بيانات الجوف فيها {len(_validation['errors'])} مشكلة")
        for err in _validation["errors"][:5]:
            logger.error(f"  {err}")
    else:
        # تحقّق عدم تعارض IDs مع الأساسية (1-10)
        existing_ids = {e["id"] for e in KNOWLEDGE_BASE}
        new_ids = {e["id"] for e in ALJAWF_KNOWLEDGE}
        conflicts = existing_ids & new_ids
        if conflicts:
            logger.error(f"⚠️ IDs متعارضة: {conflicts}")
        else:
            KNOWLEDGE_BASE.extend(ALJAWF_KNOWLEDGE)
            logger.info(f"✅ أُضيفت {len(ALJAWF_KNOWLEDGE)} قاعدة من الجوف/السنيدار")
            logger.info(
                f"   IDs: {min(new_ids)}-{max(new_ids)}, المواضيع: {len(_validation['topics'])}"
            )
except ImportError:
    logger.warning("⚠️ aljawf_knowledge.py غير موجود — استخدام KNOWLEDGE_BASE الأساسية فقط")


async def _embed(text: str, http: httpx.AsyncClient) -> list[float]:
    """تضمين نصّ عبر Ollama (/api/embeddings) — نفس نموذج RAG. يرفع عند الفشل."""
    r = await http.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60.0,
    )
    r.raise_for_status()
    vec = r.json().get("embedding")
    if not vec:
        raise ValueError("Ollama لم يُعِد متجه تضمين")
    return vec


async def seed():
    provenance = _load_provenance_manifest()
    excluded = _load_excluded_chunk_ids()
    # الاستثناء قبل التضمين وقبل فحص الـprovenance: الوثيقة المستثناة خارج هذا
    # البذر كلّه، لا وثيقةٌ ضُمِّنت ثم أُسقطت في آخر خطوة.
    knowledge = [doc for doc in KNOWLEDGE_BASE if f"seed:{doc['id']}" not in excluded]
    if excluded:
        logger.info(
            "⛔ استُثني %d هويّة محجورة من البذر (بقي %d من %d)",
            len(KNOWLEDGE_BASE) - len(knowledge),
            len(knowledge),
            len(KNOWLEDGE_BASE),
        )
    if SEED_TENANT_ID == "__global__":
        missing_sources = sorted(
            {str(doc.get("source") or "") for doc in knowledge} - set(provenance)
        )
        if missing_sources:
            raise RuntimeError(
                "global reference seed provenance missing sources: " + ", ".join(missing_sources)
            )

    # نولّد تضميناً حقيقيّاً للنصوص عبر Ollama أوّلاً. تدهور رشيق: لو تعذّر خادم
    # التضمين، نُحذّر بوضوح ونتخطّى البذر (لا نُلوّث الفهرس بمتجهات عشوائية تُفسد
    # البحث الدلاليّ — فهرس فارغ أصدق من نتائج عشوائية، وRAG يسقط على البحث الرمزيّ).
    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            vectors = [await _embed(doc["text"], http) for doc in knowledge]
        except Exception as e:
            logger.error(
                "تعذّر توليد التضمين عبر Ollama (%s=%s): %s — البذر المطلوب يفشل صراحةً.",
                EMBED_MODEL,
                OLLAMA_BASE_URL,
                e,
            )
            raise RuntimeError("required Qdrant seed embedding failed") from e

    dim = len(vectors[0])
    logger.info(f"✅ وُلّد تضمين {len(vectors)} وثيقة (بُعد={dim}, نموذج={EMBED_MODEL})")

    client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    exists = await client.collection_exists(COLLECTION)
    if not exists:
        try:
            await client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"✅ Collection '{COLLECTION}' created (dim={dim})")
        except Exception as e:
            # Race-safe retry classification: if another initializer created it, verify below;
            # otherwise preserve the real create/connect/auth failure.
            #
            # The re-probe is itself a network call and can fail for the same reason the
            # create did (unreachable host, bad key). Letting it propagate raw would
            # replace the real cause with a second-order symptom, and the operator would
            # debug the probe instead of the connection. So it fails closed on a named
            # error that keeps the original as `__cause__`.
            try:
                created_by_peer = await client.collection_exists(COLLECTION)
            except Exception as probe_error:
                logger.error("فشل إنشاء المجموعة '%s' وتعذّر التحقّق بعده: %s", COLLECTION, e)
                raise RuntimeError(
                    f"QDRANT_COLLECTION_CREATE_FAILED: collection={COLLECTION}; "
                    f"post-failure existence probe also failed ({probe_error})"
                ) from e
            if not created_by_peer:
                logger.error("فشل إنشاء/تهيئة المجموعة '%s': %s", COLLECTION, e)
                raise
    info = await client.get_collection(COLLECTION)
    live_dim = _collection_vector_size(info)
    if live_dim != dim:
        raise RuntimeError(
            "QDRANT_VECTOR_SCHEMA_MISMATCH: "
            f"collection={COLLECTION} existing_dim={live_dim} embedding_dim={dim}; "
            "migration/reindex required — refusing destructive auto-recreation"
        )
    logger.info("✅ Collection '%s' vector schema matches embedding dim=%s", COLLECTION, dim)

    points = []
    for i, doc in enumerate(knowledge):
        chunk_id = f"seed:{doc['id']}"
        document_id = f"reference:{doc.get('source', 'unknown')}:{doc['id']}"
        source = str(doc.get("source") or "")
        source_provenance = provenance.get(source, {})
        is_global = SEED_TENANT_ID == "__global__"
        metadata = {
            "chunk_id": chunk_id,
            "tenant_id": SEED_TENANT_ID,
            "source_type": "curated_reference" if is_global else "legacy_seed_quarantine",
            "document_id": document_id,
            "chunk_index": 0,
            "total_chunks": 1,
            "evidence_level": "document",
            "topic": doc.get("topic"),
            "publisher": source_provenance.get("publisher") if is_global else None,
            "source_uri": source_provenance.get("source_uri")
            if is_global
            else f"sahool://seed-quarantine/{doc['id']}",
            "source_revision": source_provenance.get("source_revision")
            if is_global
            else SEED_REVISION,
            "license": source_provenance.get("license") if is_global else None,
            "source_class": "curated_reference" if is_global else "internal_document",
            "prescriptive_eligible": False,
            "content_digest": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest(),
            "provenance_status": "verified_manifest"
            if is_global
            else "legacy_unverified_quarantine",
        }
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sahool-rag:{chunk_id}"))
        points.append(
            PointStruct(
                id=point_id,
                vector=vectors[i],
                payload={"page_content": doc["text"], "metadata": metadata},
            )
        )

    await client.upsert(collection_name=COLLECTION, points=points)
    logger.info(f"✅ Seeded {len(points)} documents into Qdrant")

    info = await client.get_collection(COLLECTION)
    logger.info(f"Collection info: {info.points_count} points")

    await client.close()


if __name__ == "__main__":
    asyncio.run(seed())
