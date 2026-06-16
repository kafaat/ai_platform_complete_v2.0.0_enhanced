"""api/document_models.py — نماذج إدارة المستندات (Document Metadata).
====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج كتلة نماذج «الوثائق».

⚠️ سجلّ بيانات وصفيّة فقط: لا يخزّن الملفّ الثنائيّ (blob). تخزين الكائنات
الفعليّ (PDF/صورة/...) يحتاج S3/MinIO — نحفظ هنا ``storage_ref`` فقط.

self-contained: pydantic + stdlib فقط. single-consumer: api/routers/documents.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentRequest(BaseModel):
    category: str = Field(pattern="^(contract|report|image|map|lab_result|other)$")
    title: str = Field(min_length=1, max_length=200)
    storage_ref: str | None = None
    content_type: str | None = Field(default=None, max_length=80)
    size_bytes: int | None = Field(default=None, ge=0)
    field_id: str | None = Field(default=None, max_length=50)  # يطابق fields.field_id VARCHAR(50)
