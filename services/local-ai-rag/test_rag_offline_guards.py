#!/usr/bin/env python3
"""Offline safety tests for local-ai-rag without Qdrant/Ollama/LangChain."""

import importlib.util
import sys
import types
from pathlib import Path


def _install_stubs():
    # Minimal modules/classes used at import time only.
    stubs = {
        "langchain_community": types.ModuleType("langchain_community"),
        "langchain_community.document_loaders": types.ModuleType(
            "langchain_community.document_loaders"
        ),
        "langchain_core": types.ModuleType("langchain_core"),
        "langchain_core.documents": types.ModuleType("langchain_core.documents"),
        "langchain_ollama": types.ModuleType("langchain_ollama"),
        "langchain_qdrant": types.ModuleType("langchain_qdrant"),
        "langchain_text_splitters": types.ModuleType("langchain_text_splitters"),
    }

    class _Doc:
        def __init__(self, page_content="", metadata=None):
            self.page_content = page_content
            self.metadata = metadata or {}

    stubs["langchain_community.document_loaders"].PyPDFLoader = object
    stubs["langchain_community.document_loaders"].TextLoader = object
    stubs["langchain_core.documents"].Document = _Doc
    stubs["langchain_ollama"].ChatOllama = object
    stubs["langchain_ollama"].OllamaEmbeddings = object
    stubs["langchain_qdrant"].QdrantVectorStore = object

    class _Splitter:
        def __init__(self, *a, **k):
            pass

        def split_documents(self, docs):
            return docs

    stubs["langchain_text_splitters"].RecursiveCharacterTextSplitter = _Splitter
    sys.modules.update(stubs)


def _load_module():
    _install_stubs()
    path = Path(__file__).with_name("main.py")
    spec = importlib.util.spec_from_file_location("local_ai_rag_main_for_tests", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_tenant_id_validation_accepts_uuid_like_and_rejects_injection():
    mod = _load_module()
    assert mod._validate_tenant_id("tenant-123_ABC") == "tenant-123_ABC"
    bad = ["", "../../etc/passwd", "tenant:other", "x" * 65, "tenant space"]
    for tenant in bad:
        try:
            mod._validate_tenant_id(tenant)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 400
        else:
            raise AssertionError(f"invalid tenant accepted: {tenant!r}")


def test_grounded_prompt_contains_no_general_knowledge_instruction_and_refusal_text():
    mod = _load_module()
    assert mod._NO_KNOWLEDGE_AR in mod._GROUNDED_PROMPT
    assert "لا تستعمل معرفتك العامّة" in mod._GROUNDED_PROMPT
    assert "لا تختلق مصادر" in mod._GROUNDED_PROMPT


def test_query_request_does_not_accept_tenant_id_from_body():
    mod = _load_module()
    fields = set(mod.QueryRequest.model_fields)
    assert "question" in fields and "k" in fields
    assert "tenant_id" not in fields
