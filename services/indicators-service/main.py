#!/usr/bin/env python3
"""SAHOOL v9 — indicators-service (نقطة دخول stub صحّيّة).

ملاحظة صدق: المنطق الفعلي للمؤشّرات مُنفَّذ حاليّاً داخل
`sahool-platform/api` (وليس هنا). كانت هذه الخدمة مُسجَّلة في
docker-compose مع `CMD uvicorn main:app` لكن **بلا ملفّ main.py** ⇒
الحاوية تدخل crash-loop عند الإقلاع. هذا الـstub يوفّر تطبيق FastAPI
بفحوص /healthz و/readyz فقط، كي تُقلع الحاوية «صحّيّة» دون ادّعاء منطق
غير موجود، إلى حين الدمج/الإزالة المعماريّة المخطّط لها.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

VERSION = os.getenv("SERVICE_VERSION", "9.0.0-stub")

app = FastAPI(
    title="SAHOOL Indicators Service (stub)",
    version=VERSION,
    description="نقطة دخول صحّيّة؛ منطق المؤشّرات الفعلي في sahool-platform/api.",
)


@app.get("/healthz")
@app.get("/health")
async def health():
    return {"status": "alive", "service": "indicators-service", "version": VERSION}


@app.get("/readyz")
async def ready():
    # stub: جاهز دائماً (لا تبعيّات خارجيّة). يُبقي healthcheck الحاوية أخضر.
    return {"status": "ready", "service": "indicators-service", "stub": True}


@app.get("/")
async def root():
    return {
        "service": "indicators-service",
        "stub": True,
        "note": "منطق المؤشّرات الفعلي مُخدَّم من sahool-platform/api؛ هذه نقطة دخول صحّيّة فقط.",
    }
