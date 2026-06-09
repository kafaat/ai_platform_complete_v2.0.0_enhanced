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
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi import File, Form, HTTPException, UploadFile, Header
from fastapi.security import HTTPBearer as _B, HTTPAuthorizationCredentials as _C
from jose import jwt as _jjwt, JWTError as _JE
from pydantic import BaseModel, Field

# LangChain imports
from langchain.chains import RetrievalQA
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_qdrant import QdrantVectorStore
from langchain_ollama import ChatOllama, OllamaEmbeddings
# مسارات مستقرّة (langchain_core/langchain_text_splitters) بدل langchain.schema
# وlangchain.text_splitter المهملين — تجنّباً للكسر عند ترقية langchain.
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from shared.logging_config import setup_logging
    logger = setup_logging("local-ai-rag")
except ImportError:
    logging.basicConfig(level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"local-ai-rag","msg":"%(message)s"}')
    logger = logging.getLogger("local-ai-rag")

# ── Config ────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_MODEL       = os.getenv("LLM_MODEL", "qwen3:32b")   # or qwen3:70b, qwen3:8b
EMBED_MODEL     = os.getenv("EMBED_MODEL", "nomic-embed-text")
QDRANT_URL      = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "sahool_agri_kb")
CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "150"))
NUM_CTX         = int(os.getenv("NUM_CTX", "8192"))  # context window
# مصادقة خدمة-لخدمة: استيعاب المستندات يكتب لقاعدة المعرفة — منع تسميم RAG
AGENT_TOKEN     = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — الاستيعاب معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")

_vectorstore: Optional[QdrantVectorStore] = None
_llm: Optional[ChatOllama] = None


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
                    logger.info(f"Ollama up. Pulling {LLM_MODEL} + {EMBED_MODEL}...")
                    # Trigger pulls (non-blocking)
                    await client.post(f"{OLLAMA_BASE_URL}/api/pull",
                        json={"name": LLM_MODEL}, timeout=300.0)
                    await client.post(f"{OLLAMA_BASE_URL}/api/pull",
                        json={"name": EMBED_MODEL}, timeout=300.0)
                    return True
            except Exception as e:  # noqa: BLE001
                logger.warning("تعذّر سحب نماذج Ollama (محاولة): %s", type(e).__name__)
            await asyncio.sleep(5)
    raise RuntimeError("Ollama not available")


# ══════════════════════════════════════════════════════════════
# Vector Store Init
# ══════════════════════════════════════════════════════════════
def init_vectorstore() -> QdrantVectorStore:
    global _vectorstore
    if _vectorstore:
        return _vectorstore

    embeddings = OllamaEmbeddings(
        model=EMBED_MODEL,
        base_url=OLLAMA_BASE_URL
    )

    _vectorstore = QdrantVectorStore.from_documents(
        documents=[Document(page_content="SAHOOL initialization document.", metadata={"source": "init"})],
        embedding=embeddings,
        url=QDRANT_URL,
        prefer_grpc=False,
        collection_name=COLLECTION_NAME,
        force_recreate=False,  # keep existing
    )
    logger.info("Qdrant vector store connected")
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
def load_document(path: Path) -> List[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(path))
    elif suffix in (".txt", ".md", ".csv"):
        loader = TextLoader(str(path), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format: {suffix}")
    return loader.load()


def split_docs(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", "!", "?", "،", "；", " ", ""],
    )
    return splitter.split_documents(docs)


async def ingest_documents(file_paths: List[Path], tenant_id: str = "default") -> dict:
    vs = init_vectorstore()
    all_docs: List[Document] = []
    for p in file_paths:
        try:
            docs = load_document(p)
            for d in docs:
                d.metadata["tenant_id"] = tenant_id
                d.metadata["source_file"] = p.name
                d.metadata["ingested_at"] = datetime.now(timezone.utc).isoformat()
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
async def query_rag(question: str, tenant_id: str = "default", k: int = 5) -> dict:
    vs = init_vectorstore()
    llm = init_llm()

    # Filter by tenant (Qdrant payload filter)
    from qdrant_client.http.models import FieldCondition, MatchValue, Filter
    filters = Filter(
        must=[FieldCondition(key="metadata.tenant_id", match=MatchValue(value=tenant_id))]
    ) if tenant_id != "default" else None

    retriever = vs.as_retriever(
        search_kwargs={"k": k, "filter": filters}
    )

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
    )

    result = await asyncio.to_thread(qa.invoke, {"query": question})
    answer = result.get("result", "")
    sources = [
        {
            "source": d.metadata.get("source_file", "unknown"),
            "page": d.metadata.get("page", 0),
            "snippet": d.page_content[:200] + "..."
        }
        for d in result.get("source_documents", [])
    ]

    return {
        "question": question,
        "answer": answer,
        "model": LLM_MODEL,
        "sources": sources,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ══════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🧠 Local AI RAG starting...")
    await wait_for_ollama()
    init_llm()
    init_vectorstore()
    logger.info("🧠 RAG service ready — Qwen3 + Ollama + Qdrant")
    yield
    logger.info("🧠 RAG service stopped")



# C-07 FIX: JWT auth for RAG endpoints
_rag_security = _B(auto_error=False)
_RAG_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_RAG_SECRET = _RAG_PUBLIC if _RAG_PUBLIC else os.getenv("JWT_SECRET", "")
_RAG_ALG = "RS256" if _RAG_PUBLIC else "HS256"

async def _get_rag_user(creds: _C = Depends(_rag_security)) -> dict:
    if not creds:
        raise HTTPException(401, "Authentication required")
    try:
        payload = _jjwt.decode(creds.credentials, _RAG_SECRET,
                               algorithms=[_RAG_ALG], audience="sahool")
        return payload
    except _JE as e:
        raise HTTPException(401, str(e))

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
    tenant_id: str = "default"
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
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest, user: dict = Depends(_get_rag_user)):
    result = await query_rag(req.question, req.tenant_id, req.k)
    return result


@app.post("/ingest")
async def ingest_endpoint(
    files: List[UploadFile] = File(...),
    tenant_id: str = Form("default"),
    x_agent_token: str = Header(None)
):
    """Upload PDF/TXT/MD files to build the agricultural knowledge base.

    يتطلّب توكن خدمة (منع تسميم قاعدة المعرفة بمستندات مزوّرة).
    """
    _require_service_token(x_agent_token)
    paths: List[Path] = []
    for upload in files:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in (".pdf", ".txt", ".md", ".csv"):
            raise HTTPException(400, f"Unsupported: {suffix}")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        content = await upload.read()
        tmp.write(content)
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
        "embed_model": EMBED_MODEL
    }



@app.get("/readyz")
async def readyz():
    return {"status": "ready", "version": "9.1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
