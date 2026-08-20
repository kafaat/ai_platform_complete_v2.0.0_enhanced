#!/usr/bin/env python3
"""
SAHOOL v9.1 — Local Generation Runtime (Qwen3 + Ollama; canonical retrieval shadow)
Agricultural Advisor with local LLM — no API keys, no cloud leakage.
Supports Arabic + English agricultural knowledge base.
Hardware: GPU RTX 4090/5090 + 192GB RAM recommended for 70B+ models.
"""

from __future__ import annotations

import asyncio
import hashlib
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

try:
    from jose import JWTError as _JE
    from jose import jwt as _jjwt
except ModuleNotFoundError:  # pragma: no cover - offline tests / minimal env

    class _JE(Exception):
        pass

    class _MissingJoseJWT:
        @staticmethod
        def decode(*args, **kwargs):
            raise _JE("python-jose is required for JWT validation")

    _jjwt = _MissingJoseJWT()

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
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://sahool-ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
QDRANT_URL = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "sahool_agri_kb")
# ARCH-S3 Expand: rag-retrieval is the intended retrieval authority.  Direct Qdrant
# remains primary only during measured shadow parity; SHADOW is OFF by default and
# never changes the response path.  Cutover/revoke is blocked by the S3 guard until
# embedding/collection/live parity proof is accepted.
RAG_RETRIEVAL_URL = os.getenv("RAG_RETRIEVAL_URL", "http://sahool-rag-retrieval:8000").rstrip("/")
RAG_RETRIEVAL_SHADOW = os.getenv("RAG_RETRIEVAL_SHADOW", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))  # context window
# مصادقة خدمة-لخدمة: استيعاب المستندات يكتب لقاعدة المعرفة — منع تسميم RAG
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")
# حدّ أقصى لحجم الملفّ المرفوع (منع DoS عبر تحميل ملفّ ضخم في الذاكرة).
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_GLOBAL_REFERENCE_TENANT = "__global__"


def _validate_tenant_id(tenant_id: str) -> str:
    if not tenant_id or not _TENANT_RE.match(str(tenant_id)):
        raise HTTPException(400, "Invalid tenant_id")
    if str(tenant_id) == _GLOBAL_REFERENCE_TENANT:
        raise HTTPException(403, "global reference tenant is reserved for curated seed ingestion")
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

    qclient = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, prefer_grpc=False)
    if not qclient.collection_exists(COLLECTION_NAME):
        # ARCH-S3 writer convergence: this runtime is now read-only against Qdrant.
        # Collection creation/initialization belongs to qdrant-seed or the canonical
        # rag-retrieval ingest authority; a query must never create storage as a side effect.
        raise RuntimeError(f"Qdrant collection {COLLECTION_NAME!r} does not exist")
    _vectorstore = QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        prefer_grpc=False,
        collection_name=COLLECTION_NAME,
    )
    logger.info("Qdrant vector store connected read-only (existing collection)")
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


async def ingest_documents(
    file_paths: list[Path],
    tenant_id: str = "default",
    source_names: dict[str, str] | None = None,
) -> dict:
    """Parse locally, but write knowledge only through the canonical retrieval authority.

    ARCH-S3 writer convergence: local-ai-rag no longer writes Qdrant during ingest.
    The direct Qdrant dependency remains read-only while retrieval parity is measured.
    Canonical-ingest failure is explicit and fail-closed; there is no direct-write fallback.
    """
    all_docs: list[Document] = []
    source_names = source_names or {}
    for p in file_paths:
        try:
            original_name = source_names.get(str(p), p.name)
            file_digest = hashlib.sha256(p.read_bytes()).hexdigest()
            docs = load_document(p)
            for d in docs:
                d.metadata["tenant_id"] = tenant_id
                d.metadata["source_file"] = original_name
                d.metadata["source_class"] = "tenant_document"
                d.metadata["source_uri"] = f"tenant-upload://{tenant_id}/{original_name}"
                d.metadata["source_revision"] = f"sha256:{file_digest}"
                d.metadata["ingested_at"] = datetime.now(UTC).isoformat()
            all_docs.extend(docs)
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")

    if not all_docs:
        return {"ingested": 0, "chunks": 0}

    chunks = split_docs(all_docs)
    by_source: dict[str, list[Document]] = {}
    for chunk in chunks:
        by_source.setdefault(str(chunk.metadata.get("source_file") or "unknown"), []).append(chunk)

    wire_chunks: list[dict] = []
    for source_file, rows in sorted(by_source.items()):
        document_id = hashlib.sha256(f"{tenant_id}:{source_file}".encode()).hexdigest()
        total = len(rows)
        for idx, chunk in enumerate(rows):
            chunk_id = hashlib.sha256(
                f"{document_id}:{idx}:".encode() + chunk.page_content.encode("utf-8")
            ).hexdigest()
            metadata = dict(chunk.metadata)
            metadata.update(
                {
                    "source_file": source_file,
                }
            )
            wire_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "tenant_id": tenant_id,
                    "text": chunk.page_content,
                    "source_type": "uploaded_document",
                    "document_id": document_id,
                    "chunk_index": idx,
                    "total_chunks": total,
                    "metadata": metadata,
                }
            )

    if not AGENT_TOKEN:
        raise HTTPException(503, "خدمة المعرفة غير مهيأة للكتابة المحكومة")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{RAG_RETRIEVAL_URL}/v1/ingest",
                json={"chunks": wire_chunks},
                headers={"X-Agent-Token": AGENT_TOKEN, "X-Tenant-Id": tenant_id},
            )
        response.raise_for_status()
        accepted = int(response.json().get("ingested", 0))
    except Exception as exc:  # noqa: BLE001 — canonical writer failure must be explicit
        logger.warning("RAG_CANONICAL_INGEST_FAILED type=%s", type(exc).__name__)
        raise HTTPException(503, "خدمة المعرفة غير متاحة حاليّاً (تعذّر الاستيعاب)") from exc
    if accepted != len(wire_chunks):
        raise HTTPException(503, "خدمة المعرفة أعادت عدداً غير مطابق من المقاطع المستوعبة")
    return {"ingested": len(all_docs), "chunks": accepted}


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


def _retrieval_fingerprint(text: str) -> str:
    normalized = " ".join((text or "").split()).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


async def _shadow_canonical_retrieval(
    question: str, tenant_id: str, k: int, direct_docs: list[Document]
) -> None:
    """Observe canonical retrieval parity without changing the authoritative response.

    Shadow failure is logged explicitly; it is not a fallback because the canonical
    path is not authoritative in EXPAND.  Once S3 reaches CUTOVER this function is
    removed together with the direct Qdrant path rather than wrapped in fallback.
    """
    if not RAG_RETRIEVAL_SHADOW:
        return
    payload = {"tenant_id": tenant_id, "query": question, "final_k": min(k, 10)}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{RAG_RETRIEVAL_URL}/v1/search",
                json=payload,
                headers={"X-Tenant-Id": tenant_id},
            )
        response.raise_for_status()
        annotations = response.json().get("annotations") or []
    except Exception as exc:  # noqa: BLE001 — shadow is read-only, failure is explicit telemetry
        logger.warning("RAG_RETRIEVAL_SHADOW_FAILED type=%s", type(exc).__name__)
        return
    direct = {_retrieval_fingerprint(d.page_content) for d in direct_docs}
    canonical = {
        _retrieval_fingerprint(str(a.get("text") or "")) for a in annotations if a.get("text")
    }
    union = direct | canonical
    overlap = (len(direct & canonical) / len(union)) if union else 1.0
    logger.info(
        "RAG_RETRIEVAL_SHADOW_PARITY direct=%d canonical=%d overlap=%.4f",
        len(direct),
        len(canonical),
        overlap,
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

    from qdrant_client.http.models import FieldCondition, Filter, MatchAny

    # العزل يبقى fail-closed: يرى المستأجر وثائقه والمرجع المشترك المنظّم فقط،
    # ولا يرى tenant آخر. ``__global__`` محجوز للـcurated reference غير prescriptive.
    tenant_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.tenant_id",
                match=MatchAny(any=[tenant_id, _GLOBAL_REFERENCE_TENANT]),
            )
        ]
    )
    retriever = vs.as_retriever(search_kwargs={"k": k, "filter": tenant_filter})

    try:
        docs = await asyncio.to_thread(retriever.invoke, question)
    except Exception as e:  # noqa: BLE001 — تعطّل Qdrant/Ollama ⇒ 503 صادق
        logger.warning("فشل استرجاع المعرفة: %s", type(e).__name__)
        raise HTTPException(503, "خدمة المعرفة غير متاحة حاليّاً (تعذّر الاسترجاع)") from e

    # ARCH-S3 EXPAND: compare canonical retrieval out-of-band. The direct path is
    # still the declared primary until live parity is accepted; no response data
    # comes from shadow and no canonical failure is silently used as a fallback.
    await _shadow_canonical_retrieval(question, tenant_id, k, docs)

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

# تحصين الإنتاج (fail-closed، تماثُل مع auth/المنصّة): RS256 إلزاميّ — HS256 سرّ متماثل
# مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر توكناً). في الإنتاج بلا
# JWT_PUBLIC_KEY نرفض الإقلاع ما لم يُعطَّل صراحةً (مهرب ترحيل SAHOOL_ALLOW_HS256_IN_PROD=1).
if (
    not os.getenv("JWT_PUBLIC_KEY", "").strip()
    and os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    and os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower()
    not in {"1", "true", "yes", "on"}
):
    raise RuntimeError(
        "RS256 مطلوب في الإنتاج: اضبط JWT_PUBLIC_KEY (HS256 لا يُنهي shared trust domain). "
        "للترحيل المؤقّت فقط: SAHOOL_ALLOW_HS256_IN_PROD=1."
    )


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


@app.post("/v1/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest, user: dict = Depends(_get_rag_user)):
    _require_ready()
    # العزل من مصدر موثوق: tenant_id من الـJWT لا من جسم الطلب (يمنع قراءة مستأجِر آخر).
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(401, "التوكن لا يحمل tenant_id")
    return await query_rag(req.question, _validate_tenant_id(str(tenant_id)), req.k)


@app.post("/v1/ingest")
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
    source_names: dict[str, str] = {}
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
        tmp_path = Path(tmp.name)
        paths.append(tmp_path)
        source_names[str(tmp_path)] = Path(upload.filename).name

    result = await ingest_documents(paths, tenant_id, source_names=source_names)

    # cleanup
    for p in paths:
        p.unlink(missing_ok=True)

    return {"status": "ingested", **result}


@app.get("/healthz")
async def healthz():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
            ollama_ok = r.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.debug("فحص صحّة Ollama فشل: %s", type(e).__name__)
    return {
        "status": "alive",
        "service": "local-ai-rag",
        "ollama": "connected" if ollama_ok else "disconnected",
        "model": LLM_MODEL,
        "embed_model": EMBED_MODEL,
    }


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def readyz():
    """يردّ 200 فقط بعد تحميل النماذج؛ 503 أثناء التهيئة الخلفيّة."""
    if _llm is None or _vectorstore is None:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "initialising",
                "service": "local-ai-rag",
                "message": "النماذج قيد التحميل",
            },
        )
    return {
        "status": "ready",
        "service": "local-ai-rag",
        "version": "9.1.0",
        "implemented_runtime": True,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
