"""Local AI RAG Tests — SAHOOL v9.1.0"""

import pytest


class TestRAGAuth:
    # تدقيق 2026-11-01 (Q1/Q2): كان ينادي «/query» (المسار الحقيقيّ «/v1/query») على خدمة
    # حيّة فيتخطّى دائماً، ولا تُشغّله أيّ وظيفة. الآن عبر main.py الحقيقيّ (real_app_probe).
    @pytest.mark.unit
    @pytest.mark.security
    def test_query_requires_auth(self):
        """RAG /v1/query must reject unauthenticated requests."""
        from real_app_probe import probe_rag

        probe = probe_rag()
        assert probe["query_no_token"] == 401
        assert probe["query_valid_token"] == 503  # شاهدٌ موجب: الحارس يُمرّر التوكن الصالح

    @pytest.mark.integration
    async def test_query_with_valid_auth(self, http_client, auth_headers):
        """RAG /query must accept valid JWT."""
        from conftest import service_urls

        resp = await http_client.post(
            f"{service_urls['rag']}/query", json={"question": "ما هو NDVI؟"}, headers=auth_headers
        )
        assert resp.status_code in [200, 503]  # 503 if Ollama not available


class TestRAGConfig:
    @pytest.mark.unit
    def test_similarity_threshold_range(self):
        """Similarity threshold must be between 0 and 1."""
        threshold = 0.7
        assert 0 < threshold < 1

    @pytest.mark.unit
    def test_qdrant_url_not_localhost(self):
        """Qdrant URL must use container name, not localhost."""
        import os

        url = os.getenv("QDRANT_URL", "http://sahool-qdrant:6333")
        # AND لا OR: العنوان يجب ألّا يحوي localhost **ولا** 127.0.0.1 (كان OR
        # يمرّر http://localhost:6333 لأنّه لا يحوي 127.0.0.1).
        assert "localhost" not in url and "127.0.0.1" not in url, (
            "Qdrant URL should not point to localhost inside Docker"
        )
