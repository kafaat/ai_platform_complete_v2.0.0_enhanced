#!/usr/bin/env python3
"""
SAHOOL v9.0 — services/qdrant-seed/seed.py
تحميل المعرفة الزراعية إلى Qdrant (RAG)
مصادر: FAO crop guides + Yemen agricultural research + WOFOST docs
"""
import asyncio, logging, os
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, models
)

logger = logging.getLogger("qdrant-seed")
logging.basicConfig(level=logging.INFO)

QDRANT_URL = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
COLLECTION  = os.getenv("COLLECTION_NAME", "sahool-agri-knowledge")
VECTOR_DIM  = 384  # sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# قاعدة معرفية زراعية لليمن (يُستبدل بـ embedding حقيقي في الإنتاج)
KNOWLEDGE_BASE = [
    {"id":1,"text":"القمح الصلب يحتاج 1200-1600 GDD للنضج في المناخ اليمني. موسم الزراعة: أكتوبر-فبراير.","topic":"wheat","source":"FAO-Yemen"},
    {"id":2,"text":"الشعير أكثر تحملاً للجفاف من القمح. معامل Kc في منتصف الموسم: 1.10","topic":"barley","source":"FAO-56"},
    {"id":3,"text":"الري بالتنقيط يوفر 40-60% من مياه الري مقارنة بالغمر في تربة البيضاء","topic":"irrigation","source":"Yemen-NWRA"},
    {"id":4,"text":"محافظة البيضاء تتلقى 150-400 ملم أمطار سنوياً. معظمها في مارس-أبريل ويوليو-أغسطس","topic":"climate","source":"YMSA"},
    {"id":5,"text":"منّ الحبوب (Aphid) يظهر عادة في مراحل الإشطاء والإيفاع. العلاج: Imidacloprid 200ml/ha","topic":"pest","source":"Yemen-DOPA"},
    {"id":6,"text":"التسميد النيتروجيني للقمح: 120 kg N/ha مقسمة 50% عند الزراعة و50% عند الإشطاء","topic":"fertilizer","source":"FAO-56"},
    {"id":7,"text":"صدأ القمح (Rust) يُكافح بـ Propiconazole 0.5L/ha. التطبيق المبكر أفعل","topic":"disease","source":"ICARDA"},
    {"id":8,"text":"NDVI > 0.7 يُشير لغطاء نباتي صحي ممتاز. 0.4-0.7 جيد. < 0.4 يحتاج تدخلاً","topic":"remote_sensing","source":"Sentinel-2-ESA"},
    {"id":9,"text":"أسعار القمح في صنعاء: 400-500 ريال/كجم. الذرة: 280-350 ريال/كجم (2026)","topic":"market","source":"FAO-GIEWS"},
    {"id":10,"text":"إنتاجية القمح في البيضاء: 1.5-3.5 طن/هكتار. المتوسط الوطني: 2.2 طن/هكتار","topic":"yield","source":"CIMMYT-Yemen"},
]

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
            logger.info(f"   IDs: {min(new_ids)}-{max(new_ids)}, "
                       f"المواضيع: {len(_validation['topics'])}")
except ImportError:
    logger.warning("⚠️ aljawf_knowledge.py غير موجود — استخدام KNOWLEDGE_BASE الأساسية فقط")

async def seed():
    client = AsyncQdrantClient(url=QDRANT_URL)
    
    # إنشاء الـ collection
    try:
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(f"✅ Collection '{COLLECTION}' created")
    except Exception:
        logger.info(f"Collection '{COLLECTION}' already exists")

    # في الإنتاج: استخدم sentence-transformers للـ embedding الحقيقي
    # هنا: vectors عشوائية كـ placeholder (يُستبدل بـ embedding حقيقي)
    import random
    rng = random.Random(42)
    
    points = [
        PointStruct(
            id=doc["id"],
            vector=[rng.gauss(0, 0.1) for _ in range(VECTOR_DIM)],
            payload={k: v for k, v in doc.items() if k != "id"}
        )
        for doc in KNOWLEDGE_BASE
    ]
    
    await client.upsert(collection_name=COLLECTION, points=points)
    logger.info(f"✅ Seeded {len(points)} documents into Qdrant")
    
    # تحقق
    info = await client.get_collection(COLLECTION)
    logger.info(f"Collection info: {info.points_count} points")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(seed())
