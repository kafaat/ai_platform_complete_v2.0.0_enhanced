"""Minimal Phase 12 Python SDK surface."""
from __future__ import annotations

class SahoolClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @property
    def fields(self):
        return _Resource(self, '/v1/fields')

    @property
    def recommendations(self):
        return _Resource(self, '/v1/recommendations')

    @property
    def ecosystem(self):
        return _Resource(self, '/v1/ecosystem')


class _Resource:
    def __init__(self, client: SahoolClient, base_path: str):
        self.client = client
        self.base_path = base_path

    def url(self, suffix: str = '') -> str:
        return self.client._url(f"{self.base_path}/{suffix}".rstrip('/'))
