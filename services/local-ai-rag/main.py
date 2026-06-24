#!/usr/bin/env python3
"""
SAHOOL v9.1 — Local AI RAG Service (Qwen3 + Ollama + Qdrant)
Agricultural Advisor with local LLM — no API keys, no cloud leakage.
Supports Arabic + English agricultural knowledge base.
Hardware: GPU RTX 4090/5090 + 192GB RAM recommended for 70B+ models.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials as _C
from fastapi.security import HTTPBearer as _B
from jose import JWTError as _JE
from jose import jwt as _jjwt

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader, TextLoader

# مسارات مستقرّة (langchain_core/langchain_text_splitters) بدل langchain.schema
# وlangchain.text_splitter المهملين — تجنّباً للكسر عند ترقية langchain.
from langchain_core.documents import Document
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("local-ai-rag")
except ImportError:
    logging.basicConfig(
        level=logging.INFO, format='{"time":"%(asctime)s","svc":"local-ai-rag","msg":"%(message)s"}'
    )
    logger = logging.getLogger("local-ai-rag")

# ── Config ────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:32b")  # or qwen3:70b, qwen3:8b
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
QDRANT_URL = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "sahool_agri_kb")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))  # context window
# مصادقة خدمة-لخدمة: استيعاب المستندات يكتب لقاعدة المعرفة — منع تسميم RAG
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")
# حدّ أقصى لحجم الملفّ المرفوع (منع DoS عبر تحميل ملفّ ضخم في الذاكرة).
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_tenant_id(tenant_id: str) -> str:
    if not tenant_id or not _TENANT_RE.match(str(tenant_id)):
        raise HTTPException(400, "Invalid tenant_id")
    return str(tenant_id)


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الاستيعاب معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


_vectorstore: QdrantVectorStore | None = None
_llm: ChatOllama | None = None


# ══════════════════════════════════════════════════════════════
# Ollama Health Check
# ══════════════════════════════════════════════════════════════
async def wait_for_ollama(timeout: float = 120.0):
    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(timeout=60.0) as client:
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
                if r.status_code == 200:
                    models = r.json().get("models", [])
                    model_names = [m.get("name", "") for m in models]
                    if LLM_MODEL in model_names and EMBED_MODEL in model_names:
                        logger.info(f"Ollama ready. Models: {model_names}")
                        return True
                    # النماذج غير حاضرة بعد: نطلب السحب ثمّ **نعيد الفحص** في الدورة
                    # التالية. لا نُرجِع True هنا (كان يُعلِن الجاهزيّة زوراً قبل اكتمال
                    # السحب، فيفشل أوّل /query بـ500 بدل انتظار صادق).
                    logger.info(f"Ollama up. Pulling {LLM_MODEL} + {EMBED_MODEL}...")
                    await client.post(
                        f"{OLLAMA_BASE_URL}/api/pull", json={"name": LLM_MODEL}, timeout=300.0
                    )
                    await client.post(
                        f"{OLLAMA_BASE_URL}/api/pull", json={"name": EMBED_MODEL}, timeout=300.0
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("تعذّر سحب نماذج Ollama (محاولة): %s", type(e).__name__)
            await asyncio.sleep(5)
    raise RuntimeError("Ollama not available — النماذج لم تجهز ضمن المهلة")


# ══════════════════════════════════════════════════════════════
# Vector Store Init
# ══════════════════════════════════════════════════════════════
def init_vectorstore() -> QdrantVectorStore:
    global _vectorstore
    if _vectorstore:
        return _vectorstore

    embeddings = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)

    # نتحقّق صراحةً من وجود المجموعة (لا نلتقط Exception عامّاً يُخفي أعطال شبكة/
    # Qdrant ويُحوّلها زوراً إلى «إنشاء جديد»). أخطاء الاتصال الحقيقيّة تنتشر بصدق.
    from qdrant_client import QdrantClient

    qclient = QdrantClient(url=QDRANT_URL, prefer_grpc=False)
    if qclient.collection_exists(COLLECTION_NAME):
        _vectorstore = QdrantVectorStore.from_existing_collection(
            embedding=embeddings,
            url=QDRANT_URL,
            prefer_grpc=False,
            collection_name=COLLECTION_NAME,
        )
        logger.info("Qdrant vector store connected (existing collection)")
    else:
        # إنشاء لمرّة واحدة بوثيقة بذرة بلا tenant_id (مُستبعَدة بفلتر العزل، فلا
        # تتراكم ولا تظهر كـ«مصدر»). لا نُعيد إدخالها في كلّ إقلاع.
        _vectorstore = QdrantVectorStore.from_documents(
            documents=[
                Document(
                    page_content="SAHOOL initialization document.",
                    metadata={"source": "init"},
                )
            ],
            embedding=embeddings,
            url=QDRANT_URL,
            prefer_grpc=False,
            collection_name=COLLECTION_NAME,
            force_recreate=False,
        )
        logger.info("Qdrant vector store created (new collection)")
    return _vectorstore


# ══════════════════════════════════════════════════════════════
# LLM Init
# ══════════════════════════════════════════════════════════════
def init_llm() -> ChatOllama:
    global _llm
    if _llm:
        return _llm
    _llm = ChatOllama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
        num_ctx=NUM_CTX,
    )
    logger.info(f"LLM initialized: {LLM_MODEL} (ctx={NUM_CTX})")
    return _llm


# ══════════════════════════════════════════════════════════════
# Document Ingestion
# ══════════════════════════════════════════════════════════════
def load_document(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(path))
    elif suffix in (".txt", ".md", ".csv"):
        loader = TextLoader(str(path), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format: {suffix}")
    return loader.load()


def split_docs(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", "!", "?", "،", "；", " ", ""],
    )
    return splitter.split_documents(docs)


async def ingest_documents(file_paths: list[Path], tenant_id: str = "default") -> dict:
    vs = init_vectorstore()
    all_docs: list[Document] = []
    for p in file_paths:
        try:
            docs = load_document(p)
            for d in docs:
                d.metadata["tenant_id"] = tenant_id
                d.metadata["source_file"] = p.name
                d.metadata["ingested_at"] = datetime.now(UTC).isoformat()
            all_docs.extend(docs)
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")

    if not all_docs:
        return {"ingested": 0, "chunks": 0}

    chunks = split_docs(all_docs)
    vs.add_documents(chunks)
    return {"ingested": len(all_docs), "chunks": len(chunks)}


# ══════════════════════════════════════════════════════════════
# RAG Query
# ══════════════════════════════════════════════════════════════
# prompt تأريض صارم: الإجابة من السياق المُسترجَع فقط، ورفض صريح عند عدم الكفاية.
# يمنع النموذج من الإجابة من معرفته الداخليّة أو اختلاق مصادر (مبدأ: لا بيانات مُلفَّقة).
_NO_KNOWLEDGE_AR = "لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال."
_GROUNDED_PROMPT = (
    "أنت مستشار زراعيّ. أجب حصراً اعتماداً على «السياق» أدناه. إن لم يكن في السياق ما "
    "يكفي للإجابة، فقل حرفيّاً: «" + _NO_KNOWLEDGE_AR + "» — لا تستعمل معرفتك العامّة "
    "ولا تختلق مصادر أو أرقاماً.\n\nالسياق:\n{context}\n\nالسؤال: {question}\n\nالإجابة:"
)


async def query_rag(question: str, tenant_id: str, k: int = 5) -> dict:
    """استعلام RAG مُؤرَّض ومعزول بالمستأجِر.

    - العزل: يُفلتَر دائماً بـtenant_id المُشتَقّ من الـJWT (لا من جسم الطلب، ولا
      استثناء لـ"default") — يمنع القراءة العابرة للمستأجرين.
    - التأريض: لا نُجيب إلّا من الوثائق المُسترجَعة؛ عند فراغ الاسترجاع نردّ رفضاً
      صريحاً بلا مصادر (لا هلوسة).
    - الصدق التشغيليّ: تعطّل Qdrant/Ollama يُترجَم إلى 503 صريح لا 500 مبهَم.
    """
    vs = init_vectorstore()
    llm = init_llm()

    from qdrant_client.http.models import FieldCondition, Filter, MatchValue

    # فلتر العزل **دائماً** (لكلّ المستأجرين بمن فيهم "default"): لا يرى المستأجِر
    # إلّا وثائقه. وثيقة init بلا tenant_id ⇒ مُستبعَدة تلقائيّاً.
    tenant_filter = Filter(
        must=[FieldCondition(key="metadata.tenant_id", match=MatchValue(value=tenant_id))]
    )
    retriever = vs.as_retriever(search_kwargs={"k": k, "filter": tenant_filter})

    try:
        docs = await asyncio.to_thread(retriever.invoke, question)
    except Exception as e:  # noqa: BLE001 — تعطّل Qdrant/Ollama ⇒ 503 صادق
        logger.warning("فشل استرجاع المعرفة: %s", type(e).__name__)
        raise HTTPException(503, "خدمة المعرفة غير متاحة حاليّاً (تعذّر الاسترجاع)") from e

    # لا سياق ⇒ رفض صريح بلا مصادر (لا نستدعي النموذج لئلّا يُجيب من معرفته).
    if not docs:
        return {
            "question": question,
            "answer": _NO_KNOWLEDGE_AR,
            "model": LLM_MODEL,
            "sources": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    context = "\n\n".join(d.page_content for d in docs)
    prompt = _GROUNDED_PROMPT.format(context=context, question=question)
    try:
        resp = await asyncio.to_thread(llm.invoke, prompt)
    except Exception as e:  # noqa: BLE001 — تعطّل Ollama ⇒ 503 صادق
        logger.warning("فشل توليد الإجابة: %s", type(e).__name__)
        raise HTTPException(503, "خدمة المعرفة غير متاحة حاليّاً (تعذّر التوليد)") from e

    answer = getattr(resp, "content", None) or str(resp)
    sources = [
        {
            "source": d.metadata.get("source_file", "unknown"),
            "page": d.metadata.get("page", 0),
            # "..." فقط عند الاقتطاع الفعليّ (لا نوحي باقتطاع لم يحدث).
            "snippet": d.page_content[:200] + ("..." if len(d.page_content) > 200 else ""),
        }
        for d in docs
    ]

    return {
        "question": question,
        "answer": answer,
        "model": LLM_MODEL,
        "sources": sources,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
async def _init_models_background() -> None:
    """يسحب النماذج ويهيّئ LLM + المتجهات دون حجب الإقلاع — كي تكون الحاوية
    حيّة فوراً للـhealthcheck. _llm/_vectorstore يصبحان غير None بعد الجاهزيّة."""
    try:
        logger.info("تهيئة خلفيّة: انتظار Ollama وسحب النماذج...")
        await wait_for_ollama()
        init_llm()
        init_vectorstore()
        logger.info("اكتملت التهيئة الخلفيّة — خدمة RAG جاهزة بالكامل")
    except Exception as exc:  # noqa: BLE001
        logger.error("فشلت التهيئة الخلفيّة للنماذج: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Local AI RAG starting (سحب النماذج يجري في الخلفيّة)...")
    # fire-and-forget: التطبيق حيّ فوراً للفحوص؛ النماذج تُحمَّل في الخلفيّة.
    asyncio.create_task(_init_models_background())
    logger.info("خادم RAG HTTP جاهز — النماذج تُحمَّل في الخلفيّة")
    yield
    logger.info("Local AI RAG stopped")


# C-07 FIX: JWT auth for RAG endpoints
_rag_security = _B(auto_error=False)
_RAG_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_RAG_SECRET = _RAG_PUBLIC if _RAG_PUBLIC else os.getenv("JWT_SECRET", "")
_RAG_ALG = "RS256" if _RAG_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}


async def _get_rag_user(creds: _C = Depends(_rag_security)) -> dict:
    # fail-closed: بلا سرّ/مفتاح مضبوط لا يجوز التحقّق (سرّ HS256 فارغ كان يقبل
    # توكنات مزوّرة). نرفض بـ503 كما يفعل حارس توكن الخدمة، لا نسمح بمرور صامت.
    if not _RAG_SECRET:
        raise HTTPException(503, "JWT_SECRET/JWT_PUBLIC_KEY غير مضبوط — المصادقة معطّلة بأمان")
    # في وضع HS256 نفرض حدّاً أدنى للطول (≥32) كبقيّة خدمات المستودع — سرّ قصير
    # قابل للتخمين. (RS256 يستعمل مفتاحاً عامّاً طويلاً فلا يَعنيه هذا الحدّ.)
    if _RAG_ALG == "HS256" and len(_RAG_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET ضعيف (<32 محرفاً) — المصادقة معطّلة بأمان")
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        payload = _jjwt.decode(
            creds.credentials, _RAG_SECRET, algorithms=[_RAG_ALG], audience="sahool"
        )
    except _JE as e:
        logger.warning("RAG JWT validation failed: %s", type(e).__name__)
        raise HTTPException(401, "Invalid token") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    return payload


app = FastAPI(title="SAHOOL Local AI RAG", version="9.1.0", lifespan=lifespan)
# ✅ OTEL
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    logger.debug("OTEL غير مثبّت — التتبّع معطّل (اختياري)")


# ══════════════════════════════════════════════════════════════
# API Models
# ══════════════════════════════════════════════════════════════
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    # ملاحظة: tenant_id لا يُؤخَذ من جسم الطلب (كان ثغرة عزل) — يُشتَقّ من الـJWT.
    k: int = Field(5, ge=1, le=20)


class QueryResponse(BaseModel):
    question: str
    answer: str
    model: str
    sources: list
    timestamp: str


# ══════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════
def _require_ready() -> None:
    """يرفض الطلبات المعتمِدة على النماذج بـ503 أثناء التهيئة الخلفيّة — كي يحصل
    العميل على 503 متّسقة (مثل /readyz) بدل 500 من فشل اتّصال Qdrant/Ollama."""
    if _llm is None or _vectorstore is None:
        raise HTTPException(503, "الخدمة قيد التهيئة — النماذج تُحمَّل، أعد المحاولة لاحقاً")


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest, user: dict = Depends(_get_rag_user)):
    _require_ready()
    # العزل من مصدر موثوق: tenant_id من الـJWT لا من جسم الطلب (يمنع قراءة مستأجِر آخر).
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(401, "التوكن لا يحمل tenant_id")
    return await query_rag(req.question, _validate_tenant_id(str(tenant_id)), req.k)


@app.post("/ingest")
async def ingest_endpoint(
    files: list[UploadFile] = File(...),
    tenant_id: str = Form("default"),
    x_agent_token: str = Header(None),
):
    """Upload PDF/TXT/MD files to build the agricultural knowledge base.

    يتطلّب توكن خدمة (منع تسميم قاعدة المعرفة بمستندات مزوّرة).
    """
    _require_service_token(x_agent_token)
    _require_ready()
    tenant_id = _validate_tenant_id(tenant_id)
    paths: list[Path] = []
    for upload in files:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in (".pdf", ".txt", ".md", ".csv"):
            raise HTTPException(400, f"Unsupported: {suffix}")

        # قراءة متدفّقة مع عدّ البايتات والإيقاف عند تجاوز الحدّ — لا نُحمّل الملفّ
        # كاملاً في الذاكرة (يمنع DoS عبر ملفّ ضخم).
        limit = MAX_UPLOAD_MB * 1024 * 1024
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        total = 0
        try:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"الملفّ {upload.filename} يتجاوز الحدّ الأقصى ({MAX_UPLOAD_MB}MB)",
                    )
                tmp.write(chunk)
        finally:
            if not tmp.closed:
                tmp.close()
        paths.append(Path(tmp.name))

    result = await ingest_documents(paths, tenant_id)

    # cleanup
    for p in paths:
        p.unlink(missing_ok=True)

    return {"status": "ingested", **result}


@app.get("/healthz")
@app.get("/health")
async def health():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
            ollama_ok = r.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.debug("فحص صحّة Ollama فشل: %s", type(e).__name__)
    return {
        "status": "alive",
        "ollama": "connected" if ollama_ok else "disconnected",
        "model": LLM_MODEL,
        "embed_model": EMBED_MODEL,
    }


@app.get("/readyz")
async def readyz():
    """يردّ 200 فقط بعد تحميل النماذج؛ 503 أثناء التهيئة الخلفيّة."""
    if _llm is None or _vectorstore is None:
        raise HTTPException(
            status_code=503,
            detail={"status": "initialising", "message": "النماذج قيد التحميل"},
        )
    return {"status": "ready", "version": "9.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
