"""api/routers/rotation.py — الدورة الزراعيّة (Crop Rotation)
=============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

تعاقب المحاصيل — خصوبة وقائيّة. ``evaluate_rotation``/``rotation_principles``/
``suggest_next_crop`` تُستورَد مباشرةً من ``api.crop_rotation`` (نفس الكائنات التي
كان ``main`` يستوردها — نُقل الاستيراد هنا لإزالة F401 من ``main`` بعد نقل الدوالّ).
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.crop_rotation import (
    evaluate_rotation,
    rotation_principles,
    suggest_next_crop,
)

router = APIRouter()


@router.get("/api/v1/rotation/principles")
def rotation_principles_endpoint():
    """مبادئ الدورة الزراعيّة + المحاصيل المصنّفة (تثقيفي)."""
    return rotation_principles()


@router.get("/api/v1/rotation/evaluate")
def rotation_evaluate(previous: str, candidate: str):
    """يقيّم تعاقب محصولَين: هل candidate خيار جيّد بعد previous؟"""
    return evaluate_rotation(previous, candidate)


@router.get("/api/v1/rotation/suggest")
def rotation_suggest(previous: str):
    """يقترح أفضل المحاصيل التالية بعد محصول (مرتّبة)، بسياق يمني."""
    return suggest_next_crop(previous)
