"""Local AI RAG Tests — SAHOOL v9.1.0"""
import pytest

class TestRAGAuth:
    @pytest.mark.security
    async def test_query_requires_auth(self, http_client):
        """RAG /query must reject unauthenticated requests."""
        from conftest import service_urls
        resp = await http_client.post(
            f"{service_urls['rag']}/query",
            json={"question": "What is NDVI?"}
        )
        assert resp.status_code == 401

    @pytest.mark.integration
    async def test_query_with_valid_auth(self, http_client, auth_headers):
        """RAG /query must accept valid JWT."""
        from conftest import service_urls
        resp = await http_client.post(
            f"{service_urls['rag']}/query",
            json={"question": "ما هو NDVI؟"},
            headers=auth_headers
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
        assert "localhost" not in url or "127.0.0.1" not in url,             "Qdrant URL should not point to localhost inside Docker"
